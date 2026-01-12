"""
Unit tests for PositionSizer class.

Tests position sizing with multiple constraints:
- Maximum position cap ($1000)
- Maximum balance percentage (2%)
- Equal contract quantities
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.risk.position_sizer import (
    InvalidPriceError,
    PositionSize,
    PositionSizer,
    create_position_sizer,
)


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock TradingConfig."""
    config = MagicMock()
    config.max_position_size_usd = 1000.0
    config.max_balance_percent = 0.02  # 2%
    return config


@pytest.fixture
def sizer(mock_config: MagicMock) -> PositionSizer:
    """Create a PositionSizer with mock config."""
    return PositionSizer(mock_config)


class TestPositionSizerBasic:
    """Basic functionality tests."""

    def test_init_with_config(self, mock_config: MagicMock) -> None:
        """Should initialize with configuration values."""
        sizer = PositionSizer(mock_config)
        assert sizer._max_position_usd == Decimal("1000")
        assert sizer._max_balance_percent == Decimal("0.02")

    def test_calculate_position_returns_position_size(
        self, sizer: PositionSizer
    ) -> None:
        """Should return a PositionSize object."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )
        assert isinstance(position, PositionSize)


class TestPositionCapConstraint:
    """Tests for the $1000 position cap constraint."""

    def test_cap_triggers_with_high_balance(self, sizer: PositionSizer) -> None:
        """With high balance, the $1000 cap should be the limiting factor."""
        # 2% of $100,000 = $2,000 > $1,000 cap
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        # Cost per pair = 0.98, max cost = $1000
        # Max contracts = floor(1000 / 0.98) = 1020
        assert position.contracts == 1020
        assert position.constraint_triggered == "position_cap"
        assert position.total_cost <= Decimal("1000")

    def test_cap_exact_boundary(self, sizer: PositionSizer) -> None:
        """Test at exact boundary where cap equals balance percentage."""
        # 2% of $50,000 = $1,000 (exactly equals cap)
        position = sizer.calculate_position(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.48"),
            available_balance=Decimal("50000"),
        )

        # Both constraints give $1000, cap wins tie
        assert position.constraint_triggered == "position_cap"


class TestBalancePercentConstraint:
    """Tests for the 2% balance constraint."""

    def test_balance_percent_triggers_with_low_balance(
        self, sizer: PositionSizer
    ) -> None:
        """With low balance, the 2% constraint should be the limiting factor."""
        # 2% of $10,000 = $200 < $1,000 cap
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("10000"),
        )

        # Cost per pair = 0.98, max cost = $200
        # Max contracts = floor(200 / 0.98) = 204
        assert position.contracts == 204
        assert position.constraint_triggered == "balance_percent"
        assert position.total_cost <= Decimal("200")

    def test_balance_percent_very_low_balance(self, sizer: PositionSizer) -> None:
        """Very low balance should result in few contracts."""
        # 2% of $500 = $10
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("500"),
        )

        # Cost per pair = 0.98, max cost = $10
        # Max contracts = floor(10 / 0.98) = 10
        assert position.contracts == 10
        assert position.constraint_triggered == "balance_percent"


class TestEqualContractQuantities:
    """Tests for equal Yes/No contract quantities."""

    def test_equal_contracts_for_both_sides(self, sizer: PositionSizer) -> None:
        """Yes and No should have equal contract quantities."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        # Both sides get same number of contracts
        yes_contracts = position.yes_cost / position.yes_price
        no_contracts = position.no_cost / position.no_price

        assert yes_contracts == no_contracts
        assert yes_contracts == position.contracts

    def test_asymmetric_prices_equal_contracts(self, sizer: PositionSizer) -> None:
        """Even with very asymmetric prices, contracts should be equal."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.10"),  # Very cheap
            no_price=Decimal("0.88"),  # Very expensive
            available_balance=Decimal("100000"),
        )

        yes_contracts = position.yes_cost / position.yes_price
        no_contracts = position.no_cost / position.no_price

        assert yes_contracts == no_contracts

    def test_costs_differ_but_contracts_equal(self, sizer: PositionSizer) -> None:
        """Dollar costs will differ, but contract counts should match."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.30"),
            no_price=Decimal("0.68"),
            available_balance=Decimal("100000"),
        )

        # Costs should be different (proportional to prices)
        assert position.yes_cost != position.no_cost

        # But contract counts should be equal
        assert position.yes_cost / position.yes_price == position.no_cost / position.no_price


