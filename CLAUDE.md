# Prediction Bot - Agent Context

## What This Project Is
A market-neutral HFT bot that exploits negative spread arbitrage on prediction markets (Kalshi + Polymarket). It buys both Yes and No outcomes when their combined cost is less than the $1.00 guaranteed payout.

## Key Architecture Decisions
- Asyncio reactor pattern with uvloop
- Kalshi auth: RSA-2048 PSS signatures
- Polymarket auth: EIP-712 signatures on Polygon (chain ID 137)
- Polymarket profit lock: call `mergePositions()` on CTF contract to convert Yes+No back to USDC instantly
- Kalshi order book: Ask side is synthetic — `Ask_Yes = (100 - Bid_No) / 100`

## Reference Documents
Only read these when a task specifically requires API details or market-matching logic:
- Cross-venue event matching strategy (Kalshi Series vs Polymarket Tags, 3-layer reconciliation engine): `docs/research/Arbitrage API Event Matching Strategy.pdf`
- Full project strategy and architecture spec: `docs/PROJECT_CONTEXT.md`

## Code Conventions
- Python 3.11+, all I/O is async
- Type checking: mypy --strict
- Logging: structlog (JSON in prod, console in dev)
- Config: Pydantic Settings loaded from .env
- Testing: pytest + pytest-asyncio, target >80% coverage
- Monetary values: use Decimal, never float
- Prices in models: dollar-denominated Decimals (0.45 = 45 cents)

## Important Gotchas
- Kalshi No Bids can be null — treat as Ask = infinity, not 100
- Polymarket 15-min crypto markets have dynamic taker fees up to 3% — require 4-cent minimum spread
- Kalshi taker fees make intra-market scalping unprofitable in tight markets — prefer market making
- Cross-platform arb is restricted to a strict whitelist due to resolution mismatch risk
