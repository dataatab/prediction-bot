"""
Unit tests for KalshiSigner class.

Tests RSA-2048 signing for Kalshi API authentication.
"""

import base64
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from src.signers.kalshi_signer import (
    InvalidKeyError,
    KalshiSigner,
    SigningError,
    generate_key_pair,
)


@pytest.fixture
def rsa_private_key():
    """Generate a fresh RSA-2048 private key for testing."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture
def rsa_private_key_pem(rsa_private_key) -> bytes:
    """Get PEM-encoded private key."""
    return rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@pytest.fixture
def signer(rsa_private_key) -> KalshiSigner:
    """Create a KalshiSigner instance for testing."""
    return KalshiSigner(api_key="test-api-key", private_key=rsa_private_key)


class TestKalshiSignerInit:
    """Tests for KalshiSigner initialization."""

    def test_init_with_valid_key(self, rsa_private_key):
        """Should initialize with a valid RSA-2048 key."""
        signer = KalshiSigner(api_key="test-key", private_key=rsa_private_key)
        assert signer.api_key == "test-key"

    def test_init_empty_api_key_raises(self, rsa_private_key):
        """Should raise InvalidKeyError for empty API key."""
        with pytest.raises(InvalidKeyError, match="API key cannot be empty"):
            KalshiSigner(api_key="", private_key=rsa_private_key)

    def test_init_invalid_key_type_raises(self):
        """Should raise InvalidKeyError for non-RSA key."""
        with pytest.raises(InvalidKeyError, match="Expected RSAPrivateKey"):
            KalshiSigner(api_key="test-key", private_key="not-a-key")  # type: ignore

    def test_init_small_key_raises(self):
        """Should raise InvalidKeyError for RSA key smaller than 2048 bits."""
        small_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=1024,  # Too small
        )
        with pytest.raises(InvalidKeyError, match="at least 2048 bits"):
            KalshiSigner(api_key="test-key", private_key=small_key)


class TestKalshiSignerFromKeyFile:
    """Tests for KalshiSigner.from_key_file factory method."""

    def test_from_key_file_success(self, rsa_private_key_pem, tmp_path):
        """Should load signer from a valid PEM key file."""
        key_file = tmp_path / "private_key.pem"
        key_file.write_bytes(rsa_private_key_pem)

        signer = KalshiSigner.from_key_file(
            api_key="test-key",
            key_path=key_file,
        )
        assert signer.api_key == "test-key"

    def test_from_key_file_not_found(self, tmp_path):
        """Should raise InvalidKeyError if file doesn't exist."""
        with pytest.raises(InvalidKeyError, match="Key file not found"):
            KalshiSigner.from_key_file(
                api_key="test-key",
                key_path=tmp_path / "nonexistent.pem",
            )

    def test_from_key_file_invalid_content(self, tmp_path):
        """Should raise InvalidKeyError for invalid PEM content."""
        key_file = tmp_path / "bad_key.pem"
        key_file.write_text("not a valid key")

        with pytest.raises(InvalidKeyError, match="Failed to load private key"):
            KalshiSigner.from_key_file(
                api_key="test-key",
                key_path=key_file,
            )


class TestKalshiSignerFromKeyString:
    """Tests for KalshiSigner.from_key_string factory method."""

    def test_from_key_string_success(self, rsa_private_key_pem):
        """Should load signer from a PEM key string."""
        signer = KalshiSigner.from_key_string(
            api_key="test-key",
            key_pem=rsa_private_key_pem.decode("utf-8"),
        )
        assert signer.api_key == "test-key"

    def test_from_key_string_with_escaped_newlines(self, rsa_private_key_pem):
        """Should handle PEM strings with escaped newlines."""
        # Replace actual newlines with escaped ones (like from env vars)
        escaped_pem = rsa_private_key_pem.decode("utf-8").replace("\n", "\\n")

        signer = KalshiSigner.from_key_string(
            api_key="test-key",
            key_pem=escaped_pem,
        )
        assert signer.api_key == "test-key"

    def test_from_key_string_invalid(self):
        """Should raise InvalidKeyError for invalid PEM string."""
        with pytest.raises(InvalidKeyError, match="Failed to parse private key"):
            KalshiSigner.from_key_string(
                api_key="test-key",
                key_pem="not a valid key",
            )


