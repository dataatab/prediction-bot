"""
Kalshi API RSA-2048 Signer

Implements authentication for Kalshi's trading API v2 using RSA-PSS signatures.
The signer creates the required authentication headers for all API requests.

Authentication Flow:
1. Create message string: {timestamp_ms}{method}{path}
2. Sign message with RSA-PSS (SHA-256)
3. Base64 encode the signature
4. Include in request headers
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

if TYPE_CHECKING:
    from typing import TypedDict

    class KalshiAuthHeaders(TypedDict):
        """Type definition for Kalshi authentication headers."""

        KALSHI_ACCESS_KEY: str
        KALSHI_ACCESS_SIGNATURE: str
        KALSHI_ACCESS_TIMESTAMP: str


class KalshiSignerError(Exception):
    """Base exception for Kalshi signer errors."""

    pass


class InvalidKeyError(KalshiSignerError):
    """Raised when the RSA private key is invalid or cannot be loaded."""

    pass


class SigningError(KalshiSignerError):
    """Raised when signing operation fails."""

    pass


class KalshiSigner:
    """
    RSA-2048 signer for Kalshi API authentication.

    This class handles the cryptographic signing required for Kalshi's trading API.
    It loads an RSA private key and generates authentication headers for each request.

    Attributes:
        api_key: The Kalshi API key (member ID) used in authentication headers.
        private_key: The RSA private key used for signing requests.

    Example:
        >>> signer = KalshiSigner.from_key_file(
        ...     api_key="your-api-key",
        ...     key_path="/path/to/private_key.pem"
        ... )
        >>> headers = signer.sign_request("GET", "/trade-api/v2/markets")
        >>> # Use headers in your HTTP request
    """

    # Kalshi API header names
    HEADER_ACCESS_KEY = "KALSHI-ACCESS-KEY"
    HEADER_ACCESS_SIGNATURE = "KALSHI-ACCESS-SIGNATURE"
    HEADER_ACCESS_TIMESTAMP = "KALSHI-ACCESS-TIMESTAMP"

    def __init__(self, api_key: str, private_key: RSAPrivateKey) -> None:
        """
        Initialize the KalshiSigner with credentials.

        Args:
            api_key: Your Kalshi API key (member ID).
            private_key: An RSA private key object for signing.

        Raises:
            InvalidKeyError: If the private key is not a valid RSA key.
        """
        if not api_key:
            raise InvalidKeyError("API key cannot be empty")

        self._validate_key(private_key)
        self._api_key = api_key
        self._private_key = private_key

    @staticmethod
    def _validate_key(private_key: RSAPrivateKey) -> None:
        """
        Validate that the key is a proper RSA key with sufficient size.

        Args:
            private_key: The RSA private key to validate.

        Raises:
            InvalidKeyError: If the key is invalid or too small.
        """
        if not isinstance(private_key, RSAPrivateKey):
            raise InvalidKeyError(
                f"Expected RSAPrivateKey, got {type(private_key).__name__}"
            )

        key_size = private_key.key_size
        if key_size < 2048:
            raise InvalidKeyError(
                f"RSA key size must be at least 2048 bits, got {key_size}"
            )

    @classmethod
    def from_key_file(
        cls,
        api_key: str,
        key_path: str | Path,
        password: bytes | None = None,
    ) -> KalshiSigner:
        """
        Create a KalshiSigner from a PEM-encoded private key file.

        Args:
            api_key: Your Kalshi API key (member ID).
            key_path: Path to the PEM-encoded RSA private key file.
            password: Optional password if the key is encrypted.

        Returns:
            A configured KalshiSigner instance.

        Raises:
            InvalidKeyError: If the key file cannot be read or parsed.

        Example:
            >>> signer = KalshiSigner.from_key_file(
            ...     api_key="member-id-123",
            ...     key_path="~/.kalshi/private_key.pem"
            ... )
        """
        key_path = Path(key_path).expanduser().resolve()

        if not key_path.exists():
            raise InvalidKeyError(f"Key file not found: {key_path}")

        try:
            key_data = key_path.read_bytes()
            private_key = serialization.load_pem_private_key(
                key_data,
                password=password,
            )
        except Exception as e:
            raise InvalidKeyError(f"Failed to load private key: {e}") from e

        if not isinstance(private_key, RSAPrivateKey):
            raise InvalidKeyError("Key file does not contain an RSA private key")

        return cls(api_key=api_key, private_key=private_key)

    @classmethod
    def from_key_string(
        cls,
        api_key: str,
        key_pem: str,
        password: bytes | None = None,
    ) -> KalshiSigner:
        """
        Create a KalshiSigner from a PEM-encoded private key string.

        This is useful when the key is stored in environment variables or
        secret managers rather than as a file.

        Args:
            api_key: Your Kalshi API key (member ID).
            key_pem: The PEM-encoded RSA private key as a string.
            password: Optional password if the key is encrypted.

        Returns:
            A configured KalshiSigner instance.

        Raises:
            InvalidKeyError: If the key cannot be parsed.

        Example:
            >>> key_pem = os.environ["KALSHI_PRIVATE_KEY"]
            >>> signer = KalshiSigner.from_key_string(
            ...     api_key="member-id-123",
            ...     key_pem=key_pem
            ... )
        """
        try:
            # Handle keys that may have escaped newlines
            key_pem_cleaned = key_pem.replace("\\n", "\n")
            private_key = serialization.load_pem_private_key(
                key_pem_cleaned.encode("utf-8"),
                password=password,
            )
        except Exception as e:
            raise InvalidKeyError(f"Failed to parse private key: {e}") from e

        if not isinstance(private_key, RSAPrivateKey):
            raise InvalidKeyError("PEM data does not contain an RSA private key")

        return cls(api_key=api_key, private_key=private_key)

    @property
    def api_key(self) -> str:
        """Get the API key used for authentication."""
        return self._api_key

    def _get_timestamp_ms(self) -> int:
        """
        Get current Unix timestamp in milliseconds.

        Returns:
            Current time as milliseconds since Unix epoch.
        """
        return int(time.time() * 1000)

    def _create_signature_message(
        self,
        timestamp_ms: int,
        method: str,
        path: str,
    ) -> bytes:
        """
        Create the message to be signed.

        The message format is: {timestamp_ms}{method}{path}

        Args:
            timestamp_ms: Unix timestamp in milliseconds.
            method: HTTP method (GET, POST, PUT, DELETE).
            path: The API endpoint path (e.g., "/trade-api/v2/markets").

        Returns:
            The message as bytes, ready for signing.
        """
        message = f"{timestamp_ms}{method.upper()}{path}"
        return message.encode("utf-8")

    def _sign_message(self, message: bytes) -> bytes:
        """
        Sign a message using RSA-PSS with SHA-256.

        Args:
            message: The message bytes to sign.

        Returns:
            The raw signature bytes.

        Raises:
            SigningError: If the signing operation fails.
        """
        try:
            signature = self._private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return signature
        except Exception as e:
            raise SigningError(f"Failed to sign message: {e}") from e

    def sign_request(
        self,
        method: str,
        path: str,
        timestamp_ms: int | None = None,
    ) -> dict[str, str]:
        """
        Generate authentication headers for a Kalshi API request.

        This method creates all required headers for authenticating with
        Kalshi's trading API. The headers should be included in every
        API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: The API endpoint path (e.g., "/trade-api/v2/markets").
            timestamp_ms: Optional timestamp override (for testing).
                         If not provided, current time is used.

        Returns:
            A dictionary containing the three authentication headers:
            - KALSHI-ACCESS-KEY: Your API key
            - KALSHI-ACCESS-SIGNATURE: Base64-encoded RSA signature
            - KALSHI-ACCESS-TIMESTAMP: Unix timestamp in milliseconds

        Raises:
            SigningError: If signature generation fails.

        Example:
            >>> headers = signer.sign_request("GET", "/trade-api/v2/markets")
            >>> response = await client.get(url, headers=headers)
        """
        if timestamp_ms is None:
            timestamp_ms = self._get_timestamp_ms()

        # Create and sign the message
        message = self._create_signature_message(timestamp_ms, method, path)
        signature = self._sign_message(message)

        # Base64 encode the signature
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            self.HEADER_ACCESS_KEY: self._api_key,
            self.HEADER_ACCESS_SIGNATURE: signature_b64,
            self.HEADER_ACCESS_TIMESTAMP: str(timestamp_ms),
        }

    def get_websocket_auth_message(self, path: str = "/trade-api/ws/v2") -> dict:
        """
        Generate authentication data for WebSocket connections.

        Kalshi WebSocket connections require authentication via a message
        sent after connection establishment.

        Args:
            path: The WebSocket endpoint path. Defaults to the trading WS.

        Returns:
            A dictionary containing the authentication message payload
            to send over the WebSocket.

        Example:
            >>> auth_msg = signer.get_websocket_auth_message()
            >>> await ws.send_json(auth_msg)
        """
        timestamp_ms = self._get_timestamp_ms()
        message = self._create_signature_message(timestamp_ms, "GET", path)
        signature = self._sign_message(message)
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "id": 1,
            "cmd": "auth",
            "params": {
                "api_key": self._api_key,
                "signature": signature_b64,
                "timestamp": str(timestamp_ms),
            },
        }


def generate_key_pair(key_size: int = 2048) -> tuple[bytes, bytes]:
    """
    Generate a new RSA key pair for Kalshi API authentication.

    This utility function generates a new RSA key pair that can be used
    with the Kalshi API. The public key should be uploaded to your
    Kalshi account, and the private key should be stored securely.

    Args:
        key_size: The RSA key size in bits. Must be at least 2048.
                 Defaults to 2048.

    Returns:
        A tuple of (private_key_pem, public_key_pem) as bytes.

    Example:
        >>> private_pem, public_pem = generate_key_pair()
        >>> Path("private_key.pem").write_bytes(private_pem)
        >>> # Upload public_pem to Kalshi dashboard
    """
    if key_size < 2048:
        raise ValueError("Key size must be at least 2048 bits")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_pem, public_pem
