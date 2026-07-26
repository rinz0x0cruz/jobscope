"""Cloudflare Access JWT validation for the private hosted control plane."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import jwt

_TEAM_DOMAIN_ENV = "JOBSCOPE_CF_ACCESS_TEAM_DOMAIN"
_AUDIENCE_ENV = "JOBSCOPE_CF_ACCESS_AUD"


class AccessJWTVerifier:
    def __init__(self, team_domain: str, audience: str, *, jwks_client: Any = None):
        self.team_domain = _valid_team_domain(team_domain)
        self.audience = (audience or "").strip()
        if not self.audience or len(self.audience) > 512:
            raise RuntimeError(f"{_AUDIENCE_ENV} is required in hosted mode")
        self.jwks_client = jwks_client or jwt.PyJWKClient(
            f"{self.team_domain}/cdn-cgi/access/certs",
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=3600,
            timeout=5,
        )

    @classmethod
    def from_environment(cls) -> "AccessJWTVerifier":
        return cls(
            os.environ.get(_TEAM_DOMAIN_ENV, ""),
            os.environ.get(_AUDIENCE_ENV, ""),
        )

    def verify(self, token: str) -> bool:
        if not token or len(token) > 16_384:
            return False
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                return False
            key = self.jwks_client.get_signing_key_from_jwt(token).key
            jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.team_domain,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
            return True
        except (jwt.PyJWTError, ValueError, TypeError, OSError):
            return False


def _valid_team_domain(value: str) -> str:
    team_domain = (value or "").strip().rstrip("/")
    try:
        parsed = urlparse(team_domain)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError(f"{_TEAM_DOMAIN_ENV} must be a Cloudflare Access HTTPS origin") from exc
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".cloudflareaccess.com")
        or hostname == ".cloudflareaccess.com"
        or port is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(f"{_TEAM_DOMAIN_ENV} must be a Cloudflare Access HTTPS origin")
    return f"https://{hostname}"
