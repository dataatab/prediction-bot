\# Prediction Bot - Project Context for Cursor AI



\## 1. Strategy \& Mathematical Constraints: The "Why"



\### 1.1 Executive Strategic Overview



This document functions as the comprehensive "Context Memory" for the Cursor AI Code Editor. It provides the architectural, mathematical, and operational boundaries required to plan and generate code for a High-Frequency Trading (HFT) bot. The specific target is the "Negative Spread" strategy—a structural arbitrage where the cumulative cost of purchasing all mutually exclusive outcomes of a binary event is less than the guaranteed payout.



The bot will operate across two distinct market venues:

\- \*\*Kalshi\*\*: A US-regulated Designated Contract Market (DCM)

\- \*\*Polymarket\*\*: A decentralized application (dApp) built on the Polygon blockchain utilizing the Gnosis Conditional Token Framework (CTF)



\*\*Primary Directive: Market Neutral Scalping\*\*



The bot does not take directional risk on event outcomes (e.g., "Will the Federal Reserve cut rates?"). Instead, it identifies pricing inefficiencies where the market implies a probability sum of less than 100%.



\*\*Example:\*\*

\- Yes price: $0.45

\- No price: $0.53

\- Total cost: $0.98

\- Guaranteed payout: $1.00

\- Theoretical profit: $0.02 per contract



\*\*The Fundamental Arbitrage Equation:\*\*

P\_Yes + P\_No + Fees\_Total < Payout\_Guaranteed



Where:

\- `P\_Yes` = executable Ask price for the 'Yes' contract

\- `P\_No` = executable Ask price for the 'No' contract

\- `Fees\_Total` = aggregate of exchange fees, gas fees (Polymarket), settlement fees, redemption costs

\- `Payout\_Guaranteed` = fixed settlement value (typically $1.00 or 1.00 USDC)



---



\### 1.2 Market Mechanics \& Microstructure



\#### 1.2.1 Kalshi (US Regulated Exchange)



\*\*Order Book Dynamics \& The "Implied Ask"\*\*



Kalshi utilizes a Central Limit Order Book (CLOB). The API returns distinct arrays for Yes Bids and No Bids but does NOT explicitly structure an "Ask" side.



\*\*Critical Insight:\*\* In a binary market, liquidity is reciprocal. A trader willing to buy 'No' at $0.40 is mathematically equivalent to a trader willing to sell 'Yes' at $0.60.



\*\*The bot must synthetically construct the Ask side:\*\*

```python

Ask\_Yes = 100 - Bid\_No  # in cents

Ask\_No = 100 - Bid\_Yes  # in cents

```



\*\*Fee Schedule (Taker Fee Formula):\*\*

```python

fee = round\_up(0.07 \* contracts \* P \* (1 - P))

```



For a contract at $0.50: fee ≈ $0.0175 per contract (effectively 3.5-4%)



\*\*Kalshi Minimum Viable Spread (MVS) Example:\*\*

Cost\_Total = 0.50 + 0.48 + 0.0175 + 0.0175 = 1.015

This trade LOSES money despite raw prices summing to $0.98. Intra-market taker scalping on Kalshi is prohibitive in tight markets.



\*\*Conclusion:\*\* The bot must prioritize Market Making on Kalshi.



---



\#### 1.2.2 Polymarket (DeFi / Polygon Network)



Polymarket operates as a hybrid system:

\- Off-chain CLOB for order matching

\- On-chain smart contracts for settlement



\*\*CTF Mechanics: Split, Merge, and Redeem\*\*



1\. \*\*Split:\*\* 1 USDC → 1 Yes + 1 No

2\. \*\*Merge:\*\* 1 Yes + 1 No → 1 USDC (ARBITRAGE MECHANISM)

3\. \*\*Redemption:\*\* Winning share → 1 USDC



\*\*The "Merge" Arbitrage Opportunity:\*\*



If the bot purchases 1 Yes and 1 No for 0.98 USDC, it can immediately call `mergePositions()` on the CTF contract to convert the pair back into 1.00 USDC, locking in profit instantly WITHOUT waiting for event expiry.



\*\*Fee Structures:\*\*



1\. \*\*Winner's Fee (Redemption Fee):\*\* 2% fee on winning shares upon redemption. Merging positions BYPASSES this fee.



2\. \*\*⚠️ CRITICAL WARNING: 15-Minute Crypto Markets\*\*

&nbsp;  

&nbsp;  Polymarket has introduced Dynamic Taker Fees specifically for short-term (15m, 1h) cryptocurrency markets to combat latency arbitrage.

&nbsp;  

&nbsp;  - \*\*Mechanism:\*\* Fee scales with probability. As price approaches 50¢, fee can spike to 3.0%