class TestSignRequest:
    """Tests for the sign_request method."""

    def test_sign_request_returns_required_headers(self, signer):
        """Should return all required authentication headers."""
        headers = signer.sign_request("GET", "/trade-api/v2/markets")

        assert "KALSHI-ACCESS-KEY" in headers
        assert "KALSHI-ACCESS-SIGNATURE" in headers
        assert "KALSHI-ACCESS-TIMESTAMP" in headers

    def test_sign_request_api_key_in_headers(self, signer):
        """Should include the API key in headers."""
        headers = signer.sign_request("GET", "/trade-api/v2/markets")
        assert headers["KALSHI-ACCESS-KEY"] == "test-api-key"

    def test_sign_request_timestamp_is_current(self, signer):
        """Timestamp should be close to current time."""
        before = int(time.time() * 1000)
        headers = signer.sign_request("GET", "/trade-api/v2/markets")
        after = int(time.time() * 1000)

        timestamp = int(headers["KALSHI-ACCESS-TIMESTAMP"])
        assert before <= timestamp <= after

    def test_sign_request_signature_is_base64(self, signer):
        """Signature should be valid base64."""
        headers = signer.sign_request("GET", "/trade-api/v2/markets")
        signature = headers["KALSHI-ACCESS-SIGNATURE"]

        # Should not raise on valid base64
        decoded = base64.b64decode(signature)
        assert len(decoded) > 0

    def test_sign_request_signature_is_valid(self, signer, rsa_private_key):
        """Signature should be verifiable with the public key."""
        timestamp_ms = 1699012345678
        method = "GET"
        path = "/trade-api/v2/markets"

        headers = signer.sign_request(method, path, timestamp_ms=timestamp_ms)
        signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])

        # Verify the signature
        message = f"{timestamp_ms}{method}{path}".encode("utf-8")
        public_key = rsa_private_key.public_key()

        # This should not raise if signature is valid
        public_key.verify(
            signature,
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_sign_request_different_methods(self, signer):
        """Should produce different signatures for different HTTP methods."""
        timestamp_ms = 1699012345678
        path = "/trade-api/v2/orders"

        get_headers = signer.sign_request("GET", path, timestamp_ms=timestamp_ms)
        post_headers = signer.sign_request("POST", path, timestamp_ms=timestamp_ms)

        assert get_headers["KALSHI-ACCESS-SIGNATURE"] != post_headers["KALSHI-ACCESS-SIGNATURE"]

    def test_sign_request_different_paths(self, signer):
        """Should produce different signatures for different paths."""
        timestamp_ms = 1699012345678

        headers1 = signer.sign_request("GET", "/trade-api/v2/markets", timestamp_ms=timestamp_ms)
        headers2 = signer.sign_request("GET", "/trade-api/v2/orders", timestamp_ms=timestamp_ms)

        assert headers1["KALSHI-ACCESS-SIGNATURE"] != headers2["KALSHI-ACCESS-SIGNATURE"]

    def test_sign_request_uppercase_method(self, signer):
        """Method should be normalized to uppercase."""
        timestamp_ms = 1699012345678
        path = "/trade-api/v2/markets"

        lower_headers = signer.sign_request("get", path, timestamp_ms=timestamp_ms)
        upper_headers = signer.sign_request("GET", path, timestamp_ms=timestamp_ms)

        assert lower_headers["KALSHI-ACCESS-SIGNATURE"] == upper_headers["KALSHI-ACCESS-SIGNATURE"]


class TestWebSocketAuth:
    """Tests for WebSocket authentication."""

    def test_get_websocket_auth_message_structure(self, signer):
        """Should return properly structured WebSocket auth message."""
        auth_msg = signer.get_websocket_auth_message()

        assert auth_msg["id"] == 1
        assert auth_msg["cmd"] == "auth"
        assert "params" in auth_msg
        assert auth_msg["params"]["api_key"] == "test-api-key"
        assert "signature" in auth_msg["params"]
        assert "timestamp" in auth_msg["params"]


class TestGenerateKeyPair:
    """Tests for the generate_key_pair utility function."""

    def test_generate_key_pair_default_size(self):
        """Should generate 2048-bit keys by default."""
        private_pem, public_pem = generate_key_pair()

        # Should be valid PEM format
        assert private_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert public_pem.startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_generate_key_pair_custom_size(self):
        """Should support custom key sizes >= 2048."""
        private_pem, public_pem = generate_key_pair(key_size=4096)

        # Load and verify key size
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        assert private_key.key_size == 4096

    def test_generate_key_pair_small_size_raises(self):
        """Should raise ValueError for key size < 2048."""
        with pytest.raises(ValueError, match="at least 2048 bits"):
            generate_key_pair(key_size=1024)

    def test_generate_key_pair_usable_with_signer(self):
        """Generated keys should work with KalshiSigner."""
        private_pem, _ = generate_key_pair()

        signer = KalshiSigner.from_key_string(
            api_key="test-key",
            key_pem=private_pem.decode("utf-8"),
        )

        # Should be able to sign requests
        headers = signer.sign_request("GET", "/trade-api/v2/markets")
        assert "KALSHI-ACCESS-SIGNATURE" in headers
