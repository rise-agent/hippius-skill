"""REST API client for the Hippius platform.

Handles:
- Bucket creation / deletion / listing
- Sub-token creation / revocation
"""

import httpx


class HippiusClientError(Exception):
    """Base exception for Hippius REST API errors."""

    pass


class HippiusClient:
    def __init__(self, api_token: str, base_url: str | None = None):
        self.api_token = api_token
        self.base_url = (base_url or "https://api.hippius.com").rstrip("/")
        self._headers = {"Authorization": f"Token {api_token}", "Content-Type": "application/json"}

    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        response = httpx.request(method, url, headers=self._headers, timeout=30.0, **kwargs)
        if response.status_code >= 400:
            raise HippiusClientError(
                f"Hippius API error {response.status_code}: {response.text}"
            )
        return response

    # ------------------------------------------------------------------ #
    # Buckets
    # ------------------------------------------------------------------ #

    def create_bucket(self, name: str) -> None:
        self._request("POST", "/api/objectstore/buckets/", json={"name": name})

    def delete_bucket(self, name: str) -> None:
        self._request("DELETE", f"/api/objectstore/buckets/{name}/")

    def list_buckets(self) -> list[str]:
        resp = self._request("GET", "/api/objectstore/buckets/")
        data = resp.json()
        # Hippius API returns {"buckets": [...], "count": ...}
        buckets = data.get("buckets", []) if isinstance(data, dict) else data
        names = []
        for b in buckets:
            if isinstance(b, dict):
                names.append(b.get("bucket_name") or b.get("name", ""))
            else:
                names.append(str(b))
        return names

    # ------------------------------------------------------------------ #
    # Sub-tokens
    # ------------------------------------------------------------------ #

    def create_sub_token(
        self,
        name: str,
        scope_type: str = "single_bucket",
        bucket_names: list[str] | None = None,
        actions: list[str] | None = None,
    ) -> dict:
        payload: dict = {
            "name": name,
            "scope_type": scope_type,
        }
        if bucket_names is not None:
            payload["bucket_names"] = bucket_names
        if actions is not None:
            payload["actions"] = actions
        resp = self._request("POST", "/api/objectstore/sub-tokens/", json=payload)
        return resp.json()

    def revoke_sub_token(self, token_id: str) -> None:
        self._request("POST", f"/api/objectstore/sub-tokens/{token_id}/revoke/")
