import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from jobscope.deliver.access import AccessJWTVerifier


TEAM = "https://example.cloudflareaccess.com"
AUDIENCE = "app-audience"
NOW = dt.datetime.now(dt.timezone.utc)


class _SigningKey:
    def __init__(self, key):
        self.key = key


class _JwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return _SigningKey(self.key.public_key())


def _token(key, **claims):
    payload = {
        "iss": TEAM,
        "aud": AUDIENCE,
        "iat": NOW,
        "exp": NOW + dt.timedelta(minutes=5),
        "sub": "identity",
        **claims,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})


def test_access_verifier_requires_valid_signature_issuer_audience_and_expiry():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = AccessJWTVerifier(TEAM, AUDIENCE, jwks_client=_JwksClient(key))

    assert verifier.verify(_token(key)) is True
    assert verifier.verify(_token(key, aud="wrong")) is False
    assert verifier.verify(_token(key, iss="https://wrong.cloudflareaccess.com")) is False
    assert verifier.verify(_token(key, exp=NOW - dt.timedelta(minutes=1))) is False
    # 32 bytes only to avoid PyJWT's weak-key warning; the point is HS256 is refused.
    assert verifier.verify(
        jwt.encode({"aud": AUDIENCE}, "s" * 32, algorithm="HS256")
    ) is False
    assert verifier.verify("not-a-token") is False


@pytest.mark.parametrize("team", [
    "",
    "http://example.cloudflareaccess.com",
    "https://example.cloudflareaccess.com/path",
    "https://example.com",
    "https://user@example.cloudflareaccess.com",
])
def test_access_verifier_rejects_invalid_team_domain(team):
    with pytest.raises(RuntimeError, match="Cloudflare Access HTTPS origin"):
        AccessJWTVerifier(team, AUDIENCE, jwks_client=object())


def test_access_verifier_requires_audience():
    with pytest.raises(RuntimeError, match="JOBSCOPE_CF_ACCESS_AUD"):
        AccessJWTVerifier(TEAM, "", jwks_client=object())