&nbsp;  - \*\*Implication:\*\* A "Negative Spread" of 2% is profitable on a political market (0% fee) but a GUARANTEED LOSS on a 15m BTC market (3% fee)

&nbsp;  

&nbsp;  \*\*Bot Logic Required:\*\*

```python

&nbsp;  if "crypto" in market.tags and "15m" in market.tags:

&nbsp;      MIN\_SPREAD = 0.04  # 4 cents minimum

```



---



\### 1.3 Arbitrage Strategies



\#### 1.3.1 Intra-Market Arbitrage (PRIMARY TARGET)



\- Buy both legs on the same venue

\- Low risk, high capital efficiency via merging

\- Requires Fill-Or-Kill (FOK) orders on Polymarket



\#### 1.3.2 Cross-Platform Arbitrage (Kalshi vs. Polymarket)



\- Buy Yes on Kalshi, No on Polymarket (or vice versa)

\- \*\*EXTREME RISK\*\* due to:

&nbsp; - Resolution mismatch (e.g., AP Call vs. Inauguration date)

&nbsp; - Capital fragmentation (cannot merge across chains)

\- \*\*Restricted to strict whitelist of atomic events\*\*



---



\## 2. Architecture \& Tech Stack



\### 2.1 Technical Architecture: The Reactor Pattern



We utilize an asyncio Reactor Pattern to handle high-throughput WebSocket streams.



\*\*Components:\*\*



1\. \*\*Market Data Gateway (MDG):\*\* Normalizes Kalshi "Deltas" and Polymarket "Orderbooks" into a standard internal object



2\. \*\*Strategy Engine:\*\* Calculates real-time MVS using gas oracles and dynamic fee lookups



3\. \*\*Risk Engine:\*\* Validates capital limits and prevents "Leg Risk" (orphaned positions)



4\. \*\*Execution Gateway:\*\* Handles EIP-712 signing (Polymarket) and RSA signing (Kalshi)



\### 2.2 Tech Stack



\- \*\*Language:\*\* Python 3.11+ with uvloop

\- \*\*Framework:\*\* FastAPI (Control Plane)

\- \*\*Database:\*\* PostgreSQL (Async SQLAlchemy) for persistence

\- \*\*Blockchain:\*\* web3.py (Async) for CTF interaction



\### 2.3 Architecture Diagram



┌─────────────────────────────────────────────────────────────────┐

│                     External Ecosystem                          │

│  ┌─────────────────┐              ┌─────────────────┐          │

│  │  Kalshi Platform │              │ Polymarket      │          │

│  └────────┬────────┘              └────────┬────────┘          │

└───────────┼────────────────────────────────┼────────────────────┘

│                                │

▼                                ▼

┌─────────────────────────────────────────────────────────────────┐

│                   Bot Core (Python uvloop)                      │

│                                                                 │

│  ┌──────────┐    ┌──────────┐    ┌──────────────┐              │

│  │ WS\_Kalshi│───▶│Normalizer│───▶│  OrderBook   │              │

│  └──────────┘    └──────────┘    │   (Unified)  │              │

│  ┌──────────┐         │          └──────┬───────┘              │

│  │ WS\_Poly  │─────────┘                 │                      │

│  └──────────┘                           ▼                      │

│                              ┌──────────────────┐              │

│  ┌──────────┐               │  Strategy Engine  │              │

│  │Gas Oracle│──────────────▶│  (MVS Calculator) │              │

│  └──────────┘               └────────┬──────────┘              │

│                                      │ Arb Signal              │

│                                      ▼                         │

│                              ┌──────────────────┐              │

│                              │   Risk Engine    │              │

│                              │ (Capital/Legs)   │              │

│                              └────────┬─────────┘              │

│                                       │ Approved               │

│                                       ▼                        │

│                              ┌──────────────────┐              │

│                              │     Signer       │              │

│                              │ (EIP-712 / RSA)  │              │

│                              └────────┬─────────┘              │

│                                       │                        │

│                                       ▼                        │

│  ┌──────────┐               ┌──────────────────┐              │

│  │  Hedger  │◀─── Fail ────│Execution Gateway │              │

│  │(Panic)   │               └────────┬─────────┘              │

│  └──────────┘                        │ Success                 │

│                                      ▼                         │

│                              ┌──────────────────┐              │

│                              │   DB Queue       │──▶ PostgreSQL│

│                              └──────────────────┘              │

└─────────────────────────────────────────────────────────────────┘



---



\## 3. API Interface Specifications



\### 3.1 Polymarket Interface (CLOB \& CTF)



\#### 3.1.1 Authentication \& Signing



