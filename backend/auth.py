"""
Clerk JWT verification.

The backend trusts Clerk-issued session tokens sent in the
`Authorization: Bearer <jwt>` header. Verification:
- JWKS fetched from CLERK_JWKS_URL (PyJWKClient caches the response per process).
- Signature checked against the JWK whose kid matches the JWT header, using RS256.
- `iss` claim verified against CLERK_ISSUER (the Clerk instance issuer URL).
- `exp` / `nbf` verified by PyJWT.

Two FastAPI dependencies are exposed:
- `get_current_user` — required-auth endpoints (401/503 on failure).
- `get_current_user_optional` — endpoints that gracefully degrade for anonymous
  callers (returns None on missing / invalid / not-configured).
"""
from __future__ import annotations

import os
from typing import Optional

import jwt
from fastapi import Header, HTTPException

CLERK_ISSUER = os.environ.get("CLERK_ISSUER")
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL")

_jwks_client: Optional["jwt.PyJWKClient"] = None


def is_auth_configured() -> bool:
    """True when both CLERK_ISSUER and CLERK_JWKS_URL are set in the environment."""
    return bool(CLERK_ISSUER and CLERK_JWKS_URL)


def _get_jwks_client() -> "jwt.PyJWKClient":
    global _jwks_client
    if _jwks_client is None:
        if not CLERK_JWKS_URL:
            raise RuntimeError("CLERK_JWKS_URL not configured")
        _jwks_client = jwt.PyJWKClient(CLERK_JWKS_URL)
    return _jwks_client


def _verify_token(token: str) -> dict:
    """Verify the JWT and return its claims. Raises jwt.PyJWTError on failure."""
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=CLERK_ISSUER,
        options={"verify_aud": False},
    )


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency: returns the authenticated Clerk user_id (sub claim).
    Raises 401 on any verification failure, 503 if auth isn't configured."""
    if not is_auth_configured():
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    try:
        claims = _verify_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim.")
    return user_id


def _claims_or_none(authorization: Optional[str]) -> Optional[dict]:
    """Verify the bearer token and return claims, or None on any failure / when
    auth is unconfigured. Shared by all *_optional dependencies so the JWT is
    only decoded once per request (FastAPI caches dependency results)."""
    if not is_auth_configured():
        return None
    token = _extract_bearer(authorization)
    if not token:
        return None
    try:
        return _verify_token(token)
    except jwt.PyJWTError:
        return None


def get_current_user_optional(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Return user_id when a valid token is present, None otherwise. No raises;
    used by endpoints that work for anonymous users with degraded functionality
    (no persistence, no history)."""
    claims = _claims_or_none(authorization)
    return claims.get("sub") if claims else None


def get_current_org_optional(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Return the active Clerk organisation id from the session token, or None.
    Clerk includes `org_id` when the user is acting inside an org context;
    solo users get None. Phase-5 endpoints use this to share scans across an
    org's members."""
    claims = _claims_or_none(authorization)
    return claims.get("org_id") if claims else None


def get_current_org_role_optional(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    """Return the caller's role inside the active org (Clerk's `org_role`,
    typically "admin" or "basic_member"), or None. Used by the frontend to
    gate admin-only UI; the backend does not enforce role-based ACLs yet."""
    claims = _claims_or_none(authorization)
    return claims.get("org_role") if claims else None
