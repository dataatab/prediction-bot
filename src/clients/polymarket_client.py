"""
Polymarket CLOB API Client

Async HTTP client for the Polymarket Central Limit Order Book API.
Handles balance queries and market operations on the Polygon network.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class AssetType(str, Enum):
    """Asset types for balance queries."""

    COLLATERAL = "COLLATERAL"  # USDC
    CONDITIONAL = "CONDITIONAL"  # Outcome tokens


class PolymarketClientError(Exception):
    """Base exception for Polymarket client errors."""

    pass


class PolymarketAPIError(PolymarketClientError):
    """Raised when API returns an error response."""

    def __init__(self, message: str, status_code: int, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class PolymarketBalance:
    """Represents balance and allowance from Polymarket."""

    # USDC has 6 decimals on Polygon
    USDC_DECIMALS = 6

    def __init__(
        self,
        balance_raw: str,
        allowance_raw: str,
        asset_type: AssetType,
    ) -> None:
        """
        Initialize balance data.

        Args:
            balance_raw: Raw balance string from API.
            allowance_raw: Raw allowance string from API.
            asset_type: Type of asset (COLLATERAL or CONDITIONAL).
        """
        self.balance_raw = balance_raw
        self.allowance_raw = allowance_raw
        self.asset_type = asset_type

    @property
    def balance(self) -> Decimal:
        """Balance in human-readable units (dollars for USDC)."""
        raw = Decimal(self.balance_raw)
        return raw / Decimal(10 ** self.USDC_DECIMALS)

    @property
    def allowance(self) -> Decimal:
        """Allowance in human-readable units."""
        raw = Decimal(self.allowance_raw)
        return raw / Decimal(10 ** self.USDC_DECIMALS)

    def __repr__(self) -> str:
        return (
            f"PolymarketBalance(balance=${self.balance}, "
            f"allowance=${self.allowance}, type={self.asset_type.value})"
        )


class PolymarketClient:
    """
    Async HTTP client for Polymarket CLOB API.

    Provides access to Polymarket's Central Limit Order Book API
    for balance queries, market data, and order operations.

    Note: This client handles read-only operations. Order signing
    requires the PolySigner class for EIP-712 signatures.

    Example:
        >>> async with PolymarketClient(wallet_address) as client:
        ...     balance = await client.get_balance()
        ...     print(f"USDC Balance: ${balance.balance}")
    """

    # API endpoints
    CLOB_API_URL = "https://clob.polymarket.com"
    GAMMA_API_URL = "https://gamma-api.polymarket.com"

    def __init__(
        self,
        wallet_address: str,
        api_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the Polymarket client.

        Args:
            wallet_address: Ethereum wallet address (0x...).
            api_url: Override CLOB API URL (optional).
            timeout: Request timeout in seconds.
        """
        self._wallet_address = wallet_address.lower()
        self._api_url = (api_url or self.CLOB_API_URL).rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def wallet_address(self) -> str:
        """Get the wallet address."""
        return self._wallet_address

    async def __aenter__(self) -> PolymarketClient:
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
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
            raise PolymarketClientError(
                "Client not initialized. Use 'async with PolymarketClient(...) as client:'"
            )
        return self._client

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a request to the Polymarket API.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL or path.
            params: Query parameters (optional).
            json_body: JSON request body (optional).

        Returns:
            Parsed JSON response.

        Raises:
            PolymarketAPIError: If API returns error status.
            PolymarketClientError: If request fails.
        """
        client = self._get_client()

        log = logger.bind(method=method, url=url)
        log.debug("Making Polymarket API request")

        try:
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
            )
        except httpx.RequestError as e:
            log.error("Request failed", error=str(e))
            raise PolymarketClientError(f"Request failed: {e}") from e

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
            raise PolymarketAPIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                response_body=error_body,
            )

        return response.json()

    async def get_balance_allowance(
        self,
        asset_type: AssetType = AssetType.COLLATERAL,
        token_id: str | None = None,
    ) -> PolymarketBalance:
        """
        Get balance and allowance for the wallet.

        Args:
            asset_type: Type of asset to query (default: COLLATERAL/USDC).
            token_id: Specific token ID for conditional tokens (optional).

        Returns:
            PolymarketBalance with balance and allowance.

        Example:
            >>> balance = await client.get_balance_allowance()
            >>> print(f"USDC Balance: ${balance.balance}")
        """
        url = f"{self._api_url}/balance-allowance"
        params: dict[str, Any] = {
            "address": self._wallet_address,
            "asset_type": asset_type.value,
        }
        if token_id:
            params["token_id"] = token_id

        data = await self._request("GET", url, params=params)

        return PolymarketBalance(
            balance_raw=data.get("balance", "0"),
            allowance_raw=data.get("allowance", "0"),
            asset_type=asset_type,
        )

    async def get_available_balance(self) -> Decimal:
        """
        Get just the available USDC balance in dollars.

        This is a convenience method for position sizing.

        Returns:
            Available balance as Decimal in dollars.
        """
        balance = await self.get_balance_allowance(AssetType.COLLATERAL)
        return balance.balance

    async def get_market(self, condition_id: str) -> dict[str, Any]:
        """
        Get market details by condition ID.

        Args:
            condition_id: The market's condition ID.

        Returns:
            Market data dictionary.
        """
        url = f"{self._api_url}/markets/{condition_id}"
        return await self._request("GET", url)

    async def get_markets(
        self,
        next_cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        List available markets.

        Args:
            next_cursor: Pagination cursor from previous response.

        Returns:
            Dictionary with markets list and pagination info.
        """
        url = f"{self._api_url}/markets"
        params: dict[str, Any] = {}
        if next_cursor:
            params["next_cursor"] = next_cursor

        return await self._request("GET", url, params=params)

    async def get_orderbook(
        self,
        token_id: str,
    ) -> dict[str, Any]:
        """
        Get order book for a specific token.

        Args:
            token_id: The outcome token ID.

        Returns:
            Order book with bids and asks.
        """
        url = f"{self._api_url}/book"
        params = {"token_id": token_id}
        return await self._request("GET", url, params=params)

    async def get_midpoint(self, token_id: str) -> Decimal:
        """
        Get the midpoint price for a token.

        Args:
            token_id: The outcome token ID.

        Returns:
            Midpoint price as Decimal.
        """
        url = f"{self._api_url}/midpoint"
        params = {"token_id": token_id}
        data = await self._request("GET", url, params=params)
        return Decimal(data.get("mid", "0"))

    async def health_check(self) -> bool:
        """
        Verify API connectivity.

        Returns:
            True if able to fetch balance.

        Example:
            >>> if await client.health_check():
            ...     print("Connected to Polymarket!")
        """
        try:
            await self.get_balance_allowance()
            return True
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
