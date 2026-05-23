"""Configuration management for hippius-skill.

Handles split config model:
- app.ini (shipped with package): global defaults, read-only
- ~/.hippius-skill/config.ini: user data, read/write, chmod 600
"""

import difflib
import os
import secrets
import stat
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

_APP_INI = Path(__file__).with_name("app.ini")

# Permissions to enforce on user config file
_CONFIG_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def _user_dir() -> Path:
    return Path.home() / ".hippius-skill"


def _user_config() -> Path:
    return _user_dir() / "config.ini"


def _ensure_user_dir() -> None:
    _user_dir().mkdir(parents=True, exist_ok=True)


def _chmod_600(path: Path) -> None:
    os.chmod(path, _CONFIG_MODE)


def _find_config(start: Path | None = None) -> Path | None:
    """Search upward from *start* (default: cwd) for config.ini.

    Returns None if not found.
    """
    if start is None:
        start = Path.cwd()
    current = start.resolve()
    for path in [current] + list(current.parents):
        candidate = path / ".hippius-skill" / "config.ini"
        if candidate.is_file():
            return candidate
    default = _user_config()
    if default.is_file():
        return default
    return None


class ConfigError(Exception):
    """Base exception for configuration errors."""

    pass


class BucketNotFoundError(ConfigError):
    """Raised when a requested bucket does not exist in config."""

    pass


@dataclass
class BucketConfig:
    name: str
    algorithm: str
    passphrase: str
    access_key: str
    secret_key: str
    token_id: str


class Config:
    """User configuration backed by an INI file."""

    def __init__(self, path: Path | None = None):
        if path is not None:
            self._path = path
        else:
            found = _find_config()
            if found:
                self._path = found
            else:
                self._path = _user_config()
        self._parser = ConfigParser()
        if self._path.exists():
            self._parser.read(self._path, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    def _save(self) -> None:
        _ensure_user_dir()
        with open(self._path, "w", encoding="utf-8") as fh:
            self._parser.write(fh)
        _chmod_600(self._path)

    @staticmethod
    def _bucket_section(name: str) -> str:
        return f"bucket:{name}"

    # ------------------------------------------------------------------ #
    # master token
    # ------------------------------------------------------------------ #

    def get_master_token(self) -> str:
        try:
            return self._parser.get("hippius", "api_token")
        except Exception as exc:
            raise ConfigError("Master token not configured. Run 'config init' first.") from exc

    def set_master_token(self, token: str) -> None:
        if not self._parser.has_section("hippius"):
            self._parser.add_section("hippius")
        self._parser.set("hippius", "api_token", token)
        self._save()

    # ------------------------------------------------------------------ #
    # bucket CRUD
    # ------------------------------------------------------------------ #

    def _get_bucket_names(self) -> list[str]:
        return [s[len("bucket:") :] for s in self._parser.sections() if s.startswith("bucket:")]

    def _suggest_bucket(self, name: str) -> str | None:
        names = self._get_bucket_names()
        if not names:
            return None
        matches = difflib.get_close_matches(name, names, n=1, cutoff=0.5)
        return matches[0] if matches else None

    def get_bucket(self, name: str) -> BucketConfig:
        section = self._bucket_section(name)
        if not self._parser.has_section(section):
            suggestion = self._suggest_bucket(name)
            msg = f"Bucket '{name}' not found."
            if suggestion:
                msg += f" Did you mean '{suggestion}'?"
            raise BucketNotFoundError(msg)
        return BucketConfig(
            name=name,
            algorithm=self._parser.get(section, "algorithm"),
            passphrase=self._parser.get(section, "passphrase"),
            access_key=self._parser.get(section, "access_key"),
            secret_key=self._parser.get(section, "secret_key"),
            token_id=self._parser.get(section, "token_id", fallback=""),
        )

    def add_bucket(
        self,
        name: str,
        algorithm: str = "AES256",
        /,
        access_key: str = "",
        secret_key: str = "",
        token_id: str = "",
    ) -> BucketConfig:
        section = self._bucket_section(name)
        if self._parser.has_section(section):
            raise ConfigError(f"Bucket '{name}' already exists.")
        self._parser.add_section(section)
        passphrase = secrets.token_urlsafe(32)
        self._parser.set(section, "algorithm", algorithm)
        self._parser.set(section, "passphrase", passphrase)
        self._parser.set(section, "access_key", access_key)
        self._parser.set(section, "secret_key", secret_key)
        self._parser.set(section, "token_id", token_id)
        self._save()
        return BucketConfig(
            name=name,
            algorithm=algorithm,
            passphrase=passphrase,
            access_key=access_key,
            secret_key=secret_key,
            token_id=token_id,
        )

    def update_bucket_credentials(self, name: str, access_key: str, secret_key: str) -> None:
        section = self._bucket_section(name)
        if not self._parser.has_section(section):
            raise BucketNotFoundError(f"Bucket '{name}' not found.")
        self._parser.set(section, "access_key", access_key)
        self._parser.set(section, "secret_key", secret_key)
        self._save()

    def list_buckets(self) -> list[str]:
        return self._get_bucket_names()

    def remove_bucket(self, name: str) -> None:
        section = self._bucket_section(name)
        if self._parser.has_section(section):
            self._parser.remove_section(section)
            self._save()

    # ------------------------------------------------------------------ #
    # app defaults (read-only)
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_app_defaults() -> ConfigParser:
        parser = ConfigParser()
        parser.read(_APP_INI, encoding="utf-8")
        return parser
