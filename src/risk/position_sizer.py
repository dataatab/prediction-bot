"""
Position Sizing for Market-Neutral Arbitrage

Calculates optimal position sizes that satisfy multiple constraints:
1. Maximum position size cap (e.g., $1000)
2. Maximum percentage of available balance (e.g., 2%)
3. Equal contract quantities for Yes and No sides (market-neutral)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.utils.config import TradingConfig

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PositionSize:
    """
    Calculated position size for an arbitrage trade.

    All monetary values are in dollars as Decimal for precision.

    Attributes:
        contracts: Number of contracts to buy (equal for Yes and No).
        yes_price: Price per Yes contract.
        no_price: Price per No contract.
        yes_cost: Total cost for Yes side.
        no_cost: Total cost for No side.
        total_cost: Combined cost of Yes + No.
        expected_payout: Expected payout at settlement ($1 per contract).
        expected_profit: Expected profit (payout - total_cost).
        profit_margin: Profit as percentage of cost.
        constraint_triggered: Which constraint limited the size.
    """

    contracts: int
    yes_price: Decimal
    no_price: Decimal
    yes_cost: Decimal
    no_cost: Decimal
    total_cost: Decimal
    expected_payout: Decimal
    expected_profit: Decimal
    profit_margin: Decimal
    constraint_triggered: str

    def is_viable(self) -> bool:
        """Check if this position is viable (has positive contracts and profit)."""
        return self.contracts > 0 and self.expected_profit > 0

    def __str__(self) -> str:
        return (
            f"PositionSize({self.contracts} contracts, "
            f"Yes@{self.yes_price}, No@{self.no_price}, "
            f"cost=${self.total_cost}, profit=${self.expected_profit}, "
            f"margin={self.profit_margin:.2%}, "
            f"limited_by={self.constraint_triggered})"
        )


class PositionSizerError(Exception):
    """Base exception for position sizer errors."""

    pass


class InsufficientBalanceError(PositionSizerError):
    """Raised when balance is insufficient for minimum position."""

    pass


class InvalidPriceError(PositionSizerError):
    """Raised when prices are invalid for arbitrage."""

    pass


class PositionSizer:
    """
    Calculates position sizes for market-neutral arbitrage.

    Enforces multiple constraints to manage risk:
    1. Total cost (yes + no) <= max_position_size_usd (hard cap)
    2. Total cost <= max_balance_percent of available balance
    3. Equal contract quantities for Yes and No (market-neutral)

    The position size is determined by the most restrictive constraint.

    Example:
        >>> sizer = PositionSizer(config)
        >>> position = sizer.calculate_position(
        ...     yes_price=Decimal("0.45"),
        ...     no_price=Decimal("0.53"),
        ...     available_balance=Decimal("10000"),
        ... )
        >>> print(f"Buy {position.contracts} contracts")
        >>> print(f"Expected profit: ${position.expected_profit}")
    """

    # Standard payout per contract in prediction markets
    PAYOUT_PER_CONTRACT = Decimal("1.00")

    # Minimum contracts to make a trade worthwhile
    MIN_CONTRACTS = 1

    def __init__(self, config: TradingConfig) -> None:
        """
        Initialize the position sizer.

        Args:
            config: Trading configuration with position limits.
        """
        self._max_position_usd = Decimal(str(config.max_position_size_usd))
        self._max_balance_percent = Decimal(str(config.max_balance_percent))

    def calculate_position(
        self,
        yes_price: Decimal,
        no_price: Decimal,
        available_balance: Decimal,
    ) -> PositionSize:
        """
        Calculate optimal position size for an arbitrage opportunity.

        Args:
            yes_price: Ask price for Yes contract (e.g., 0.45 for 45¢).
            no_price: Ask price for No contract (e.g., 0.53 for 53¢).
            available_balance: Available balance in dollars.

        Returns:
            PositionSize with calculated quantities and costs.

        Raises:
            InvalidPriceError: If prices are outside valid range.
            InsufficientBalanceError: If balance is too low for minimum position.

        Example:
            >>> position = sizer.calculate_position(
            ...     yes_price=Decimal("0.45"),
            ...     no_price=Decimal("0.53"),
            ...     available_balance=Decimal("10000"),
            ... )
        """
        # Validate prices
        self._validate_prices(yes_price, no_price)

        # Calculate cost per pair (one Yes + one No)
        cost_per_pair = yes_price + no_price

        # Calculate max cost from each constraint
        max_from_cap = self._max_position_usd
        max_from_balance = available_balance * self._max_balance_percent

        # Use the most restrictive constraint
        if max_from_cap <= max_from_balance:
            max_cost = max_from_cap
            constraint = "position_cap"
        else:
            max_cost = max_from_balance
            constraint = "balance_percent"

        log = logger.bind(
            yes_price=float(yes_price),
            no_price=float(no_price),
            available_balance=float(available_balance),
            max_from_cap=float(max_from_cap),
            max_from_balance=float(max_from_balance),
            max_cost=float(max_cost),
            constraint=constraint,
        )

        # Calculate number of contracts (equal quantity for both sides)
        # Use floor division to ensure we don't exceed max cost
        contracts = int((max_cost / cost_per_pair).to_integral_value(rounding=ROUND_DOWN))

        # Check minimum viable position
        if contracts < self.MIN_CONTRACTS:
            min_required = cost_per_pair * self.MIN_CONTRACTS
            log.warning(
                "Insufficient funds for minimum position",
                min_required=float(min_required),
                contracts=contracts,
            )
            # Return zero-position instead of raising to allow caller to handle gracefully
            return self._create_position(
                contracts=0,
                yes_price=yes_price,
                no_price=no_price,
                constraint="insufficient_funds",
            )

        log.debug(
            "Position calculated",
            contracts=contracts,
            total_cost=float(contracts * cost_per_pair),
        )

        return self._create_position(
            contracts=contracts,
            yes_price=yes_price,
            no_price=no_price,
            constraint=constraint,
        )

    def calculate_max_contracts(
        self,
        yes_price: Decimal,
        no_price: Decimal,
        available_balance: Decimal,
    ) -> int:
        """
        Calculate maximum number of contracts that can be purchased.

        This is a convenience method that returns just the contract count.

        Args:
            yes_price: Ask price for Yes contract.
            no_price: Ask price for No contract.
            available_balance: Available balance in dollars.

        Returns:
            Maximum number of contracts (equal for both sides).
        """
        position = self.calculate_position(yes_price, no_price, available_balance)
        return position.contracts

    def validate_opportunity(
        self,
        yes_price: Decimal,
        no_price: Decimal,
        min_profit_margin: Decimal = Decimal("0.001"),
    ) -> bool:
        """
        Check if prices represent a valid arbitrage opportunity.

        Args:
            yes_price: Ask price for Yes contract.
            no_price: Ask price for No contract.
            min_profit_margin: Minimum profit margin required.

        Returns:
            True if opportunity exists (Yes + No < $1.00 - margin).
        """
        total_cost = yes_price + no_price
        profit = self.PAYOUT_PER_CONTRACT - total_cost
        margin = profit / total_cost if total_cost > 0 else Decimal("0")

        return profit > 0 and margin >= min_profit_margin

    def _validate_prices(self, yes_price: Decimal, no_price: Decimal) -> None:
        """Validate that prices are within acceptable bounds."""
        if yes_price <= 0 or yes_price >= 1:
            raise InvalidPriceError(f"Yes price must be between 0 and 1, got {yes_price}")

        if no_price <= 0 or no_price >= 1:
            raise InvalidPriceError(f"No price must be between 0 and 1, got {no_price}")

        total = yes_price + no_price
        if total >= self.PAYOUT_PER_CONTRACT:
            raise InvalidPriceError(
                f"No arbitrage opportunity: Yes ({yes_price}) + No ({no_price}) = {total} >= $1.00"
            )

    def _create_position(
        self,
        contracts: int,
        yes_price: Decimal,
        no_price: Decimal,
        constraint: str,
    ) -> PositionSize:
        """Create a PositionSize from calculated values."""
        contracts_dec = Decimal(contracts)

        yes_cost = contracts_dec * yes_price
        no_cost = contracts_dec * no_price
        total_cost = yes_cost + no_cost
        expected_payout = contracts_dec * self.PAYOUT_PER_CONTRACT
        expected_profit = expected_payout - total_cost

        # Calculate profit margin (avoid division by zero)
        if total_cost > 0:
            profit_margin = expected_profit / total_cost
        else:
            profit_margin = Decimal("0")

        return PositionSize(
            contracts=contracts,
            yes_price=yes_price,
            no_price=no_price,
            yes_cost=yes_cost,
            no_cost=no_cost,
            total_cost=total_cost,
            expected_payout=expected_payout,
            expected_profit=expected_profit,
            profit_margin=profit_margin,
            constraint_triggered=constraint,
        )


def create_position_sizer(config: TradingConfig | None = None) -> PositionSizer:
    """
    Factory function to create a PositionSizer.

    Args:
        config: Trading configuration. If None, loads from settings.

    Returns:
        Configured PositionSizer instance.
    """
    if config is None:
        from src.utils.config import get_settings

        settings = get_settings()
        config = settings.trading

    return PositionSizer(config)
