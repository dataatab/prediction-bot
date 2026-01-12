"""
Kalshi API Client

Async HTTP client for the Kalshi trading API v2.
Handles authentication via RSA-2048 signing and provides
methods for account and market operations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import structlog

from src.signers.kalshi_signer import KalshiSigner

logger = structlog.get_logger(__name__)


class KalshiClientError(Exception):
    """Base exception for Kalshi client errors."""

    pass


class KalshiAuthenticationError(KalshiClientError):
    """Raised when authentication fails."""

    pass


class KalshiAPIError(KalshiClientError):
    """Raised when API returns an error response."""

    def __init__(self, message: str, status_code: int, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class KalshiBalance:
    """Represents the account balance from Kalshi."""

    def __init__(
        self,
        balance_cents: int,
        portfolio_value_cents: int,
        payout_cents: int,
    ) -> None:
        """
        Initialize balance data.

        Args:
            balance_cents: Available balance in cents.
            portfolio_value_cents: Current portfolio value in cents.
            payout_cents: Potential payout value in cents.
        """
        self.balance_cents = balance_cents
        self.portfolio_value_cents = portfolio_value_cents
        self.payout_cents = payout_cents

    @property
    def balance(self) -> Decimal:
        """Available balance in dollars."""
        return Decimal(self.balance_cents) / Decimal(100)

    @property
    def portfolio_value(self) -> Decimal:
        """Portfolio value in dollars."""
        return Decimal(self.portfolio_value_cents) / Decimal(100)

    @property
    def payout(self) -> Decimal:
        """Potential payout in dollars."""
        return Decimal(self.payout_cents) / Decimal(100)

    def __repr__(self) -> str:
        return (
            f"KalshiBalance(balance=${self.balance}, "
            f"portfolio_value=${self.portfolio_value})"
        )


class KalshiClient:
    """
    Async HTTP client for Kalshi API v2.

    Provides authenticated access to Kalshi's trading API including
    account balance, market data, and order management.

    Example:
        >>> signer = KalshiSigner.from_key_file(api_key, key_path)
        >>> async with KalshiClient(signer) as client:
        ...     balance = await client.get_balance()
        ...     print(f"Available: ${balance.balance}")
    """

    # API endpoints
    PROD_BASE_URL = "https://trading-api.kalshi.com"
    DEMO_BASE_URL = "https://demo-api.kalshi.co"

    # API paths
    PATH_BALANCE = "/trade-api/v2/portfolio/balance"
    PATH_MARKETS = "/trade-api/v2/markets"

    def __init__(
        self,
        signer: KalshiSigner,
        base_url: str | None = None,
        use_demo: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the Kalshi client.

        Args:
            signer: KalshiSigner instance for authentication.
            base_url: Override base URL (optional).
            use_demo: Use demo environment if True (default).
            timeout: Request timeout in seconds.
        """
        self._signer = signer
        self._timeout = timeout

        if base_url:
            self._base_url = base_url.rstrip("/")
        else:
            self._base_url = self.DEMO_BASE_URL if use_demo else self.PROD_BASE_URL

        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> KalshiClient:
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not initialized."""
        if self._client is None:
            raise KalshiClientError(
                "Client not initialized. Use 'async with KalshiClient(...) as client:'"
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an authenticated request to the Kalshi API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path.
            params: Query parameters (optional).
            json_body: JSON request body (optional).

        Returns:
            Parsed JSON response.

        Raises:
            KalshiAPIError: If API returns error status.
            KalshiClientError: If request fails.
        """
        client = self._get_client()
        auth_headers = self._signer.sign_request(method, path)

        log = logger.bind(method=method, path=path)
        log.debug("Making Kalshi API request")

        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json_body,
                headers=auth_headers,
            )
        except httpx.RequestError as e:
            log.error("Request failed", error=str(e))
            raise KalshiClientError(f"Request failed: {e}") from e

        if response.status_code == 401:
            log.error("Authentication failed")
            raise KalshiAuthenticationError("Authentication failed - check API key and signature")

        if response.status_code >= 400:
            try:
                error_body = response.json()
            except Exception:
                error_body = response.text

            log.error(
                "API error",
                status_code=response.status_code,
                response=error_body,
            )
            raise KalshiAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_body=error_body,
            )

        return response.json()

    async def get_balance(self) -> KalshiBalance:
        """
        Get the account balance.

        Returns:
            KalshiBalance with available balance and portfolio value.

        Raises:
            KalshiClientError: If request fails.

        Example:
            >>> balance = await client.get_balance()
            >>> print(f"Available: ${balance.balance}")
            >>> print(f"Portfolio: ${balance.portfolio_value}")
        """
        data = await self._request("GET", self.PATH_BALANCE)

        return KalshiBalance(
            balance_cents=data.get("balance", 0),
            portfolio_value_cents=data.get("portfolio_value", 0),
            payout_cents=data.get("payout", 0),
        )

    async def get_available_balance(self) -> Decimal:
        """
        Get just the available balance in dollars.

        This is a convenience method for position sizing.

        Returns:
            Available balance as Decimal in dollars.
        """
        balance = await self.get_balance()
        return balance.balance

    async def get_market(self, ticker: str) -> dict[str, Any]:
        """
        Get market details by ticker.

        Args:
            ticker: The market ticker (e.g., "INXD-24JAN02-T4650").

        Returns:
            Market data dictionary.

        Example:
            >>> market = await client.get_market("INXD-24JAN02-T4650")
            >>> print(market["title"])
        """
        path = f"{self.PATH_MARKETS}/{ticker}"
        data = await self._request("GET", path)
        return data.get("market", data)

    async def list_markets(
        self,
        limit: int = 100,
        cursor: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        List available markets.

        Args:
            limit: Maximum number of markets to return.
            cursor: Pagination cursor from previous response.
            status: Filter by market status (e.g., "open").

        Returns:
            Dictionary with "markets" list and optional "cursor".
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status

        return await self._request("GET", self.PATH_MARKETS, params=params)

    async def health_check(self) -> bool:
        """
        Verify API connectivity and authentication.

        Returns:
            True if able to authenticate and fetch balance.

        Example:
            >>> if await client.health_check():
            ...     print("Connected to Kalshi!")
        """
        try:
            await self.get_balance()
            return True
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
