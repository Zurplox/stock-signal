# ⚡ Day-Trading Signal Engine

A non-stop intraday co-pilot. It watches the tickers you choose, analyzes each
one every cycle on **5-minute bars**, and tells you **BUY / SELL / HOLD** with a
built-in risk plan. It writes a **live dashboard** (`report.html`) that
auto-refreshes in your browser, and prints an **alert** whenever a ticker's
signal flips.

> **Educational use only — not financial advice.** Day trading is high risk.
> The tool never places trades; you stay in full control. Always use a stop-loss.

---

## The 6 steps it runs on every ticker, every cycle

1. **Scan** – pull fresh intraday (5-min) data + the SPY benchmark.
2. **Trend** – VWAP (above/below) and EMA9 vs EMA20.
3. **Momentum** – RSI(14), MACD, relative volume, 30-min opening-range breakout.
4. **Relative strength** – today's move vs SPY.
5. **Risk engine** – ATR-based stop, 2:1 target, position size so one loss ≈ 1% of your account.
6. **Decision** – a weighted score → BUY / SELL / HOLD.

---

## Run it (this is the best way for non-stop day trading)

```bash
pip install -r requirements.txt

# loop forever, refresh every 60s (default), watch these tickers:
python day_trader.py TSLA AAPL NVDA MSFT
```

Then open **`report.html`** in your browser. It refreshes itself — keep it on a
second monitor. Press **Ctrl+C** in the terminal to stop.

### Options

```bash
python day_trader.py --interval 30 TSLA AAPL   # refresh every 30 seconds
python day_trader.py --bar 1m TSLA             # use 1-minute bars
python day_trader.py --once TSLA               # single pass, then exit
```

### Make it yours (top of `day_trader.py`)

| Setting | Default | Meaning |
|---|---|---|
| `ACCOUNT_SIZE` | `10_000` | your capital |
| `RISK_PER_TRADE` | `0.01` | risk 1% per trade (safest) |
| `MIN_RR` | `2.0` | reward:risk target |
| `ATR_MULT` | `1.5` | how tight the stop is |
| `BAR` | `5m` | intraday bar size |

---

## Local vs GitHub — which should I use?

**For non-stop day trading, run locally.** GitHub Actions cannot run truly
continuously (its schedule fires at most every ~5 minutes and is often delayed),
so it can't keep up with fast intraday moves.

The included workflow (`.github/workflows/daily.yml`) is an optional cloud
fallback: during US market hours it runs one pass every ~5 minutes and commits
`report.html`. Handy if your computer is off, but the local loop is faster and
more reliable for active trading.

---

## Upload to GitHub (optional)

1. Create a new empty repo (e.g. `day-trader`).
2. **Add file → Upload files** → drag in everything from this folder → **Commit**.
3. To use the cloud fallback: **Actions** tab → enable workflows → **Run workflow**.
4. (Optional) enable **Settings → Pages** to view `report.html` online.

---

## How to read a card

- **Score** – higher = stronger long setup. BUY needs a strong score *and* price above VWAP.
- **Chips** – green = supportive (Above VWAP, EMA9>EMA20, MACD↑, ORB breakout, Beats SPY).
- **Price plan** – Stop (red) · Entry (blue) · Target (green), sized to a 2:1 reward:risk.
- **Risk footer** – shares to buy, position value, and max loss (≈1% of your account).
