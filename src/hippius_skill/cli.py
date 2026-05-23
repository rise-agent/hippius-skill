"""Click CLI for hippius-skill.

Exit codes:
  0  Success
  1  General error
  2  Configuration error
  3  Integrity mismatch
  4  Encryption error
"""

import os
import sys
from pathlib import Path

import click

from hippius_skill.config import BucketNotFoundError, Config, ConfigError
from hippius_skill.crypto import EncryptionError, GpgEncryptStream, decrypt_stream
from hippius_skill.hippius_client import HippiusClient, HippiusClientError
from hippius_skill.storage import IntegrityError as StorageIntegrityError, Storage


# --------------------------------------------------------------------------- #
# Exit-code helpers
# --------------------------------------------------------------------------- #

_EXIT_OK = 0
_EXIT_GENERAL = 1
_EXIT_CONFIG = 2
_EXIT_INTEGRITY = 3
_EXIT_ENCRYPTION = 4


def _handle_exc(exc: Exception) -> int:
    """Map exceptions to exit codes and print a friendly message."""
    if isinstance(exc, (BucketNotFoundError, ConfigError)):
        click.secho(f"Configuration error: {exc}", fg="red", err=True)
        return _EXIT_CONFIG
    if isinstance(exc, StorageIntegrityError):
        click.secho(f"Integrity mismatch: {exc}", fg="red", err=True)
        return _EXIT_INTEGRITY
    if isinstance(exc, EncryptionError):
        click.secho(f"Encryption error: {exc}", fg="red", err=True)
        return _EXIT_ENCRYPTION
    if isinstance(exc, HippiusClientError):
        click.secho(f"Hippius API error: {exc}", fg="red", err=True)
        return _EXIT_GENERAL
    if isinstance(exc, (OSError, IOError)):
        click.secho(f"File I/O error: {exc}", fg="red", err=True)
        return _EXIT_GENERAL
    raise exc  # unexpected – re-raise


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #


def _get_config(click_ctx: click.Context) -> Config:
    return click_ctx.ensure_object(dict)["config"]


def _get_app_defaults():
    return Config.get_app_defaults()


def _get_hippius_client(config: Config) -> HippiusClient:
    token = config.get_master_token()
    defaults = _get_app_defaults()
    return HippiusClient(token, base_url=defaults.get("hippius", "api_url"))


def _get_storage(bucket_cfg) -> Storage:
    defaults = _get_app_defaults()
    return Storage(
        endpoint=defaults.get("hippius", "s3_endpoint"),
        access_key=bucket_cfg.access_key,
        secret_key=bucket_cfg.secret_key,
        region=defaults.get("hippius", "region"),
        signature_version=defaults.get("hippius", "signature_version"),
        addressing_style=defaults.get("hippius", "addressing_style"),
    )


# --------------------------------------------------------------------------- #
# Main group
# --------------------------------------------------------------------------- #


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    help="Path to a custom config INI file.",
)
@click.pass_context
def cli(click_ctx: click.Context, config_path: Path | None) -> None:
    """hippius-skill – securely store and retrieve encrypted files."""
    cfg = Config(path=config_path)
    click_ctx.ensure_object(dict)["config"] = cfg


# --------------------------------------------------------------------------- #
# Config commands
# --------------------------------------------------------------------------- #


@cli.group("config")
def config_cmd():
    """Manage configuration and buckets."""
    pass


@config_cmd.command("init")
@click.option("--master-token", prompt="Master token", hide_input=True, required=True)
@click.pass_context
def config_init(click_ctx: click.Context, master_token: str) -> None:
    """Store the Hippius master token."""
    cfg = _get_config(click_ctx)
    try:
        cfg.set_master_token(master_token)
        click.echo("Master token stored.")
    except Exception as exc:
        sys.exit(_handle_exc(exc))


@config_cmd.command("add-bucket")
@click.argument("name")
@click.option("--algorithm", default="AES256", show_default=True)
@click.pass_context
def config_add_bucket(click_ctx: click.Context, name: str, algorithm: str) -> None:
    """Create a bucket on Hippius and store it locally."""
    cfg = _get_config(click_ctx)
    try:
        client = _get_hippius_client(cfg)
        client.create_bucket(name)
        sub = client.create_sub_token(
            name, scope_type="single_bucket", bucket_names=[name], actions=["read", "write"]
        )
        bucket_cfg = cfg.add_bucket(
            name,
            algorithm,
            access_key=sub.get("accessKeyId", ""),
            secret_key=sub.get("secret", ""),
        )
        click.echo(f"Bucket '{name}' created with algorithm {bucket_cfg.algorithm}.")
    except Exception as exc:
        sys.exit(_handle_exc(exc))


