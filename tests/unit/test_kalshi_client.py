"""
Unit tests for KalshiClient class.

Tests async HTTP client for Kalshi API including
balance fetching and authentication.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.clients.kalshi_client import (
    KalshiAPIError,
    KalshiAuthenticationError,
    KalshiBalance,
    KalshiClient,
    KalshiClientError,
)


@pytest.fixture
def mock_signer() -> MagicMock:
    """Create a mock KalshiSigner."""
    signer = MagicMock()
    signer.sign_request.return_value = {
        "KALSHI-ACCESS-KEY": "test-key",
        "KALSHI-ACCESS-SIGNATURE": "test-sig",
        "KALSHI-ACCESS-TIMESTAMP": "1234567890",
    }
    return signer


class TestKalshiBalance:
    """Tests for KalshiBalance data class."""

    def test_balance_conversion_from_cents(self) -> None:
        """Should convert cents to dollars correctly."""
        balance = KalshiBalance(
            balance_cents=100000,  # $1,000.00
            portfolio_value_cents=50000,  # $500.00
            payout_cents=25000,  # $250.00
        )

        assert balance.balance == Decimal("1000.00")
        assert balance.portfolio_value == Decimal("500.00")
        assert balance.payout == Decimal("250.00")

    def test_balance_handles_small_amounts(self) -> None:
        """Should handle small cent amounts correctly."""
        balance = KalshiBalance(
            balance_cents=1,  # $0.01
            portfolio_value_cents=0,
            payout_cents=0,
        )

        assert balance.balance == Decimal("0.01")

    def test_balance_repr(self) -> None:
        """Should have useful string representation."""
        balance = KalshiBalance(
            balance_cents=100000,
            portfolio_value_cents=50000,
            payout_cents=0,
        )

        repr_str = repr(balance)
        assert "1000" in repr_str
        assert "500" in repr_str


class TestKalshiClientInit:
    """Tests for KalshiClient initialization."""

    def test_init_with_demo_mode(self, mock_signer: MagicMock) -> None:
        """Should use demo URL by default."""
        client = KalshiClient(mock_signer, use_demo=True)
        assert "demo" in client._base_url

    def test_init_with_prod_mode(self, mock_signer: MagicMock) -> None:
        """Should use prod URL when specified."""
        client = KalshiClient(mock_signer, use_demo=False)
        assert "trading-api.kalshi.com" in client._base_url

    def test_init_with_custom_url(self, mock_signer: MagicMock) -> None:
        """Should use custom URL when provided."""
        client = KalshiClient(mock_signer, base_url="https://custom.api.com")
        assert client._base_url == "https://custom.api.com"

    def test_init_strips_trailing_slash(self, mock_signer: MagicMock) -> None:
        """Should strip trailing slash from URL."""
        client = KalshiClient(mock_signer, base_url="https://api.com/")
        assert not client._base_url.endswith("/")


class TestKalshiClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_enter_creates_client(self, mock_signer: MagicMock) -> None:
        """Should create httpx client on enter."""
        client = KalshiClient(mock_signer)
        assert client._client is None

        async with client as c:
            assert c._client is not None
            assert isinstance(c._client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_exit_closes_client(self, mock_signer: MagicMock) -> None:
        """Should close client on exit."""
        client = KalshiClient(mock_signer)

        async with client:
            pass

        assert client._client is None

    @pytest.mark.asyncio
    async def test_raises_without_context_manager(
        self, mock_signer: MagicMock
    ) -> None:
        """Should raise if used without context manager."""
        client = KalshiClient(mock_signer)

        with pytest.raises(KalshiClientError, match="not initialized"):
            await client.get_balance()


class TestKalshiClientGetBalance:
    """Tests for get_balance method."""

    @pytest.mark.asyncio
    async def test_get_balance_success(self, mock_signer: MagicMock) -> None:
        """Should return KalshiBalance on success."""
        mock_response = httpx.Response(
            200,
            json={
                "balance": 100000,
                "portfolio_value": 50000,
                "payout": 25000,
            },
        )

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                balance = await client.get_balance()

            assert isinstance(balance, KalshiBalance)
            assert balance.balance == Decimal("1000.00")

    @pytest.mark.asyncio
    async def test_get_balance_includes_auth_headers(
        self, mock_signer: MagicMock
    ) -> None:
        """Should include authentication headers in request."""
        mock_response = httpx.Response(200, json={"balance": 0})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                await client.get_balance()

            # Verify signer was called with correct method and path
            mock_signer.sign_request.assert_called_with(
                "GET", "/trade-api/v2/portfolio/balance"
            )

            # Verify headers were included in request
            call_kwargs = mock_request.call_args.kwargs
            assert "KALSHI-ACCESS-KEY" in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_get_balance_handles_missing_fields(
        self, mock_signer: MagicMock
    ) -> None:
        """Should handle missing fields in response."""
        mock_response = httpx.Response(200, json={})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                balance = await client.get_balance()

            assert balance.balance == Decimal("0")


class TestKalshiClientErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_authentication_error(self, mock_signer: MagicMock) -> None:
        """Should raise KalshiAuthenticationError on 401."""
        mock_response = httpx.Response(401, json={"error": "Unauthorized"})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                with pytest.raises(KalshiAuthenticationError):
                    await client.get_balance()

    @pytest.mark.asyncio
    async def test_api_error(self, mock_signer: MagicMock) -> None:
        """Should raise KalshiAPIError on 4xx/5xx."""
        mock_response = httpx.Response(400, json={"error": "Bad Request"})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                with pytest.raises(KalshiAPIError) as exc_info:
                    await client.get_balance()

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_error(self, mock_signer: MagicMock) -> None:
        """Should raise KalshiClientError on request failure."""
        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = httpx.RequestError("Connection failed")

            async with KalshiClient(mock_signer) as client:
                with pytest.raises(KalshiClientError, match="Request failed"):
                    await client.get_balance()


class TestKalshiClientGetAvailableBalance:
    """Tests for get_available_balance convenience method."""

    @pytest.mark.asyncio
    async def test_returns_decimal(self, mock_signer: MagicMock) -> None:
        """Should return just the balance as Decimal."""
        mock_response = httpx.Response(
            200,
            json={"balance": 100000, "portfolio_value": 50000, "payout": 0},
        )

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                balance = await client.get_available_balance()

            assert balance == Decimal("1000.00")
            assert isinstance(balance, Decimal)


class TestKalshiClientHealthCheck:
    """Tests for health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_signer: MagicMock) -> None:
        """Should return True on successful balance fetch."""
        mock_response = httpx.Response(200, json={"balance": 0})

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                is_healthy = await client.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_signer: MagicMock) -> None:
        """Should return False on failure."""
        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = httpx.RequestError("Failed")

            async with KalshiClient(mock_signer) as client:
                is_healthy = await client.health_check()

            assert is_healthy is False


class TestKalshiClientGetMarket:
    """Tests for get_market method."""

    @pytest.mark.asyncio
    async def test_get_market_success(self, mock_signer: MagicMock) -> None:
        """Should return market data."""
        mock_response = httpx.Response(
            200,
            json={
                "market": {
                    "ticker": "TEST-MARKET",
                    "title": "Test Market",
                    "yes_bid": 45,
                    "no_bid": 53,
                }
            },
        )

        with patch.object(
            httpx.AsyncClient, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            async with KalshiClient(mock_signer) as client:
                market = await client.get_market("TEST-MARKET")

            assert market["ticker"] == "TEST-MARKET"
