# Prediction Bot

A high-frequency trading bot that exploits **negative spread arbitrage** on prediction markets. The bot identifies pricing inefficiencies where the combined cost of purchasing all mutually exclusive outcomes of a binary event is less than the guaranteed $1.00 payout.

## Strategy

The bot is **market-neutral** — it does not take directional bets on event outcomes. Instead, it scalps structural arbitrage:

```
Yes Price + No Price + Fees < $1.00 Payout
```

**Example:** Buy Yes at $0.45 + No at $0.53 = $0.98 total cost → $0.02 guaranteed profit per contract.

### Supported Venues

| Venue | Type | Settlement | Auth |
|---|---|---|---|
| **Kalshi** | US-regulated DCM (CLOB) | Cash ($1.00) | RSA-2048 signed requests |
| **Polymarket** | DeFi on Polygon (CTF) | USDC via merge/redeem | EIP-712 signatures |

### Arbitrage Modes

- **Intra-market** (primary): Buy both legs on the same venue. On Polymarket, instantly lock profit via `mergePositions()` on the CTF contract — no need to wait for event settlement.
- **Cross-platform** (restricted): Buy legs across Kalshi and Polymarket. Higher risk due to resolution mismatches and capital fragmentation.

## Architecture

The bot uses an **asyncio reactor pattern** with these core components:

```
WebSocket Feeds → Market Data Gateway → Strategy Engine → Risk Engine → Execution Gateway
                                              ↑                              ↓
                                         Gas Oracle                    Signer (RSA/EIP-712)
                                                                           ↓
                                                                   Hedger (on failure)
```

- **Market Data Gateway** — Normalizes Kalshi deltas and Polymarket orderbooks into a unified internal format
- **Strategy Engine** — Calculates minimum viable spread (MVS) with dynamic fee awareness (e.g., Polymarket's 3% fee on 15-min crypto markets)
- **Risk Engine** — Enforces capital limits, position caps (2% of balance per trade), and prevents orphaned legs
- **Position Sizer** — Computes optimal contract quantities under multiple constraints (hard cap, balance %, market-neutral pairing)
- **Execution Gateway** — Handles FOK orders on Polymarket and limit orders on Kalshi
- **Hedger** — Fade/chase logic for failed second-leg fills

### Kalshi Order Book Insight

Kalshi only exposes Yes Bids and No Bids. The bot synthetically constructs the Ask side:

```python
Ask_Yes = (100 - Bid_No) / 100
Ask_No  = (100 - Bid_Yes) / 100
```

## Tech Stack

- **Python 3.11+** with `uvloop`
- **httpx** — async HTTP client
- **web3.py** — Polygon CTF interaction (merge/split/redeem)
- **cryptography** — RSA-2048 signing for Kalshi
- **structlog** — JSON structured logging for latency analysis
- **Pydantic Settings** — typed configuration from environment variables
- **PostgreSQL** (asyncpg + SQLAlchemy) — trade persistence
- **FastAPI** — control plane API

## Project Structure

```
src/
├── clients/          # API clients (Kalshi, Polymarket)
├── gateways/         # Market data ingestion & order execution
├── models/           # OrderBook, Trade data models
├── risk/             # Risk engine, position sizer, hedger
├── signers/          # RSA (Kalshi) and EIP-712 (Polymarket) signers
├── strategies/       # Negative spread strategy
├── utils/            # Config, logging
├── web3_services/    # CTF merge/split, gas oracle
└── main.py
tests/
├── unit/
└── integration/
```

## Setup

1. **Clone and install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp exampleenv.txt .env
   # Fill in your API keys, private keys, and database URL
   ```

3. **Generate Kalshi RSA keys** (if needed):
   ```python
   from src.signers.kalshi_signer import generate_key_pair
   private_pem, public_pem = generate_key_pair()
   # Upload public_pem to Kalshi dashboard
   ```

4. **Run:**
   ```bash
   python -m src.main
   ```

## Configuration

Key environment variables (see `exampleenv.txt` for full list):

| Variable | Description |
|---|---|
| `KALSHI_API_KEY` | Kalshi API key (member ID) |
| `KALSHI_PRIVATE_KEY_PATH` | Path to RSA private key PEM file |
| `POLY_PRIVATE_KEY` | Ethereum private key for Polymarket |
| `POLYGON_RPC_URL` | Polygon RPC endpoint |
| `DATABASE_URL` | PostgreSQL connection string |
| `MIN_SPREAD_CENTS` | Minimum spread to trade (default: 2) |
| `MAX_POSITION_SIZE` | Max position size in USD (default: 1000) |
| `ENABLE_LIVE_TRADING` | Set `true` to enable real trades |

## Testing

```bash
pytest
pytest --cov=src
```

## License

Private — All rights reserved.