@config_cmd.command("list-buckets")
@click.pass_context
def config_list_buckets(click_ctx: click.Context) -> None:
    """List locally configured buckets."""
    cfg = _get_config(click_ctx)
    buckets = cfg.list_buckets()
    if not buckets:
        click.echo("No buckets configured.")
    for name in buckets:
        click.echo(name)


@config_cmd.command("remove-bucket")
@click.argument("name")
@click.pass_context
def config_remove_bucket(click_ctx: click.Context, name: str) -> None:
    """Remove a bucket from local configuration."""
    cfg = _get_config(click_ctx)
    cfg.remove_bucket(name)
    click.echo(f"Bucket '{name}' removed from configuration.")


# --------------------------------------------------------------------------- #
# File operations
# --------------------------------------------------------------------------- #


@cli.command()
@click.argument("bucket")
@click.argument("local_path", type=click.Path(path_type=Path, exists=True))
@click.argument("remote_path")
@click.pass_context
def upload(click_ctx: click.Context, bucket: str, local_path: Path, remote_path: str) -> None:
    """Encrypt and upload LOCAL_PATH to BUCKET as REMOTE_PATH."""
    cfg = _get_config(click_ctx)
    try:
        bucket_cfg = cfg.get_bucket(bucket)
        storage = _get_storage(bucket_cfg)

        with open(local_path, "rb") as fh:
            encryptor = GpgEncryptStream(
                passphrase=bucket_cfg.passphrase,
                algorithm=bucket_cfg.algorithm,
                source_stream=fh,
            )
            with encryptor:
                result = storage.upload(bucket, remote_path, encryptor)

        click.echo(f"Uploaded {local_path} → {bucket}/{remote_path}")
        click.echo(f"SHA-256: {result.get('checksum', 'n/a')}")
    except Exception as exc:
        sys.exit(_handle_exc(exc))


@cli.command()
@click.argument("bucket")
@click.argument("remote_path")
@click.argument("local_path", type=click.Path(path_type=Path))
@click.pass_context
def download(
    click_ctx: click.Context,
    bucket: str,
    remote_path: str,
    local_path: Path,
) -> None:
    """Download REMOTE_PATH from BUCKET and decrypt to LOCAL_PATH."""
    cfg = _get_config(click_ctx)
    try:
        bucket_cfg = cfg.get_bucket(bucket)
        storage = _get_storage(bucket_cfg)

        body = storage.download(bucket, remote_path)
        try:
            decrypt_stream(
                passphrase=bucket_cfg.passphrase,
                algorithm=bucket_cfg.algorithm,
                ciphertext_stream=body,
                destination_path=local_path,
            )
        finally:
            body.close()

        click.echo(f"Downloaded {bucket}/{remote_path} → {local_path}")
    except Exception as exc:
        sys.exit(_handle_exc(exc))


@cli.command("list")
@click.argument("bucket")
@click.option("--prefix", default="", show_default=True)
@click.pass_context
def list_files(click_ctx: click.Context, bucket: str, prefix: str) -> None:
    """List files in BUCKET matching PREFIX."""
    cfg = _get_config(click_ctx)
    try:
        bucket_cfg = cfg.get_bucket(bucket)
        storage = _get_storage(bucket_cfg)
        keys = storage.list_files(bucket, prefix=prefix)
        if not keys:
            click.echo("No files found.")
        for key in keys:
            click.echo(key)
    except Exception as exc:
        sys.exit(_handle_exc(exc))


@cli.command()
@click.argument("bucket")
@click.argument("remote_path")
@click.pass_context
def delete(click_ctx: click.Context, bucket: str, remote_path: str) -> None:
    """Delete REMOTE_PATH from BUCKET."""
    cfg = _get_config(click_ctx)
    try:
        bucket_cfg = cfg.get_bucket(bucket)
        storage = _get_storage(bucket_cfg)
        storage.delete(bucket, remote_path)
        click.echo(f"Deleted {bucket}/{remote_path}")
    except Exception as exc:
        sys.exit(_handle_exc(exc))


if __name__ == "__main__":
    cli()
