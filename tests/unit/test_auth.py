"""Unit tests for the OAuth Resource Server token verifier.

The HTTP layer is stubbed so these run offline: an explicit ``introspection_url``
skips discovery, and ``_client`` is replaced with a fake whose ``post`` returns a
canned response.
"""

import time

import pytest

from postgres_mcp.auth import MoebliAccessToken
from postgres_mcp.auth import MoebliIntrospectionVerifier

RESOURCE = "https://mcp.example/mcp/postgres"


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict):
        self.status_code = status_code
        self._json = json_body

    def json(self) -> dict:
        return self._json


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.post_calls = 0

    async def post(self, url, data=None, headers=None):  # noqa: ANN001
        self.post_calls += 1
        return self._response


def _make_verifier(response: _FakeResponse, **kwargs) -> tuple[MoebliIntrospectionVerifier, _FakeClient]:
    verifier = MoebliIntrospectionVerifier(
        issuer="https://as.example",
        resource=RESOURCE,
        client_id="rs",
        client_secret="secret",
        introspection_url="https://as.example/introspect",
        **kwargs,
    )
    fake = _FakeClient(response)
    verifier._client = lambda: fake  # type: ignore[method-assign]
    return verifier, fake


@pytest.mark.asyncio
async def test_inactive_token_rejected():
    verifier, _ = _make_verifier(_FakeResponse(200, {"active": False}))
    assert await verifier.verify_token("tok") is None


@pytest.mark.asyncio
async def test_non_200_rejected():
    verifier, _ = _make_verifier(_FakeResponse(503, {}))
    assert await verifier.verify_token("tok") is None


@pytest.mark.asyncio
async def test_audience_mismatch_rejected():
    verifier, _ = _make_verifier(_FakeResponse(200, {"active": True, "aud": "https://other/mcp"}))
    assert await verifier.verify_token("tok") is None


@pytest.mark.asyncio
async def test_valid_token_without_pin():
    body = {
        "active": True,
        "aud": RESOURCE,
        "account_id": "acct-1",
        "sub": "user-9",
        "client_id": "cli",
        "scope": "read write",
        "exp": int(time.time()) + 3600,
    }
    verifier, _ = _make_verifier(_FakeResponse(200, body))

    token = await verifier.verify_token("tok")

    assert isinstance(token, MoebliAccessToken)
    assert token.account_id == "acct-1"
    assert token.sub == "user-9"
    assert token.client_id == "cli"
    assert token.scopes == ["read", "write"]
    assert token.resource == RESOURCE


@pytest.mark.asyncio
async def test_account_pin_match_allows():
    body = {"active": True, "aud": RESOURCE, "account_id": "acct-1"}
    verifier, _ = _make_verifier(_FakeResponse(200, body), expected_account_id="acct-1")

    token = await verifier.verify_token("tok")

    assert token is not None
    assert token.account_id == "acct-1"


@pytest.mark.asyncio
async def test_account_pin_mismatch_rejected():
    body = {"active": True, "aud": RESOURCE, "account_id": "acct-2"}
    verifier, _ = _make_verifier(_FakeResponse(200, body), expected_account_id="acct-1")
    assert await verifier.verify_token("tok") is None


@pytest.mark.asyncio
async def test_account_pin_missing_account_rejected():
    body = {"active": True, "aud": RESOURCE}
    verifier, _ = _make_verifier(_FakeResponse(200, body), expected_account_id="acct-1")
    assert await verifier.verify_token("tok") is None


@pytest.mark.asyncio
async def test_result_is_cached():
    body = {"active": True, "aud": RESOURCE, "account_id": "acct-1", "exp": int(time.time()) + 3600}
    verifier, fake = _make_verifier(_FakeResponse(200, body))

    first = await verifier.verify_token("tok")
    second = await verifier.verify_token("tok")

    assert first is second
    assert fake.post_calls == 1
