"""S3-compatible storage client wrapper around boto3.

Each bucket is addressed with credentials from a Hippius Sub Token.
"""

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


class StorageError(Exception):
    """Base exception for storage operation errors."""

    pass


class IntegrityError(StorageError):
    """Raised when a checksum does not match."""

    pass


class FileNotFoundError(StorageError):
    """Raised when a requested file does not exist in the bucket."""

    pass


class Storage:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "decentralized",
        signature_version: str = "s3v4",
        addressing_style: str = "path",
    ):
        boto_config = BotoConfig(
            signature_version=signature_version,
            s3={"addressing_style": addressing_style},
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=boto_config,
        )

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #

    def upload(self, bucket: str, key: str, data) -> dict:
        """Upload *data* (file-like or bytes) to *bucket*/*key*.

        Returns a dict with ``checksum`` and ``etag``.
        """
        try:
            response = self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ChecksumAlgorithm="SHA256",
            )
        except ClientError as exc:
            raise StorageError(f"Upload failed: {exc}") from exc

        checksum = response.get("ChecksumSHA256", "")
        etag = response.get("ETag", "").strip('"')
        return {"checksum": checksum, "etag": etag}

    # ------------------------------------------------------------------ #
    # Download
    # ------------------------------------------------------------------ #

    def download(self, bucket: str, key: str):
        """Download *key* from *bucket*.

        Returns a boto3 StreamingBody (file-like object). The caller is
        responsible for closing the stream.
        """
        try:
            response = self._client.get_object(
                Bucket=bucket,
                Key=key,
                ChecksumMode="ENABLED",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError(f"File '{key}' not found in bucket '{bucket}'") from exc
            raise StorageError(f"Download failed: {exc}") from exc
        return response["Body"]

    # ------------------------------------------------------------------ #
    # List / Delete
    # ------------------------------------------------------------------ #

    def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        """Return a list of file keys in *bucket* matching *prefix*."""
        keys = []
        kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
        try:
            while True:
                response = self._client.list_objects_v2(**kwargs)
                for obj in response.get("Contents", []):
                    keys.append(obj["Key"])
                if not response.get("IsTruncated"):
                    break
                kwargs["ContinuationToken"] = response["NextContinuationToken"]
        except ClientError as exc:
            raise StorageError(f"List failed: {exc}") from exc
        return keys

    def delete(self, bucket: str, key: str) -> None:
        """Delete *key* from *bucket*."""
        try:
            self._client.delete_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            raise StorageError(f"Delete failed: {exc}") from exc
