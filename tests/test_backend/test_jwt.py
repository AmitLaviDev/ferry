"""Tests for GitHub App JWT generation."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ferry_backend.auth.jwt import generate_app_jwt


@pytest.fixture
def rsa_key_pair():
    """Generate an RSA key pair for testing JWT signing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key = private_key.public_key()
    return private_pem, public_key


class TestGenerateAppJwt:
    """Tests for generate_app_jwt function."""

    def test_returns_string(self, rsa_key_pair):
        """JWT should be returned as a string (PyJWT 2.0+ behavior)."""
        private_pem, _ = rsa_key_pair
        token = generate_app_jwt("Iv1.abc123", private_pem)
        assert isinstance(token, str)

    def test_uses_rs256_algorithm(self, rsa_key_pair):
        """JWT must use RS256 algorithm."""
        private_pem, public_key = rsa_key_pair
        token = generate_app_jwt("Iv1.abc123", private_pem)
        # Decode with public key -- will fail if algorithm is not RS256
        decoded = jwt.decode(token, public_key, algorithms=["RS256"])
        assert decoded is not None

    def test_iss_claim_matches_app_id(self, rsa_key_pair):
        """JWT iss claim should be the app_id (Client ID string)."""
        private_pem, public_key = rsa_key_pair
        token = generate_app_jwt("Iv1.abc123", private_pem)
        decoded = jwt.decode(token, public_key, algorithms=["RS256"])
        assert decoded["iss"] == "Iv1.abc123"

    def test_iat_backdated_60_seconds(self, rsa_key_pair):
        """JWT iat should be backdated 60 seconds for clock drift tolerance."""
        private_pem, public_key = rsa_key_pair
        now = int(time.time())
        token = generate_app_jwt("Iv1.abc123", private_pem)
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        # iat should be approximately now - 60
        assert abs(decoded["iat"] - (now - 60)) <= 2

    def test_exp_set_to_9_minutes(self, rsa_key_pair):
        """JWT exp should be set to 540 seconds (9 minutes) from now."""
        private_pem, public_key = rsa_key_pair
        now = int(time.time())
        token = generate_app_jwt("Iv1.abc123", private_pem)
        decoded = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        # exp should be approximately now + 540
        assert abs(decoded["exp"] - (now + 540)) <= 2

    def test_jwt_decodable_with_public_key(self, rsa_key_pair):
        """JWT should be decodable and verifiable with the corresponding public key."""
        private_pem, public_key = rsa_key_pair
        token = generate_app_jwt("Iv1.abc123", private_pem)
        decoded = jwt.decode(token, public_key, algorithms=["RS256"])
        assert "iss" in decoded
        assert "iat" in decoded
        assert "exp" in decoded

    def test_invalid_pem_key_raises_error(self):
        """Invalid/malformed PEM key should raise a clear error."""
        with pytest.raises(Exception):
            generate_app_jwt("Iv1.abc123", "not-a-valid-pem-key")

    def test_different_app_ids_produce_different_iss(self, rsa_key_pair):
        """Different app IDs should produce JWTs with different iss claims."""
        private_pem, public_key = rsa_key_pair
        token1 = generate_app_jwt("Iv1.abc123", private_pem)
        token2 = generate_app_jwt("Iv1.def456", private_pem)
        decoded1 = jwt.decode(token1, public_key, algorithms=["RS256"])
        decoded2 = jwt.decode(token2, public_key, algorithms=["RS256"])
        assert decoded1["iss"] != decoded2["iss"]