Orders require EIP-712 signing. The bot must implement an `encode\_structured\_data` routine compatible with Polygon Chain ID 137.



\#### 3.1.2 The CTF "Merge" Implementation (CRUCIAL)



The standard py-clob-client does NOT handle `mergePositions` well. The bot must call the contract directly via web3.py.



\*\*Contract Addresses:\*\*

\- CTF Contract: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`

\- USDC Token: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`



\*\*Required ABI:\*\*

```json

\[

&nbsp; {

&nbsp;   "constant": false,

&nbsp;   "inputs": \[

&nbsp;     {"name": "collateralToken", "type": "address"},

&nbsp;     {"name": "parentCollectionId", "type": "bytes32"},

&nbsp;     {"name": "conditionId", "type": "bytes32"},

&nbsp;     {"name": "partition", "type": "uint256\[]"},

&nbsp;     {"name": "amount", "type": "uint256"}

&nbsp;   ],

&nbsp;   "name": "mergePositions",

&nbsp;   "outputs": \[],

&nbsp;   "payable": false,

&nbsp;   "stateMutability": "nonpayable",

&nbsp;   "type": "function"

&nbsp; }

]

```



\*\*Merge Logic:\*\*



1\. Approve CTF Contract to spend ERC-1155 tokens

2\. Call `mergePositions` with:

&nbsp;  - `parentCollectionId`: `0x0000000000000000000000000000000000000000000000000000000000000000`

&nbsp;  - `partition`: `\[1, 2]` (Standard Binary Yes/No slots)



---



\### 3.2 Kalshi Interface (v2 API)



\#### 3.2.1 Authentication



Requires RSA-2048 signing of: `timestamp + method + path`



\#### 3.2.2 API Gotchas \& Quirks



1\. \*\*Provisional Markets:\*\*

&nbsp;  - API returns `is\_provisional: true` for markets that may be delisted

&nbsp;  - \*\*Rule:\*\* `if market.is\_provisional: continue`



2\. \*\*The 100-Cent Rule \& Null Bids:\*\*

&nbsp;  - Formula: `Implied\_Yes\_Ask = 100 - no\_bid`

&nbsp;  - \*\*TRAP:\*\* If `no\_bid` is `null` (empty book), the formula breaks

&nbsp;  - \*\*Solution:\*\* Handle null by setting Ask to INFINITY, not 100

```python

&nbsp;  def get\_implied\_ask(no\_bid: Optional\[int]) -> float:

&nbsp;      if no\_bid is None:

&nbsp;          return float('inf')

&nbsp;      return (100 - no\_bid) / 100

```



---



\## 4. Implementation Phases



\### Phase 1: Connectivity \& Authentication

1\. Implement `PolySigner` (EIP-712)

2\. Implement `KalshiSigner` (RSA)

3\. Create basic HTTP clients to fetch one market from each venue to verify auth



\### Phase 2: Data Ingestion

1\. Build `MarketDataGateway` with websockets

2\. Implement `OrderBook` class with `KalshiAdapter` for "Implied Ask" inversion logic



\### Phase 3: Strategy \& Risk

1\. Implement `NegativeSpreadStrategy` with dynamic fee logic for crypto markets

2\. Implement `RiskEngine` to block trades if open legs exist

3\. Implement `Hedger` logic (Fade/Chase) for failed legs



\### Phase 4: Execution \& Persistence

1\. Build `ExecutionGateway` handling FOK orders on Polymarket and Limit orders on Kalshi

2\. Implement Web3 service for calling `mergePositions` on Polygon chain

3\. Connect SQLAlchemy for trade logging



---



\## 5. Code Standards



\- \*\*Type Checking:\*\* Enforce `mypy --strict` mode

\- \*\*Logging:\*\* Use `structlog` for JSON logging (latency analysis)

\- \*\*Async:\*\* All I/O operations must be async

\- \*\*Testing:\*\* pytest with >80% coverage target



---



\## 6. Key Constants Reference

```python

\# Contract Addresses (Polygon Mainnet)

CTF\_CONTRACT = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

USDC\_TOKEN = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

POLYGON\_CHAIN\_ID = 137



\# Fee Constants

KALSHI\_TAKER\_FEE\_RATE = 0.07

POLYMARKET\_WINNER\_FEE = 0.02

CRYPTO\_15M\_MAX\_FEE = 0.03



\# Trading Constants

BINARY\_PAYOUT = 1.00  # $1.00 or 1 USDC

MERGE\_PARENT\_COLLECTION\_ID = bytes(32)  # 32 zero bytes

BINARY\_PARTITION = \[1, 2]  # Yes=1, No=2

```

