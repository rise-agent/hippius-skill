# Implementation Plan: Hippius Storage Assistant

## 1. Project Structure

```
hippius-skill/
├── src/
│   ├── hippius/
│   │   ├── __init__.py
│   │   ├── cli.py              # Click-based CLI entrypoint
│   │   ├── config.py           # ConfigParser for .hippius-skill/config.ini
│   │   ├── crypto.py           # GPG symmetric encryption/decryption
│   │   ├── storage.py          # Hippius API client
│   │   └── integrity.py        # Streaming hash calculator
│   └── tests/
│       ├── test_crypto.py
│       ├── test_config.py
│       ├── test_storage.py
│       └── test_cli.py
├── docs/
│   └── adr/
│       └── ...
├── CONTEXT.md
├── README.md
├── PLAN.md
├── pyproject.toml              # Build system, dependencies
└── .gitignore
```

## 2. Technology Stack

- **Language**: Python 3.10+
- **CLI Framework**: `click` — standard for composable CLIs
- **Configuration**: `configparser` from stdlib
- **Encryption**: `python-gnupg` wrapper around system GPG binary
- **HTTP Client**: `httpx` — async-capable, modern Requests replacement
- **Testing**: `pytest`
- **Build Tool**: `hatchling` via `pyproject.toml`

## 3. Configuration Management (`src/hippius/config.py`)

### Responsibilities
- Locate `.hippius-skill/config.ini` (searching upward from cwd, falling back to `~/.hippius-skill/config.ini`)
- Read/write bucket definitions with fields:
  - `passphrase`
  - `algorithm`
- Ensure the config file has `chmod 600` permissions

### Implementation Steps
1. Define a `Config` class that loads the INI file on instantiation.
2. Provide `get_bucket(name) -> dict` raising `BucketNotFoundError` if absent.
3. Provide `add_bucket(name, algorithm="AES256")` that generates a 256-bit random passphrase using `secrets.token_urlsafe(32)`, writes the section, and saves.
4. Provide `list_buckets() -> list[str]`.

## 4. Encryption Layer (`src/hippius/crypto.py`)

### Responsibilities
- Encrypt plaintext streams to ciphertext streams
- Decrypt ciphertext streams to plaintext streams

### Implementation Steps
1. `encrypt(bucket_name: str, plaintext_stream: BinaryIO) -> BinaryIO`
   - Look up the bucket’s passphrase and algorithm from config.
   - Spawn `gpg --symmetric --cipher-algo <algorithm> --passphrase-fd 0 --batch --no-tty --yes`.
   - Feed passphrase and plaintext via stdin.
   - Return a BytesIO of the ciphertext.
   
2. `decrypt(bucket_name: str, ciphertext_stream: BinaryIO) -> BinaryIO`
   - Spawn `gpg --decrypt --passphrase-fd 0 --batch --no-tty --yes`.
   - Feed passphrase and ciphertext via stdin.
   - Return a BytesIO of the plaintext.
   
3. Use a context manager (`@contextlib.contextmanager`) to ensure GPG processes are cleaned up.

### Note on Streaming
`python-gnupg` provides a wrapper that handles the GPG binary. To support true streaming, we should use `subprocess.Popen` directly when needed for very large files, but for the MVP, `python-gnupg`’s `encrypt_file` with file-like objects is sufficient.

## 5. Hippius Storage Client (`src/hippius/storage.py`)

### Responsibilities
- Upload encrypted data
- Download encrypted data
- List keys with prefix filtering
- Delete keys
- Retrieve server-side hash for integrity verification

### Implementation Steps
1. Define `HippiusClient(base_url: str, api_key: str)`.
2. `upload(bucket: str, key: str, data: BinaryIO, content_hash: str) -> str`
   - POST to `/buckets/{bucket}/files/{key}`.
   - Include `Content-Hash: <content_hash>` header.
   - Return the server-reported hash from the response body/headers.
3. `download(bucket: str, key: str) -> BinaryIO`
   - GET from `/buckets/{bucket}/files/{key}`.
   - Return a BytesIO of ciphertext. The caller will decrypt.
4. `list_files(bucket: str, prefix: str = "") -> list[str]`
   - GET from `/buckets/{bucket}/files?prefix=<prefix>`.
5. `delete(bucket: str, key: str)`
   - DELETE `/buckets/{bucket}/files/{key}`.

