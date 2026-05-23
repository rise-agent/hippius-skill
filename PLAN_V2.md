# Implementation Plan V2: Hippius Storage Assistant

This is the authoritative plan. Decisions made during the grilling session supersede anything in PLAN.md.

---

## 1. Naming

The project name is **`hippius-skill`** in all contexts:

| Context | Name |
|---------|------|
| Python package | `hippius_skill` |
| CLI command | `hippius-skill` |
| Config directory | `.hippius-skill/` |
| PyPI distribution | `hippius-skill` |

---

## 2. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.10+ | Async not needed; boto3 is sync |
| CLI Framework | `click` | Standard for composable CLIs |
| User Config | `configparser` + INI | Simple, stdlib |
| App Config | `configparser` + INI (shipped in package) | Global defaults, read-only |
| Storage Client | `boto3` | Hippius exposes S3-compatible API |
| HTTP Client (REST) | `httpx` | For Hippius REST API (token mgmt) |
| Encryption | `subprocess.Popen` + GPG | Memory-efficient streaming |
| Threading | `threading` + `queue.Queue` | GPG stdin/stdout producer-consumer |
| Integrity | `boto3` `ChecksumAlgorithm='SHA256'` | Delegated to S3 SDK |
| Testing | `pytest` | Standard |
| Build Tool | `hatchling` via `pyproject.toml` | Modern Python packaging |

---

## 3. Architecture Overview

### Two-Tier Hippius API

```
Hippius REST API (api.hippius.com)
  ├─ Master Token  ──► Create/Revoke Sub-tokens
  │                     Sub-token → S3 credentials (access_key, secret_key)
  │
  └─ Bucket API    ──► Create/Delete/List buckets

Hippius S3 API (s3.hippius.com)
  └─ S3 credentials from sub-token
     ├─ put_object (Body=GpgEncryptStream)  → Upload encrypted file
     ├─ get_object                            → Download encrypted file
     ├─ list_objects_v2                       → List files in bucket
     └─ delete_object                         → Delete file
```

### Authentication Flow

```
hippius-skill config init --master-token <token>
  └─ Stores master token in ~/.hippius-skill/config.ini

hippius-skill config add-bucket <name> [--algorithm ALGO]
  ├─ Creates S3 bucket via Hippius REST API
  ├─ Creates sub-token via REST API (scope: single_bucket)
  ├─ Stores sub-token S3 credentials (access_key, secret_key)
  ├─ Generates 256-bit passphrase via secrets.token_urlsafe(32)
  ├─ Stores algorithm (default: AES256)
  └─ Fails if bucket already exists
```

### Upload Flow

```python
source = open("local-file.txt", "rb")
encrypt_stream = GpgEncryptStream(bucket="backups", source=source)
# boto3 reads from encrypt_stream, which:
#   - pipes plaintext → GPG stdin in a background thread
#   - yields ciphertext from GPG stdout on read()

s3_client.put_object(
    Bucket="backups",
    Key="path/to/file.txt",
    Body=encrypt_stream,
    ChecksumAlgorithm="SHA256",
)
# boto3 computes SHA-256 of ciphertext, server verifies,
# response includes ChecksumSHA256
```

### Download Flow

```python
response = s3_client.get_object(
    Bucket="backups",
    Key="path/to/file.txt",
    ChecksumMode="ENABLED",
)
# boto3 verifies ChecksumSHA256 automatically if available

decrypt_stream(
    bucket="backups",
    ciphertext_stream=response["Body"],
    destination_path="/tmp/decrypted.txt",
)
# pipes ciphertext chunks → GPG stdin → writes plaintext to file
```

---

## 4. Configuration

### Split Config Model

| File | Scope | Format | Permissions |
|------|-------|--------|-------------|
| `src/hippius_skill/app.ini` | Global defaults | Static INI, read-only | Package file |
| `~/.hippius-skill/config.ini` | User data | INI, read/write | `chmod 600` |

No environment variable overrides. No user-level override of app defaults. Simple, explicit.

### `app.ini` (shipped with package)

```ini
[hippius]
api_url = https://api.hippius.com
s3_endpoint = https://s3.hippius.com
region = decentralized
signature_version = s3v4
addressing_style = path
```

### `~/.hippius-skill/config.ini`

```ini
[hippius]
api_token = <master-token-for-rest-api>

[bucket:backups]
algorithm = AES256
passphrase = <generated>
access_key = <sub-token-access-key>
secret_key = <sub-token-secret-key>

[bucket:photos]
algorithm = AES256
passphrase = <generated>
access_key = <sub-token-access-key>
secret_key = <sub-token-secret-key>
```

The file is created lazily on first write. Every write enforces `chmod 600`.

---

## 5. Module Design

### `config.py`

```python
class Config:
    def __init__(self, path: Path | None = None)
    def get_master_token() -> str                    # Reads [hippius] api_token
    def set_master_token(token: str)                 # Writes [hippius] api_token
    def get_bucket(name) -> BucketConfig             # Raises BucketNotFoundError
    def add_bucket(name, algorithm="AES256")         # Generates passphrase
    def list_buckets() -> list[str]                  # Names only
    def remove_bucket(name)                          # Deletes bucket section

@dataclass
class BucketConfig:
    name: str
    algorithm: str
    passphrase: str
    access_key: str
    secret_key: str
```

Responsibilities:
- Locate config (search upward from cwd → `~/.hippius-skill/config.ini`)
- Read/write bucket sections
- `chmod 600` enforcement
- Suggest closest match on misspelled bucket name

