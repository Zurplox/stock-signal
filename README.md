# Stock Signal 📈

Automated 6-step stock analysis that turns a ticker (e.g. `TSLA`) into a
**BUY / SELL / HOLD** recommendation with a built-in risk plan (entry, stop-loss,
target, position size, and max loss).

> ⚠️ **Educational use only. Not financial advice.** Signals are decision-support,
> not guarantees. Backtest first, start with tiny position sizes, and never risk
> money you can't afford to lose. Always use a stop-loss.

## What it does (the 6 steps)

1. **Scan / ingest** – pulls ~2 years of daily price data for the ticker and SPY.
2. **Trend analysis** – 50/150/200-day moving averages, Minervini Trend Template,
   and Weinstein market phase (1–4).
3. **Momentum analysis** – RSI(14), MACD, and volume confirmation.
4. **Relative strength** – compares the stock's 3-month return vs SPY.
5. **Risk engine** – ATR-based stop-loss, 1% account-risk position sizing, and a
   minimum 2:1 reward/risk check.
6. **Decision** – combines everything into a weighted score → BUY / SELL / HOLD.

## Setup

You need [Python 3.10+](https://www.python.org/downloads/) installed.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run it
python stock_signal.py TSLA

# Analyze several at once
python stock_signal.py TSLA AAPL NVDA
```

## Configure your risk (top of `stock_signal.py`)

| Setting | Meaning | Default |
|---|---|---|
| `ACCOUNT_SIZE` | Your total capital | `10_000` |
| `RISK_PER_TRADE` | Fraction of account risked per trade | `0.01` (1%) |
| `MIN_RR` | Minimum reward-to-risk ratio to allow a BUY | `2.0` |
| `ATR_MULT` | Stop-loss distance = this × ATR | `2.0` |
| `BENCHMARK` | Market benchmark for relative strength | `"SPY"` |

## Automate it for free (GitHub Actions)

This repo includes `.github/workflows/daily.yml`, which runs the scan every
weekday after the US market close and commits a `report.txt` to the repo.

1. Push this repo to GitHub.
2. Go to **Settings → Actions → General → Workflow permissions** and enable
   **Read and write permissions** (so it can commit the report).
3. Edit the ticker list on the `python stock_signal.py ...` line in the workflow.
4. Trigger it anytime from the **Actions** tab → **Daily stock signals** →
   **Run workflow**.

## Example output

```
============================================================
 TSLA  ->  HOLD / WAIT   (score 6)
============================================================
 Phase:            Phase 2 (uptrend)
 Trend template:   6/7 criteria passed
 RSI(14):          58.3   MACD bullish: True   Vol confirm: False
 Rel. strength 3m: stock 12.4% vs SPY 4.1%  (outperform: True)
 --- Risk plan (risk 1% of $10,000) ---
 Entry: $250.12   Stop: $232.40   Target: $285.56
 Reward:Risk: 2.0:1   Buy 5 shares ($1,250.60)
 Max loss if stopped out: $100.0
```

## Ideas for later

- Send the report to Telegram / email / Slack.
- Add fundamentals (revenue/EPS growth, margins) as an extra filter.
- Add news/sentiment analysis.
- Backtest the rules on history with `backtesting.py` or `backtrader`.

## License

MIT
