# Hippius Storage Assistant

A CLI tool for securely storing and retrieving encrypted files from the Hippius storage system.

## Features

- **Secure Encryption**: Uses GPG symmetric encryption to protect files before upload.
- **Per-Bucket Isolation**: Each bucket uses a unique encryption key and algorithm.
- **Local Key Management**: Keys are stored locally in `.hippius-skill/config.ini` and never uploaded.
- **Data Integrity**: Streaming uploads with on-the-fly hashing to verify ciphertext integrity.
- **Flat Namespace**: Supports "folders" via path delimiters in a flat storage model.

## CLI Commands

- `hippius upload <bucket> <local-path> <remote-path>`: Encrypts and uploads a file.
- `hippius download <bucket> <remote-path> <local-path>`: Downloads and decrypts a file.
- `hippius list <bucket> [prefix]`: Lists files in a bucket, optionally filtered by prefix.
- `hippius delete <bucket> <remote-path>`: Deletes a file from a bucket.
- `hippius config add-bucket <bucket-name>`: Generates a random passphrase and adds a new bucket to the local config.

## Architecture

Detailed design decisions are documented in the [Architecture Decision Records (ADRs)](./docs/adr/).
The project glossary is maintained in [CONTEXT.md](./CONTEXT.md).