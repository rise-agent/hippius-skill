"""Tests for hippius_skill.config."""

import os
import stat
from configparser import ConfigParser
from pathlib import Path

import pytest

from hippius_skill.config import BucketNotFoundError, Config, ConfigError


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg_path = tmp_path / "config.ini"
    return Config(path=cfg_path)


# --------------------------------------------------------------------------- #
# Master token
# --------------------------------------------------------------------------- #


def test_master_token_round_trip(config: Config) -> None:
    config.set_master_token("tk_12345")
    assert config.get_master_token() == "tk_12345"


def test_get_master_token_missing(config: Config) -> None:
    with pytest.raises(ConfigError, match="Master token not configured"):
        config.get_master_token()


# --------------------------------------------------------------------------- #
# Bucket CRUD
# --------------------------------------------------------------------------- #


def test_add_bucket_generates_passphrase(config: Config) -> None:
    bc = config.add_bucket("photos", "AES256")
    assert bc.name == "photos"
    assert bc.algorithm == "AES256"
    assert len(bc.passphrase) >= 32
    assert bc.access_key == ""
    assert bc.secret_key == ""
    assert bc.token_id == ""


def test_add_bucket_with_token_id(config: Config) -> None:
    bc = config.add_bucket("videos", token_id="tok_abc")
    assert bc.token_id == "tok_abc"


def test_add_bucket_duplicate(config: Config) -> None:
    config.add_bucket("photos")
    with pytest.raises(ConfigError, match="already exists"):
        config.add_bucket("photos")


def test_get_bucket(config: Config) -> None:
    config.add_bucket("photos", access_key="ak", secret_key="sk", token_id="tok123")
    bc = config.get_bucket("photos")
    assert bc.name == "photos"
    assert bc.access_key == "ak"
    assert bc.secret_key == "sk"
    assert bc.token_id == "tok123"


def test_get_bucket_not_found(config: Config) -> None:
    with pytest.raises(BucketNotFoundError, match="Bucket 'missing' not found"):
        config.get_bucket("missing")


def test_get_bucket_suggestion(config: Config) -> None:
    config.add_bucket("backups")
    with pytest.raises(BucketNotFoundError, match="Did you mean 'backups'"):
        config.get_bucket("backup")


def test_list_buckets(config: Config) -> None:
    config.add_bucket("a")
    config.add_bucket("b")
    assert sorted(config.list_buckets()) == ["a", "b"]


def test_remove_bucket(config: Config) -> None:
    config.add_bucket("old")
    config.remove_bucket("old")
    assert config.list_buckets() == []
    with pytest.raises(BucketNotFoundError):
        config.get_bucket("old")


def test_update_bucket_credentials(config: Config) -> None:
    config.add_bucket("pictures", access_key="old_ak", secret_key="old_sk")
    config.update_bucket_credentials("pictures", access_key="new_ak", secret_key="new_sk")
    bc = config.get_bucket("pictures")
    assert bc.access_key == "new_ak"
    assert bc.secret_key == "new_sk"


# --------------------------------------------------------------------------- #
# File permissions
# --------------------------------------------------------------------------- #


def test_config_permissions(config: Config) -> None:
    config.set_master_token("x")
    mode = stat.S_IMODE(config._path.stat().st_mode)
    assert mode == 0o600


# --------------------------------------------------------------------------- #
# App defaults
# --------------------------------------------------------------------------- #


def test_app_defaults() -> None:
    defaults = Config.get_app_defaults()
    assert defaults.get("hippius", "api_url") == "https://api.hippius.com"
    assert defaults.get("hippius", "s3_endpoint") == "https://s3.hippius.com"
    assert defaults.get("hippius", "region") == "decentralized"


# --------------------------------------------------------------------------- #
# Config path discovery
# --------------------------------------------------------------------------- #


def test_find_config_walks_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hippius_skill.config as config_mod

    custom_dir = tmp_path / "projects" / "foo"
    custom_dir.mkdir(parents=True)
    config_path = custom_dir / ".hippius-skill" / "config.ini"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("[hippius]\napi_token = abc\n", encoding="utf-8")

    sub = custom_dir / "sub"
    sub.mkdir(exist_ok=True)
    monkeypatch.chdir(sub)

    found = config_mod._find_config()
    assert found == config_path


def test_find_config_fallback_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hippius_skill.config as config_mod

    user_cfg = tmp_path / ".hippius-skill" / "config.ini"
    user_cfg.parent.mkdir(parents=True)
    user_cfg.write_text("[hippius]\napi_token = xyz\n", encoding="utf-8")

    # Monkeypatch the module-level helper to use tmp_path as "home"
    monkeypatch.setattr(config_mod, "_user_config", lambda: user_cfg)
    monkeypatch.setattr(config_mod, "_user_dir", lambda: user_cfg.parent)

    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)

    found = config_mod._find_config()
    assert found == user_cfg
