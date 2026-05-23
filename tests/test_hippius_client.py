"""Tests for hippius_skill.hippius_client."""

import json

import httpx
import pytest
from pytest import MonkeyPatch

from hippius_skill.hippius_client import HippiusClient, HippiusClientError


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_response(status_code: int = 200, json_data=None, text: str = "") -> httpx.Response:
    if json_data is not None:
        content = json.dumps(json_data).encode("utf-8")
        headers = {"content-type": "application/json"}
    else:
        content = text.encode("utf-8")
        headers = {}
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers,
        request=httpx.Request("GET", "http://test"),
    )


# --------------------------------------------------------------------------- #
# Bucket operations
# --------------------------------------------------------------------------- #


def test_create_bucket(monkeypatch: MonkeyPatch) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _make_response(201)

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    client.create_bucket("my-bucket")

    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][1] == "https://api.hippius.com/api/objectstore/buckets/"
    assert calls[0][2]["json"] == {"name": "my-bucket"}
    assert calls[0][2]["headers"]["Authorization"] == "Token token123"


def test_delete_bucket(monkeypatch: MonkeyPatch) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return _make_response(204)

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123", base_url="https://api.example.com")
    client.delete_bucket("old-bucket")

    assert calls == [("DELETE", "https://api.example.com/api/objectstore/buckets/old-bucket/")]


def test_list_buckets(monkeypatch: MonkeyPatch) -> None:
    def fake_request(method, url, **kwargs):
        return _make_response(
            200,
            json_data=[{"name": "alpha"}, {"name": "beta"}],
        )

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    buckets = client.list_buckets()
    assert buckets == ["alpha", "beta"]


def test_list_buckets_plain_list(monkeypatch: MonkeyPatch) -> None:
    def fake_request(method, url, **kwargs):
        return _make_response(
            200,
            json_data=[{"name": "one"}, {"name": "two"}],
        )

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    buckets = client.list_buckets()
    assert buckets == ["one", "two"]


# --------------------------------------------------------------------------- #
# Sub-token operations
# --------------------------------------------------------------------------- #


def test_create_sub_token(monkeypatch: MonkeyPatch) -> None:
    def fake_request(method, url, **kwargs):
        return _make_response(
            201,
            json_data={
                "id": "stok_123",
                "accessKeyId": "ACCESS123",
                "secret": "SECRET456",
            },
        )

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    result = client.create_sub_token("my-token", scope_type="single_bucket", bucket_names=["b1"])

    assert result["accessKeyId"] == "ACCESS123"
    assert result["secret"] == "SECRET456"


def test_revoke_sub_token(monkeypatch: MonkeyPatch) -> None:
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return _make_response(204)

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    client.revoke_sub_token("stok_123")

    assert calls == [("POST", "https://api.hippius.com/api/objectstore/sub-tokens/stok_123/revoke/")]


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #


def test_api_error_raises(monkeypatch: MonkeyPatch) -> None:
    def fake_request(method, url, **kwargs):
        return _make_response(400, text='{"error": "bad request"}')

    monkeypatch.setattr(httpx, "request", fake_request)

    client = HippiusClient("token123")
    with pytest.raises(HippiusClientError, match="Hippius API error 400"):
        client.create_bucket("fail")
