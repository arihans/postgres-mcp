"""OAuth 2.1 Resource Server token verification for the HTTP transports.

When ``MCP_AUTH_ENABLED`` is set, the server acts as an OAuth 2.1 Resource Server:
it delegates authentication to an external Authorization Server and validates each
opaque bearer token by calling that server's RFC 7662 introspection endpoint.

``stdio`` and unauthenticated HTTP are unaffected -- ``server.py`` only wires this
in when the environment opts in.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any
from typing import Optional

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

logger = logging.getLogger(__name__)

_DISCOVERY_SUFFIX = "/.well-known/oauth-authorization-server"


class MoebliAccessToken(AccessToken):
    """``AccessToken`` plus the moebli-specific claims from introspection.

    Tools can reach these via :func:`get_principal` (which reads the SDK's
    per-request auth contextvar).
    """

    account_id: Optional[str] = None
    sub: Optional[str] = None


def get_principal() -> Optional[MoebliAccessToken]:
    """Return the validated token (with ``account_id`` / ``sub``) for the current
    request, or ``None`` when unauthenticated / auth disabled."""
    token = get_access_token()
    return token if isinstance(token, MoebliAccessToken) else None


class MoebliIntrospectionVerifier:
    """Validate opaque bearer tokens against an OAuth AS via RFC 7662 introspection.

    Implements the ``mcp`` ``TokenVerifier`` protocol
    (``async def verify_token(self, token) -> AccessToken | None``).
    """

    def __init__(
        self,
        *,
        issuer: str,
        resource: str,
        client_id: str,
        client_secret: str,
        introspection_url: str | None = None,
        cache_ttl: float = 45.0,
        http_timeout: float = 5.0,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._resource = resource
        self._introspection_url = introspection_url
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._cache_ttl = cache_ttl
        self._http_timeout = http_timeout
        self._http: httpx.AsyncClient | None = None
        # token -> (validated token, monotonic expiry)
        self._cache: dict[str, tuple[MoebliAccessToken, float]] = {}

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._http_timeout)
        return self._http

    async def _resolve_introspection_url(self) -> str:
        if self._introspection_url:
            return self._introspection_url
        resp = await self._client().get(self._issuer + _DISCOVERY_SUFFIX)
        resp.raise_for_status()
        url = resp.json().get("introspection_endpoint")
        if not url:
            raise RuntimeError(f"AS metadata at {self._issuer}{_DISCOVERY_SUFFIX} has no introspection_endpoint")
        self._introspection_url = url
        logger.info("discovered introspection_endpoint: %s", url)
        return url

    async def verify_token(self, token: str) -> AccessToken | None:
        now = time.monotonic()
        cached = self._cache.get(token)
        if cached and cached[1] > now:
            return cached[0]

        try:
            url = await self._resolve_introspection_url()
            resp = await self._client().post(
                url,
                data={"token": token},
                headers={"Authorization": f"Basic {self._basic}"},
            )
        except httpx.HTTPError as exc:
            logger.warning("introspection call failed: %s", exc)
            return None

        if resp.status_code != 200:
            logger.warning("introspection returned HTTP %s", resp.status_code)
            return None

        body: dict[str, Any] = resp.json()
        if not body.get("active"):
            return None

        aud = body.get("aud")
        if aud != self._resource:
            logger.warning("token audience %r != expected %r; rejecting", aud, self._resource)
            return None

        exp = body.get("exp")
        validated = MoebliAccessToken(
            token=token,
            client_id=str(body.get("client_id") or ""),
            scopes=_split_scope(body.get("scope")),
            expires_at=exp if isinstance(exp, int) else None,
            resource=aud,
            account_id=body.get("account_id"),
            sub=body.get("sub"),
        )

        ttl = self._cache_ttl
        if isinstance(exp, (int, float)):
            ttl = max(0.0, min(ttl, exp - time.time()))
        self._cache[token] = (validated, now + ttl)
        logger.info(
            "token verified: account_id=%s sub=%s client_id=%s",
            validated.account_id,
            validated.sub,
            validated.client_id,
        )
        return validated


def _split_scope(scope: Any) -> list[str]:
    if isinstance(scope, str) and scope.strip():
        return scope.split()
    return []
