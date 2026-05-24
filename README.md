# Hippius Storage Assistant

A CLI tool and Hermes Agent skill for securely storing and retrieving encrypted files from the Hippius storage system.

## Features

- **Secure Encryption**: Uses GPG symmetric encryption to protect files before upload.
- **Per-Bucket Isolation**: Each bucket uses a unique encryption key and algorithm.
- **Local Key Management**: Keys are stored locally in `.hippius-skill/config.ini` and never uploaded.
- **Data Integrity**: Streaming uploads with on-the-fly hashing to verify ciphertext integrity.
- **Flat Namespace**: Supports "folders" via path delimiters in a flat storage model.

## Installation

### Python CLI

```bash
pip install hippius-skill
```

Verify:
```bash
hippius-skill --help
```

### Hermes Agent Skill (optional)

To get Hermes Agent to know how to operate this CLI:

```bash
hermes skills install anlach/hippius-skill
```

Or add this repository as a skill source:

```bash
hermes skills tap add anlach/hippius-skill
hermes skills search hippius-backup
```

## Quick Start

Before using file commands, store your Hippius Master Token and create a Bucket:

```bash
# Store your Master Token (run once)
hippius-skill config init --master-token <token>

# Create a Bucket on Hippius and store it locally
hippius-skill config add-bucket <bucket-name>

# List locally configured Buckets
hippius-skill config list-buckets

# Remove a Bucket (deletes all Files, the Bucket, and revokes its Sub Token)
hippius-skill config remove-bucket <bucket-name>
```

## File Operations

```bash
# Encrypt and upload a file
hippius-skill upload <bucket> <local-path> <remote-path>

# Download and decrypt a file
hippius-skill download <bucket> <remote-path> <local-path>

# List files in a Bucket, optionally filtered by prefix
hippius-skill list <bucket> --prefix <prefix>

# Delete a file from a Bucket
hippius-skill delete <bucket> <remote-path>
```

## Shell Completion

Tab completion is available via Click's built-in shell completion support.

### Bash (≥4.4)

```bash
# Evaluate on-the-fly (current session)
eval "$(hippius-skill config completion bash)"

# Install permanently
hippius-skill config completion bash | sudo tee /etc/bash_completion.d/hippius-skill
```

### Zsh

```zsh
# Evaluate on-the-fly (current session)
source <(hippius-skill config completion zsh)

# Install permanently
hippius-skill config completion zsh > "${fpath[1]}/_hippius-skill"
```

### Fish

```fish
# Evaluate on-the-fly (current session)
hippius-skill config completion fish | source

# Install permanently
hippius-skill config completion fish > ~/.config/fish/completions/hippius-skill.fish
```

## Architecture

Detailed design decisions are documented in the [Architecture Decision Records (ADRs)](./docs/adr/).
The project glossary is maintained in [CONTEXT.md](./CONTEXT.md).