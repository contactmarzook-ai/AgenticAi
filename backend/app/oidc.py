"""Microsoft Entra ID sign-in (OpenID Connect, authorization code flow with PKCE).

The browser is sent to Microsoft, comes back to /api/auth/oidc/callback with a one-time code,
and the server exchanges that code for an ID token which it verifies (signature against
Microsoft's published keys, issuer, audience, tenant, expiry, nonce). The user's role comes from
the existing account or from the Entra app roles / groups in OIDC_ROLE_MAP - never from anything
the browser sends. Platform-admin rights are never granted through sign-in.
"""

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt

from .config import settings
from .rbac import PLATFORM_ADMIN, ROLE_PERMISSIONS

logger = logging.getLogger("agentos.oidc")

STATE_COOKIE = "sd_oidc"
STATE_COOKIE_PATH = "/api/auth/oidc"
_STATE_AUDIENCE = "stardust-oidc-state"


class OIDCError(Exception):
    """Sign-in failed; `code` is a short reason safe to show in the browser URL."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def issuer() -> str:
    return f"{settings.oidc_authority}/{settings.oidc_tenant_id}/v2.0"


_discovery_cache: dict = {"at": 0.0, "doc": None}
_jwks_clients: dict[str, jwt.PyJWKClient] = {}
_lock = threading.Lock()


def discovery() -> dict:
    with _lock:
        if _discovery_cache["doc"] and time.time() - _discovery_cache["at"] < 3600:
            return _discovery_cache["doc"]
    try:
        resp = httpx.get(f"{issuer()}/.well-known/openid-configuration", timeout=10)
        resp.raise_for_status()
        doc = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OIDCError("idp_unavailable", f"Cannot read Entra ID configuration: {exc}") from exc
    if doc.get("issuer") != issuer():
        raise OIDCError("idp_misconfigured", "Discovery issuer does not match the configured tenant")
    with _lock:
        _discovery_cache.update(at=time.time(), doc=doc)
    return doc


def signing_key(id_token: str):
    uri = discovery()["jwks_uri"]
    with _lock:
        client = _jwks_clients.get(uri) or jwt.PyJWKClient(uri, cache_keys=True, lifespan=3600)
        _jwks_clients[uri] = client
    try:
        return client.get_signing_key_from_jwt(id_token).key
    except jwt.PyJWKClientError as exc:
        raise OIDCError("bad_token", str(exc)) from exc


def exchange_code(code: str, verifier: str) -> dict:
    try:
        resp = httpx.post(
            discovery()["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
                "code_verifier": verifier,
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise OIDCError("idp_unavailable", str(exc)) from exc
    if resp.status_code != 200:
        # Never log the response body: it can contain tokens.
        raise OIDCError("code_rejected", f"Token endpoint returned {resp.status_code}")
    return resp.json()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start() -> tuple[str, str]:
    """Return (authorization URL, signed state cookie value)."""
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    url = (
        discovery()["authorization_endpoint"]
        + "?"
        + urlencode(
            {
                "client_id": settings.oidc_client_id,
                "response_type": "code",
                "redirect_uri": settings.oidc_redirect_uri,
                "response_mode": "query",
                "scope": "openid profile email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    now = datetime.now(timezone.utc)
    cookie = jwt.encode(
        {
            "st": state,
            "nn": nonce,
            "cv": verifier,
            "aud": _STATE_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return url, cookie


def read_state(cookie: str | None, state: str | None) -> dict:
    if not cookie or not state:
        raise OIDCError("state_missing")
    try:
        data = jwt.decode(cookie, settings.jwt_secret, algorithms=["HS256"], audience=_STATE_AUDIENCE)
    except jwt.InvalidTokenError as exc:
        raise OIDCError("state_invalid") from exc
    if not secrets.compare_digest(str(data.get("st", "")), state):
        raise OIDCError("state_mismatch")
    return data


def verify_id_token(id_token: str, nonce: str) -> dict:
    try:
        claims = jwt.decode(
            id_token,
            signing_key(id_token),
            algorithms=["RS256"],
            audience=settings.oidc_client_id,
            issuer=issuer(),
            leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise OIDCError("bad_token", str(exc)) from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OIDCError("bad_nonce")
    if claims.get("tid") and claims["tid"] != settings.oidc_tenant_id:
        raise OIDCError("wrong_tenant")
    return claims


def email_of(claims: dict) -> str:
    email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if "@" not in email:
        raise OIDCError("no_email")
    domain = email.rsplit("@", 1)[1]
    if settings.oidc_allowed_domains and domain not in {d.lower() for d in settings.oidc_allowed_domains}:
        raise OIDCError("domain_not_allowed")
    return email


def role_map() -> dict[str, str]:
    try:
        raw = json.loads(settings.oidc_role_map or "{}")
    except ValueError:
        logger.error("OIDC_ROLE_MAP is not valid JSON; ignoring it")
        return {}
    return {str(k): v for k, v in raw.items() if v in ROLE_PERMISSIONS and v != PLATFORM_ADMIN}


# Highest wins when a user is in several mapped groups.
_RANK = ["viewer", "auditor", "operator", "developer", "org_admin"]


def mapped_role(claims: dict) -> str | None:
    mapping = role_map()
    values = [str(v) for key in ("roles", "groups") for v in (claims.get(key) or [])]
    roles = {mapping[v] for v in values if v in mapping}
    for role in reversed(_RANK):
        if role in roles:
            return role
    return None


def default_role() -> str | None:
    role = settings.oidc_default_role.strip()
    return role if role in ROLE_PERMISSIONS and role not in (PLATFORM_ADMIN, "org_admin") else None
