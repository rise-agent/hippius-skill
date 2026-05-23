# Hippius Storage Assistant

A CLI tool for securely storing and retrieving encrypted files from the Hippius storage system.

## Language

**Bucket**:
An S3 Bucket on the Hippius platform, managed through the Hippius REST API. Each Bucket has a unique encryption passphrase and dedicated S3 credentials derived from a Sub Token.
_Avoid_: Folder, namespace.

**File**:
A piece of encrypted data stored within a **Bucket**, referenced by a flat key string with delimiter-based path simulation (e.g., `path/to/file.txt`).
_Avoid_: Object, blob.

**Master Token**:
The long-lived credential used to authenticate with the Hippius REST API for account-level operations (creating Buckets, managing Sub Tokens). Stored once in the user configuration and never used for S3 operations.
_Avoid_: API key, master key.

**Sub Token**:
A scoped, revocable credential created via the Hippius REST API from a **Master Token**. Each Sub Token is bound to a single **Bucket** and provides a unique `access_key`/`secret_key` pair for S3 operations.
_Avoid_: S3 key, child token.

## Relationships

- **Master Token → Sub Token**: One-to-many. A single Master Token can create many Sub Tokens, each scoped to one Bucket.
- **Bucket → Sub Token**: One-to-one. Each Bucket owns exactly one Sub Token and one encryption passphrase.
- **Bucket → File**: One-to-many. A Bucket can contain many Files.

## Example Dialogue

> **Dev**: I want to back up my project files.
> **User**: Run `hippius-skill config add-bucket project-backups`. It will create the Bucket on Hippius, generate a Sub Token with its own S3 credentials, and store a random passphrase locally.
> **Dev**: So I upload `/data dump.sql` as `backups/dump.sql`?
> **User**: Exactly. The CLI encrypts it with that passphrase, streams the ciphertext through GPG, and boto3 uploads it with an S3 SHA-256 checksum. The Hippius server verifies the checksum.
> **Dev**: What if I need to revoke access later?
> **User**: Revoke the Sub Token on Hippius, or remove the Bucket from local config. The Master Token stays untouched.

## Flagged Ambiguities

- **Bucket** in the Hippius UI may refer to the web dashboard's concept of a storage container. In this project, **Bucket** always means the S3 Bucket created via the Hippius REST API, combined with its local encryption key and Sub Token credentials.
- **File** in S3 terminology is an Object. In this project, **File** is the encrypted piece of data as seen by the CLI user.