class TestProfitCalculations:
    """Tests for profit and margin calculations."""

    def test_expected_payout_is_contracts_times_one(
        self, sizer: PositionSizer
    ) -> None:
        """Expected payout should be $1 per contract."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        assert position.expected_payout == Decimal(position.contracts)

    def test_profit_is_payout_minus_cost(self, sizer: PositionSizer) -> None:
        """Profit should be payout minus total cost."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        expected_profit = position.expected_payout - position.total_cost
        assert position.expected_profit == expected_profit

    def test_profit_margin_calculation(self, sizer: PositionSizer) -> None:
        """Profit margin should be profit / cost."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        expected_margin = position.expected_profit / position.total_cost
        assert position.profit_margin == expected_margin

    def test_wider_spread_higher_margin(self, sizer: PositionSizer) -> None:
        """Wider spreads should result in higher profit margins."""
        narrow_spread = sizer.calculate_position(
            yes_price=Decimal("0.49"),
            no_price=Decimal("0.50"),  # Total = 0.99
            available_balance=Decimal("100000"),
        )

        wide_spread = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.50"),  # Total = 0.95
            available_balance=Decimal("100000"),
        )

        assert wide_spread.profit_margin > narrow_spread.profit_margin


class TestInsufficientFunds:
    """Tests for insufficient balance scenarios."""

    def test_returns_zero_contracts_when_insufficient(
        self, sizer: PositionSizer
    ) -> None:
        """Should return zero contracts when balance is too low."""
        # 2% of $10 = $0.20, not enough for one pair at $0.98
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("10"),
        )

        assert position.contracts == 0
        assert position.constraint_triggered == "insufficient_funds"

    def test_is_viable_returns_false_for_zero_contracts(
        self, sizer: PositionSizer
    ) -> None:
        """is_viable() should return False when no contracts can be bought."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("10"),
        )

        assert not position.is_viable()

    def test_is_viable_returns_true_for_valid_position(
        self, sizer: PositionSizer
    ) -> None:
        """is_viable() should return True for valid positions."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        assert position.is_viable()


class TestPriceValidation:
    """Tests for price validation."""

    def test_raises_for_zero_yes_price(self, sizer: PositionSizer) -> None:
        """Should raise InvalidPriceError for zero Yes price."""
        with pytest.raises(InvalidPriceError, match="Yes price"):
            sizer.calculate_position(
                yes_price=Decimal("0"),
                no_price=Decimal("0.53"),
                available_balance=Decimal("100000"),
            )

    def test_raises_for_zero_no_price(self, sizer: PositionSizer) -> None:
        """Should raise InvalidPriceError for zero No price."""
        with pytest.raises(InvalidPriceError, match="No price"):
            sizer.calculate_position(
                yes_price=Decimal("0.45"),
                no_price=Decimal("0"),
                available_balance=Decimal("100000"),
            )

    def test_raises_for_price_equals_one(self, sizer: PositionSizer) -> None:
        """Should raise InvalidPriceError for price at $1."""
        with pytest.raises(InvalidPriceError, match="Yes price"):
            sizer.calculate_position(
                yes_price=Decimal("1"),
                no_price=Decimal("0.53"),
                available_balance=Decimal("100000"),
            )

    def test_raises_for_no_arbitrage(self, sizer: PositionSizer) -> None:
        """Should raise when sum of prices >= $1 (no arbitrage)."""
        with pytest.raises(InvalidPriceError, match="No arbitrage opportunity"):
            sizer.calculate_position(
                yes_price=Decimal("0.50"),
                no_price=Decimal("0.52"),  # Total = 1.02
                available_balance=Decimal("100000"),
            )

    def test_raises_for_negative_price(self, sizer: PositionSizer) -> None:
        """Should raise for negative prices."""
        with pytest.raises(InvalidPriceError):
            sizer.calculate_position(
                yes_price=Decimal("-0.10"),
                no_price=Decimal("0.53"),
                available_balance=Decimal("100000"),
            )


class TestValidateOpportunity:
    """Tests for the validate_opportunity helper method."""

    def test_valid_opportunity_returns_true(self, sizer: PositionSizer) -> None:
        """Should return True for valid arbitrage opportunity."""
        is_valid = sizer.validate_opportunity(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
        )
        assert is_valid

    def test_invalid_opportunity_returns_false(self, sizer: PositionSizer) -> None:
        """Should return False when prices sum to >= $1."""
        is_valid = sizer.validate_opportunity(
            yes_price=Decimal("0.50"),
            no_price=Decimal("0.51"),
        )
        assert not is_valid

    def test_respects_min_profit_margin(self, sizer: PositionSizer) -> None:
        """Should return False when margin is below minimum."""
        # Total = 0.995, profit = 0.005, margin = 0.005/0.995 ≈ 0.5%
        is_valid = sizer.validate_opportunity(
            yes_price=Decimal("0.495"),
            no_price=Decimal("0.500"),
            min_profit_margin=Decimal("0.01"),  # Require 1%
        )
        assert not is_valid


class TestCalculateMaxContracts:
    """Tests for the calculate_max_contracts helper method."""

    def test_returns_contract_count(self, sizer: PositionSizer) -> None:
        """Should return just the contract count."""
        contracts = sizer.calculate_max_contracts(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        assert isinstance(contracts, int)
        assert contracts == 1020  # Based on $1000 cap


class TestEdgeCases:
    """Edge case tests."""

    def test_very_small_spread(self, sizer: PositionSizer) -> None:
        """Should handle very small arbitrage spreads."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.495"),
            no_price=Decimal("0.500"),  # Total = 0.995
            available_balance=Decimal("100000"),
        )

        assert position.contracts > 0
        assert position.expected_profit > 0

    def test_extreme_price_asymmetry(self, sizer: PositionSizer) -> None:
        """Should handle extreme price asymmetry."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.01"),  # 1 cent
            no_price=Decimal("0.97"),  # 97 cents
            available_balance=Decimal("100000"),
        )

        assert position.contracts > 0
        # Verify equal contracts
        assert position.yes_cost / position.yes_price == position.no_cost / position.no_price


class TestPositionSizeDataclass:
    """Tests for the PositionSize dataclass."""

    def test_str_representation(self, sizer: PositionSizer) -> None:
        """Should have readable string representation."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        str_repr = str(position)
        assert "1020 contracts" in str_repr
        assert "position_cap" in str_repr

    def test_is_frozen_dataclass(self, sizer: PositionSizer) -> None:
        """PositionSize should be immutable (frozen)."""
        position = sizer.calculate_position(
            yes_price=Decimal("0.45"),
            no_price=Decimal("0.53"),
            available_balance=Decimal("100000"),
        )

        with pytest.raises(AttributeError):
            position.contracts = 999  # type: ignore


class TestFactoryFunction:
    """Tests for the create_position_sizer factory function."""

    def test_creates_sizer_with_explicit_config(self, mock_config: MagicMock) -> None:
        """Should create sizer with provided config."""
        sizer = create_position_sizer(mock_config)
        assert isinstance(sizer, PositionSizer)
