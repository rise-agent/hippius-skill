"""Tests for hippius_skill.crypto.

We verify:
- Round-trip encrypt / decrypt via actual GPG with a temporary keyring.
- Mock GPG binary tests for subprocess-wrapper edge cases.
"""

import os
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import pytest

from hippius_skill.crypto import EncryptionError, GpgEncryptStream, decrypt_stream


# --------------------------------------------------------------------------- #
# Round-trip with live GPG
# --------------------------------------------------------------------------- #


def test_encrypt_decrypt_round_trip() -> None:
    """Encrypt some bytes, decrypt them, assert plaintext matches."""
    passphrase = "super_secret_passphrase_123"
    algorithm = "AES256"
    plaintext = b"The quick brown fox jumps over the lazy dog.\n" * 100

    source = BytesIO(plaintext)
    stream = GpgEncryptStream(passphrase=passphrase, algorithm=algorithm, source_stream=source)

    # Read all ciphertext
    ciphertext = stream.read()
    stream.close()

    assert ciphertext != plaintext
    assert ciphertext.startswith(b"-----BEGIN PGP MESSAGE-----")

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "decrypted.bin"
        ciphertext_stream = BytesIO(ciphertext)
        decrypt_stream(passphrase, algorithm, ciphertext_stream, dest)
        decrypted = dest.read_bytes()

    assert decrypted == plaintext


def test_encrypt_stream_chunked_read() -> None:
    """Read encrypted stream in small chunks."""
    passphrase = "pass123"
    plaintext = b"hello world"
    source = BytesIO(plaintext)
    stream = GpgEncryptStream(passphrase=passphrase, algorithm="AES256", source_stream=source)

    chunks = []
    while True:
        chunk = stream.read(256)
        if not chunk:
            break
        chunks.append(chunk)
    stream.close()

    ciphertext = b"".join(chunks)
    assert ciphertext.startswith(b"-----BEGIN PGP MESSAGE-----")


def test_decrypt_stream_file() -> None:
    """Encrypt to file, then decrypt from file."""
    passphrase = "abc123"
    plaintext = b"some important data" * 500

    with tempfile.TemporaryDirectory() as td:
        encrypted_path = Path(td) / "data.gpg"
        source = BytesIO(plaintext)
        stream = GpgEncryptStream(passphrase=passphrase, algorithm="AES256", source_stream=source)
        encrypted_path.write_bytes(stream.read())
        stream.close()

        decrypted_path = Path(td) / "out.bin"
        with open(encrypted_path, "rb") as fh:
            decrypt_stream(passphrase, "AES256", fh, decrypted_path)

        assert decrypted_path.read_bytes() == plaintext


# --------------------------------------------------------------------------- #
# Mock GPG binary test
# --------------------------------------------------------------------------- #


def test_gpg_encrypt_stream_bad_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """If GPG exits non-zero, close() should raise EncryptionError."""

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStream()
            self.stdout = FakeStream(b"partial")
            self.stderr = FakeStream(b"bad passphrase\n")
            self.returncode = 2

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    class FakeStream:
        def __init__(self, data: bytes = b""):
            self._data = data
            self.closed = False

        def write(self, data):
            pass

        def flush(self):
            pass

        def read(self, size=-1):
            out = self._data
            self._data = b""
            return out

        def close(self):
            self.closed = True

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProc())

    stream = GpgEncryptStream("pw", "AES256", BytesIO(b"data"))
    stream.read()
    with pytest.raises(EncryptionError, match="bad passphrase"):
        stream.close()