### Configuration for Hippius Server
Add a `[hippius]` section to `config.ini` for server URL and API key, e.g.:
```ini
[hippius]
base_url = https://api.hippius.example.com
api_key = <secret>
```

## 6. Integrity / Streaming Hash (`src/hippius/integrity.py`)

### Responsibilities
- Compute SHA-256 of a stream without buffering the entire stream in memory.
- Pass through all bytes unchanged.

### Implementation Steps
1. Define `HashingStream(raw_stream: BinaryIO)` as a file-like wrapper.
2. On `read()` calls, pass through to the underlying stream, update an internal `hashlib.sha256()`, and return the chunk.
3. Provide `hexdigest() -> str` after EOF.

### Upload Flow
```python
hasher = HashingStream(plaintext_file)
gpg_stream = crypto.encrypt(bucket, hasher)
# Actually, we need to hash the *ciphertext*, not plaintext.
# Correct flow:
encryptor = crypto.StreamingEncryptor(bucket)
hasher = HashingStream(encryptor)
client.upload(bucket, key, hasher, hasher.hexdigest())
```
**Correction**: The hash for integrity verification should be computed on the **ciphertext** stream.
Correct flow:
1. Read plaintext chunk.
2. Pass through GPG subprocess stdin.
3. Receive ciphertext chunk from GPG subprocess stdout.
4. Update SHA-256.
5. Yield ciphertext chunk to HTTP client.
6. After EOF, compare local hash with server-reported hash.

This requires `crypto.py` to support a generator-based streaming interface rather than a simple `encrypt()` wrapper.

## 7. CLI Implementation (`src/hippius/cli.py`)

### Commands

```
hippius upload <bucket> <local-path> <remote-path>
hippius download <bucket> <remote-path> <local-path>
hippius list <bucket> [--prefix <prefix>]
hippius delete <bucket> <remote-path>
hippius config add-bucket <bucket-name> [--algorithm ALGO]
hippius config list-buckets
```

### Design Notes
- **Global `--config` flag**: Allow overriding the default `.hippius-skill/config.ini` path.
- **Suggestions**: If a bucket is misspelled, suggest the closest match from `config.list_buckets()`.
- **Strict enforcement**: Every operation referencing a bucket must verify it exists in config first.
- **Progress output**: Use `click.progressbar` for upload/download.
- **Exit codes**: 
  - `0`: Success
  - `1`: General error
  - `2`: Configuration error (missing bucket, bad config file)
  - `3`: Integrity mismatch (hash mismatch after upload)

## 8. Skill File (`SKILL.md` in repo root or `.kilo/skills/`)

The skill file describes how to instruct an AI agent to use the CLI *without* referencing implementation details.

### Contents
- How to check if the CLI is installed.
- How to check available buckets (`hippius config list-buckets`).
- How to add a bucket if one is missing.
- How to upload/download/list/delete files.
- **Important**: The skill must remind the AI never to read or write the `config.ini` file, never to inspect passphrases, and never to upload the config file itself.

## 9. Testing Strategy

### Unit Tests
- `test_config.py`: Mock filesystem, test read/write, test `chmod 600` enforcement.
- `test_crypto.py`: Mock GPG binary or use a temporary GNUPGHOME with a known passphrase. Verify round-trip encrypt/decrypt.
- `test_integrity.py`: Verify `HashingStream` yields exact bytes and computes correct SHA-256.
- `test_storage.py`: Mock `httpx` responses. Verify correct URLs, headers, and error handling.
- `test_cli.py`: Use `click.testing.CliRunner` to invoke commands. Mock `config`, `crypto`, and `storage` modules.

### Integration Tests (manual for MVP)
- Actually run against a Hippius dev instance.
- Verify upload/download round-trip and hash verification.

## 10. Build & Distribution

### Steps
1. Define `[project]` and `[project.scripts]` in `pyproject.toml`:
   ```toml
   [project.scripts]
   hippius = "hippius.cli:main"
   ```
2. Build a wheel: `python -m build`.
3. Install: `pip install -e .` for development.
4. (Future) Publish to PyPI.

## 11. Milestone Checklist

- [ ] `pyproject.toml` and project skeleton
- [ ] `config.py` + tests
- [ ] `crypto.py` + tests
- [ ] `integrity.py` + tests
- [ ] `storage.py` + tests
- [ ] `cli.py` + tests
- [ ] `SKILL.md` written
- [ ] README updated with installation instructions
- [ ] Manual integration test against Hippius
