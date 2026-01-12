"""
Signers module for exchange authentication.

Provides cryptographic signing implementations for:
- Kalshi: RSA-2048 signing
- Polymarket: EIP-712 Ethereum signing
"""

from src.signers.kalshi_signer import (
    InvalidKeyError,
    KalshiSigner,
    KalshiSignerError,
    SigningError,
    generate_key_pair,
)

__all__ = [
    "KalshiSigner",
    "KalshiSignerError",
    "InvalidKeyError",
    "SigningError",
    "generate_key_pair",
]
