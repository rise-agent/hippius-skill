"""Encryption / decryption backed by GPG symmetric mode.

Provides streaming encryption as a file-like object suitable for
boto3::put_object(Body=...) and a standalone streaming decryption
function that writes to a file path.
"""

import queue
import subprocess
import sys
import threading
import warnings
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

warnings.filterwarnings("ignore", category=DeprecationWarning)


class EncryptionError(Exception):
    """Raised when GPG reports an error on stderr."""

    pass


def _gpg_encrypt_cmd(algorithm: str) -> list[str]:
    return [
        "gpg",
        "--symmetric",
        "--cipher-algo",
        algorithm,
        "--passphrase-fd",
        "0",
        "--batch",
        "--no-tty",
        "--yes",
        "--armor",
        "--pinentry-mode",
        "loopback",
        "-o",
        "-",
    ]


def _gpg_decrypt_cmd(algorithm: str) -> list[str]:
    return [
        "gpg",
        "--decrypt",
        "--cipher-algo",
        algorithm,
        "--passphrase-fd",
        "0",
        "--batch",
        "--no-tty",
        "--yes",
        "--pinentry-mode",
        "loopback",
        "-o",
        "-",
    ]


class GpgEncryptStream:
    """File-like streamer that feeds *source_stream* through GPG symmetric encryption.

    Suitable as ``Body=`` argument for ``boto3.client('s3').put_object()``.
    """

    _CHUNK = 64 * 1024  # 64 KiB

    def __init__(self, passphrase: str, algorithm: str, source_stream: BinaryIO):
        self._passphrase = passphrase
        self._algorithm = algorithm
        self._source = source_stream
        self._proc: subprocess.Popen | None = None
        self._feeder: threading.Thread | None = None
        self._stderr_queue: queue.Queue[str] = queue.Queue()
        self._started = False
        self._closed = False
        self._read_error: Exception | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def _start(self) -> None:
        if self._started:
            return
        self._proc = subprocess.Popen(
            _gpg_encrypt_cmd(self._algorithm),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Write passphrase to GPG stdin first, then feed source in thread
        assert self._proc.stdin is not None
        self._proc.stdin.write((self._passphrase + "\n").encode())
        self._proc.stdin.flush()

        self._feeder = threading.Thread(target=self._feed_stdin, daemon=True)
        self._feeder.start()

        # stderr collector thread
        threading.Thread(target=self._collect_stderr, daemon=True).start()
        self._started = True

    def _feed_stdin(self) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None
        try:
            while True:
                chunk = self._source.read(self._CHUNK)
                if not chunk:
                    break
                self._proc.stdin.write(chunk)
        except Exception as exc:
            self._read_error = exc
        finally:
            try:
                self._proc.stdin.close()
            except Exception:
                pass

    def _collect_stderr(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None
        try:
            stderr_data = self._proc.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            return
        if stderr_data.strip():
            self._stderr_queue.put(stderr_data.strip())

    # ------------------------------------------------------------------ #
    # File-like interface
    # ------------------------------------------------------------------ #

    def read(self, size: int = -1) -> bytes:
        if self._closed:
            return b""
        self._start()
        assert self._proc is not None
        assert self._proc.stdout is not None
        if size == -1:
            return self._proc.stdout.read()
        return self._proc.stdout.read(size)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._feeder is not None:
            self._feeder.join(timeout=5.0)

        if self._proc is not None:
            try:
                if self._proc.stdin and not self._proc.stdin.closed:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                if self._proc.stdout and not self._proc.stdout.closed:
                    self._proc.stdout.close()
            except Exception:
                pass
            ret = self._proc.wait(timeout=10)
            if ret != 0:
                try:
                    err = self._stderr_queue.get_nowait()
                except queue.Empty:
                    err = f"gpg exited with code {ret}"
                raise EncryptionError(err)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def decrypt_stream(
    passphrase: str,
    algorithm: str,
    ciphertext_stream: BinaryIO,
    destination_path: Path,
) -> None:
    """Decrypt *ciphertext_stream* with GPG and write plaintext to *destination_path*."""
    proc = subprocess.Popen(
        _gpg_decrypt_cmd(algorithm),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Write passphrase first
    assert proc.stdin is not None
    proc.stdin.write((passphrase + "\n").encode())
    proc.stdin.flush()

    feeder_thread = threading.Thread(
        target=_feed_chunks,
        args=(proc.stdin, ciphertext_stream),
        daemon=True,
    )
    feeder_thread.start()

    with open(destination_path, "wb") as fh:
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            fh.write(chunk)

    feeder_thread.join(timeout=5.0)
    ret = proc.wait(timeout=10)

    stderr_data = proc.stderr.read().decode("utf-8", errors="replace").strip() if proc.stderr else ""
    if ret != 0:
        raise EncryptionError(stderr_data or f"gpg exited with code {ret}")


def _feed_chunks(stdin: BinaryIO, source: BinaryIO) -> None:
    try:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            stdin.write(chunk)
    finally:
        try:
            stdin.close()
        except Exception:
            pass
