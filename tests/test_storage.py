"""Tests for hippius_skill.storage."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from hippius_skill.storage import FileNotFoundError, Storage, StorageError


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_boto3():
    with patch("hippius_skill.storage.boto3.client") as mock:
        fake_client = MagicMock()
        mock.return_value = fake_client
        yield fake_client


@pytest.fixture
def storage(mock_boto3) -> Storage:
    return Storage(
        endpoint="https://s3.hippius.com",
        access_key="access123",
        secret_key="secret456",
    )


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def test_upload(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_boto3.put_object.return_value = {
        "ChecksumSHA256": "abc123",
        "ETag": '"etag123"',
    }

    result = storage.upload("bucket1", "file.txt", b"hello")

    assert result == {"checksum": "abc123", "etag": "etag123"}
    mock_boto3.put_object.assert_called_once_with(
        Bucket="bucket1",
        Key="file.txt",
        Body=b"hello",
        ChecksumAlgorithm="SHA256",
    )


def test_upload_error(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_boto3.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}},
        "PutObject",
    )
    with pytest.raises(StorageError, match="Upload failed"):
        storage.upload("b", "k", b"d")


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #


def test_download(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_stream = MagicMock()
    mock_boto3.get_object.return_value = {"Body": mock_stream}

    body = storage.download("bucket1", "file.txt")

    assert body is mock_stream
    mock_boto3.get_object.assert_called_once_with(
        Bucket="bucket1",
        Key="file.txt",
        ChecksumMode="ENABLED",
    )


def test_download_not_found(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_boto3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
        "GetObject",
    )
    with pytest.raises(FileNotFoundError, match="not found"):
        storage.download("b", "k")


# --------------------------------------------------------------------------- #
# List / Delete
# --------------------------------------------------------------------------- #


def test_list_files(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_boto3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "b/c.txt"},
        ],
        "IsTruncated": False,
    }

    keys = storage.list_files("bucket1", prefix="b/")
    assert keys == ["b/c.txt"]
    # Verify prefix was passed
    call_kwargs = mock_boto3.list_objects_v2.call_args[1]
    assert call_kwargs["Prefix"] == "b/"


def test_list_files_paginated(mock_boto3: MagicMock, storage: Storage) -> None:
    mock_boto3.list_objects_v2.side_effect = [
        {
            "Contents": [{"Key": "1.txt"}],
            "IsTruncated": True,
            "NextContinuationToken": "tok1",
        },
        {
            "Contents": [{"Key": "2.txt"}],
            "IsTruncated": False,
        },
    ]

    keys = storage.list_files("bucket1")
    assert keys == ["1.txt", "2.txt"]
    assert mock_boto3.list_objects_v2.call_count == 2


def test_delete(mock_boto3: MagicMock, storage: Storage) -> None:
    storage.delete("bucket1", "old.txt")
    mock_boto3.delete_object.assert_called_once_with(
        Bucket="bucket1",
        Key="old.txt",
    )
