"""Tests for hippius_skill.cli.

Uses click.testing.CliRunner and mocks all underlying modules."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hippius_skill.cli import cli
from hippius_skill.config import BucketNotFoundError, ConfigError


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mock_config():
    with patch("hippius_skill.cli.Config") as m:
        instance = MagicMock()
        m.return_value = instance
        yield instance


@pytest.fixture
def mock_hippius_client():
    with patch("hippius_skill.cli.HippiusClient") as m:
        instance = MagicMock()
        m.return_value = instance
        yield instance


@pytest.fixture
def mock_storage():
    with patch("hippius_skill.cli.Storage") as m:
        instance = MagicMock()
        m.return_value = instance
        yield instance


# --------------------------------------------------------------------------- #
# Config commands
# --------------------------------------------------------------------------- #


def test_config_init(runner: CliRunner, mock_config: MagicMock) -> None:
    result = runner.invoke(cli, ["config", "init", "--master-token", "abc123"])
    assert result.exit_code == 0
    mock_config.set_master_token.assert_called_once_with("abc123")
    assert "stored" in result.output.lower()


def test_config_add_bucket(runner: CliRunner, mock_config: MagicMock, mock_hippius_client: MagicMock) -> None:
    mock_hippius_client.create_sub_token.return_value = {
        "id": "stok_789",
        "accessKeyId": "ak123",
        "secret": "sk456",
    }
    result = runner.invoke(cli, ["config", "add-bucket", "photos"])
    assert result.exit_code == 0
    mock_hippius_client.create_bucket.assert_called_once_with("photos")
    mock_hippius_client.create_sub_token.assert_called_once_with(
        "photos", scope_type="single_bucket", bucket_names=["photos"], actions=["read", "write"]
    )
    mock_config.add_bucket.assert_called_once_with(
        "photos", "AES256", access_key="ak123", secret_key="sk456", token_id="stok_789"
    )


def test_config_list_buckets(runner: CliRunner, mock_config: MagicMock) -> None:
    mock_config.list_buckets.return_value = ["alpha", "beta"]
    result = runner.invoke(cli, ["config", "list-buckets"])
    assert result.exit_code == 0
    assert "alpha\nbeta\n" in result.output


def test_config_completion_bash(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "completion", "bash"])
    assert result.exit_code == 0
    assert "_hippius_skill_completion" in result.output


def test_config_completion_fish(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "completion", "fish"])
    assert result.exit_code == 0
    assert "_hippius_skill_completion" in result.output


def test_config_completion_zsh(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "completion", "zsh"])
    assert result.exit_code == 0
    assert "_hippius_skill_completion" in result.output


def test_config_completion_invalid_shell(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["config", "completion", "invalid"])
    assert result.exit_code != 0
    assert "Invalid value" in result.output


def test_config_remove_bucket(
    runner: CliRunner,
    mock_config: MagicMock,
    mock_hippius_client: MagicMock,
    mock_storage: MagicMock,
) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    bucket_cfg.token_id = "stok_123"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.list_files.return_value = ["a.txt", "b/c.txt"]

    result = runner.invoke(cli, ["config", "remove-bucket", "old"])
    assert result.exit_code == 0
    mock_storage.list_files.assert_called_once_with("old")
    assert mock_storage.delete.call_count == 2
    mock_hippius_client.delete_bucket.assert_called_once_with("old")
    mock_hippius_client.revoke_sub_token.assert_called_once_with("stok_123")
    mock_config.remove_bucket.assert_called_once_with("old")


def test_config_remove_bucket_not_found_in_config(
    runner: CliRunner, mock_config: MagicMock
) -> None:
    mock_config.get_bucket.side_effect = BucketNotFoundError("nope")
    result = runner.invoke(cli, ["config", "remove-bucket", "missing"])
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_config_remove_bucket_api_404(
    runner: CliRunner,
    mock_config: MagicMock,
    mock_hippius_client: MagicMock,
    mock_storage: MagicMock,
) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    bucket_cfg.token_id = "stok_123"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.list_files.return_value = []
    from hippius_skill.hippius_client import HippiusClientError

    mock_hippius_client.delete_bucket.side_effect = HippiusClientError("not found", status_code=404)
    mock_hippius_client.revoke_sub_token.side_effect = HippiusClientError(
        "not found", status_code=404
    )

    result = runner.invoke(cli, ["config", "remove-bucket", "old"])
    assert result.exit_code == 0
    assert "Warning" in result.output
    mock_config.remove_bucket.assert_called_once_with("old")


def test_config_remove_bucket_file_delete_fails(
    runner: CliRunner,
    mock_config: MagicMock,
    mock_hippius_client: MagicMock,
    mock_storage: MagicMock,
) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    bucket_cfg.token_id = "stok_123"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.list_files.return_value = ["a.txt"]
    from hippius_skill.storage import StorageError

    mock_storage.delete.side_effect = StorageError("network down")

    result = runner.invoke(cli, ["config", "remove-bucket", "old"])
    assert result.exit_code == 1
    assert "Failed to delete" in result.output
    mock_config.remove_bucket.assert_not_called()


# --------------------------------------------------------------------------- #
# Upload / Download / List / Delete
# --------------------------------------------------------------------------- #


def test_upload(runner: CliRunner, mock_config: MagicMock, mock_storage: MagicMock, tmp_path: Path) -> None:
    local_file = tmp_path / "data.txt"
    local_file.write_text("hello world")

    bucket_cfg = MagicMock()
    bucket_cfg.passphrase = "pw"
    bucket_cfg.algorithm = "AES256"
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.upload.return_value = {"checksum": "sha256-abc"}

    with patch("hippius_skill.cli.GpgEncryptStream") as MockStream:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        MockStream.return_value = instance

        result = runner.invoke(
            cli, ["upload", "mybucket", str(local_file), "data.txt"]
        )

    assert result.exit_code == 0
    mock_storage.upload.assert_called_once()


def test_download(runner: CliRunner, mock_config: MagicMock, mock_storage: MagicMock, tmp_path: Path) -> None:
    out_file = tmp_path / "output.bin"

    bucket_cfg = MagicMock()
    bucket_cfg.passphrase = "pw"
    bucket_cfg.algorithm = "AES256"
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    mock_config.get_bucket.return_value = bucket_cfg

    mock_body = MagicMock()
    mock_body.read.return_value = b"encrypted-data"
    mock_storage.download.return_value = mock_body

    with patch("hippius_skill.cli.decrypt_stream") as mock_decrypt:
        result = runner.invoke(
            cli, ["download", "mybucket", "remote/file.txt", str(out_file)]
        )

    assert result.exit_code == 0
    mock_storage.download.assert_called_once_with("mybucket", "remote/file.txt")
    mock_decrypt.assert_called_once()
    mock_body.close.assert_called_once()


def test_list_files(runner: CliRunner, mock_config: MagicMock, mock_storage: MagicMock) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.list_files.return_value = ["a.txt", "b/c.txt"]

    result = runner.invoke(cli, ["list", "mybucket"])
    assert result.exit_code == 0
    assert "a.txt\n" in result.output
    assert "b/c.txt\n" in result.output


def test_list_files_with_prefix(runner: CliRunner, mock_config: MagicMock, mock_storage: MagicMock) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    mock_config.get_bucket.return_value = bucket_cfg
    mock_storage.list_files.return_value = ["b/c.txt"]

    result = runner.invoke(cli, ["list", "mybucket", "--prefix", "b/"])
    assert result.exit_code == 0
    mock_storage.list_files.assert_called_once_with("mybucket", prefix="b/")


def test_delete(runner: CliRunner, mock_config: MagicMock, mock_storage: MagicMock) -> None:
    bucket_cfg = MagicMock()
    bucket_cfg.access_key = "ak"
    bucket_cfg.secret_key = "sk"
    mock_config.get_bucket.return_value = bucket_cfg

    result = runner.invoke(cli, ["delete", "mybucket", "file.txt"])
    assert result.exit_code == 0
    mock_storage.delete.assert_called_once_with("mybucket", "file.txt")


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #


def test_bucket_not_found(runner: CliRunner, mock_config: MagicMock) -> None:
    mock_config.get_bucket.side_effect = BucketNotFoundError("no such bucket")
    result = runner.invoke(cli, ["list", "missing"])
    assert result.exit_code == 2
    assert "Configuration error" in result.output


def test_config_error(runner: CliRunner, mock_config: MagicMock) -> None:
    mock_config.get_bucket.side_effect = ConfigError("bad config")
    result = runner.invoke(cli, ["list", "b"])
    assert result.exit_code == 2
    assert "Configuration error" in result.output


def test_custom_config_option(runner: CliRunner, mock_config: MagicMock) -> None:
    custom_path = Path("/tmp/custom_config.ini")
    result = runner.invoke(cli, ["--config", str(custom_path), "config", "list-buckets"])
    assert result.exit_code == 0
    # Config constructor is patched, but the option was passed correctly
