---
name: hippius-backup
description: Back up and retrieve encrypted files using the hippius-skill CLI. Use when the user asks to store files in Hippius, download from Hippius, or manage Hippius Buckets.
---

<what-to-do>

You are an operator of the `hippius-skill` CLI. Your goal is to move files between the local filesystem and Hippius Buckets without needing to know the underlying encryption, GPG streaming, boto3, or S3 implementation details.

When tasked with backing up or retrieving files:
1. Identify the source path, target Bucket name, and target File key.
2. Use the `hippius-skill` CLI to perform the operation.
3. Verify the success of the command via its exit code and output.

If a Bucket does not exist or the user hasn't configured one, guide them to use the configuration commands (e.g., `hippius-skill config add-bucket <name>`) before attempting file operations.

</what-to-do>

<supporting-info>

## Domain Terminology
Always adhere to the following terms from the project's CONTEXT.md:
- **Bucket**: The encrypted storage container on the Hippius platform, managed via the Hippius REST API. Each has a unique encryption passphrase and dedicated S3 credentials derived from a Sub Token.
- **File**: A piece of encrypted data stored within a Bucket, referenced by a flat key string with delimiter-based path simulation (e.g., `path/to/file.txt`).
- **Sub Token**: A scoped, revocable credential created from a Master Token. Each is bound to a single Bucket. Handled internally by the CLI.
- **Master Token**: The long-lived credential for account-level operations (creating Buckets, managing Sub Tokens). Stored once in user configuration and never used for S3 operations.

## CLI Reference

### Configuration
**Store the Hippius Master Token:**
`hippius-skill config init --master-token <token>`

**Create a Bucket on Hippius and store it locally:**
`hippius-skill config add-bucket <bucket-name>`

**List locally configured Buckets:**
`hippius-skill config list-buckets`

**Remove a Bucket from Hippius and local config:**
`hippius-skill config remove-bucket <bucket-name>`
Deletes all Files in the Bucket, deletes the Bucket via the Hippius API, revokes the Sub Token, and removes the local configuration. If any File deletion fails, the command aborts and the local config is preserved.

### File Operations
**Encrypt and upload a local file:**
`hippius-skill upload <bucket-name> <local-path> <remote-file-key>`

**Download a File and decrypt it:**
`hippius-skill download <bucket-name> <remote-file-key> <local-path>`

**List Files in a Bucket matching a prefix:**
`hippius-skill list <bucket-name> --prefix <prefix>`

**Delete a File from a Bucket:**
`hippius-skill delete <bucket-name> <remote-file-key>`

## Operational Constraints
- Never attempt to manually manage S3 credentials (access_key/secret_key), encryption passphrases, or GPG parameters; rely entirely on the `hippius-skill` CLI.
- Always ensure the destination directory for a download exists or is valid before executing.

</supporting-info>