### `crypto.py`

```python
class GpgEncryptStream:
    """File-like object for boto3 put_object Body= argument.
    Reads plaintext from source_stream, pipes through GPG, yields ciphertext.
    """
    def __init__(self, bucket: str, source_stream: BinaryIO)
    def read(self, size: int = -1) -> bytes
    def close(self)
    def __enter__(self) -> Self
    def __exit__(self, ...)

def decrypt_stream(bucket: str, ciphertext_stream: BinaryIO, destination_path: Path) -> None:
    """Consumes ciphertext_stream, pipes through GPG, writes plaintext to destination_path."""
```

**Implementation notes:**
- Spawns `gpg --symmetric --cipher-algo <algorithm> --passphrase-fd 0 --batch --no-tty --yes -o -`
- Passphrase written to GPG stdin first, then plaintext in a background thread
- `read()` pulls from GPG stdout in chunks
- If GPG returns non-empty stderr on close, raise `EncryptionError`

### `hippius_client.py` (REST API client)

```python
class HippiusClient:
    def __init__(self, api_token: str, base_url: str)
    def create_bucket(name: str) -> None
    def create_sub_token(
        name: str,
        scope_type: str = "single_bucket",
        bucket_names: list[str] | None = None,
    ) -> dict  # Returns {access_key, secret_key}
    def delete_bucket(name: str) -> None
    def list_buckets() -> list[str]
    def revoke_sub_token(token_id: str) -> None
```

Uses `httpx` for REST calls to `api.hippius.com`.

### `storage.py` (S3 client wrapper)

```python
class Storage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, region: str)
    def upload(bucket: str, key: str, data: BinaryIO) -> dict  # Returns {checksum, etag}
    def download(bucket: str, key: str) -> BinaryIO            # StreamingBody
    def list_files(bucket: str, prefix: str = "") -> list[str]
    def delete(bucket: str, key: str) -> None
```

### `cli.py`

Commands:

```bash
# Global flag
hippius-skill --config /custom/path/config.ini <command>

# Configuration
hippius-skill config init --master-token <token>
hippius-skill config add-bucket <name> [--algorithm ALGO]
hippius-skill config list-buckets
hippius-skill config remove-bucket <name>

# File operations (each requires bucket to exist in config first)
hippius-skill upload <bucket> <local-path> <remote-path>
hippius-skill download <bucket> <remote-path> <local-path>
hippius-skill list <bucket> [--prefix <prefix>]
hippius-skill delete <bucket> <remote-path>
```

**Exit codes:**
- `0` Success
- `1` General error
- `2` Configuration error (missing bucket, bad config)
- `3` Integrity mismatch
- `4` Encryption error

**Progress:** `click.progressbar` for upload/download.

---

## 6. Project Structure

```
hippius-skill/
├── src/
│   └── hippius_skill/
│       ├── __init__.py
│       ├── __about__.py        # Version
│       ├── app.ini             # Global defaults (endpoints)
│       ├── cli.py              # Click commands
│       ├── config.py           # ConfigParser wrapper
│       ├── crypto.py           # GpgEncryptStream + decrypt_stream
│       ├── hippius_client.py   # REST API client
│       └── storage.py          # boto3 S3 wrapper
├── tests/
│   ├── test_config.py
│   ├── test_crypto.py
│   ├── test_hippius_client.py
│   ├── test_storage.py
│   └── test_cli.py
├── docs/
│   └── adr/
│       ├── 0001-gpg-symmetric-encryption.md
│       ├── 0002-local-config-key-management.md
│       ├── 0003-streaming-with-s3-native-checksums.md
│       └── 0004-flat-namespace.md
├── CONTEXT.md                  # Glossary (Bucket, File)
├── PLAN.md                     # Original plan (superseded)
├── PLAN_V2.md                  # This plan (authoritative)
├── README.md
├── pyproject.toml
└── .gitignore
```

---

## 7. Key Constraints & Limits

| Constraint | Value | Rationale |
|------------|-------|-----------|
| Single-upload size limit | 5 GB | S3 single-part `put_object` limit |
| No temp files | ENFORCED | Memory-efficient GPG subprocess streaming |
| Plain text secrets | PERMITTED | `chmod 600` only, no keyring for MVP |
| No env var overrides | ENFORCED | App config is authoritative, no override chain |
| Scope type per sub-token | `single_bucket` | One sub-token per bucket for isolation |

---

## 8. Testing Strategy

| Test File | Coverage |
|-----------|----------|
| `test_config.py` | INI read/write, bucket CRUD, chmod 600, path resolution, misspelling suggestion |
| `test_crypto.py` | Mock GPG binary (test subprocess wrapper without real GPG), round-trip encrypt/decrypt via temporary GNUPGHOME |
| `test_hippius_client.py` | Mock `httpx` responses for REST API endpoints (create bucket, create sub-token, list) |
| `test_storage.py` | Mock `boto3` client (upload/download/list/delete with checksums) |
| `test_cli.py` | `click.testing.CliRunner`, mock all underlying modules |

Integration tests: Manual against Hippius dev environment for end-to-end upload/download round-trip.

---

## 9. Milestone Checklist

- [ ] `pyproject.toml` and project skeleton
- [ ] `app.ini` with default endpoints
- [ ] `config.py` + tests
- [ ] `hippius_client.py` + tests
- [ ] `crypto.py` + tests
- [ ] `storage.py` + tests
- [ ] `cli.py` + tests
- [ ] SKILL.md written
- [ ] README updated
- [ ] Manual integration test against Hippius
