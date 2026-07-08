"""
Automated 6-step stock analysis -> BUY / SELL / HOLD with risk management.
Usage:  python stock_signal.py TSLA
        python stock_signal.py TSLA AAPL NVDA
Educational use only. Not financial advice.
"""
import sys
import numpy as np
import pandas as pd
import yfinance as yf

# ---- Your settings (the "safest risk" knobs) -------------------------------
ACCOUNT_SIZE   = 10_000    # your total capital in your currency
RISK_PER_TRADE = 0.01      # risk 1% of account per trade (0.01 = safest, 0.02 = normal)
MIN_RR         = 2.0       # only BUY if reward:risk >= 2:1
ATR_MULT       = 2.0       # stop = entry - 2 * ATR
BENCHMARK      = "SPY"     # market benchmark for relative strength


# ---- Indicator helpers -----------------------------------------------------
def sma(s, n):        return s.rolling(n).mean()
def ema(s, n):        return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    delta = s.diff()
    gain  = delta.clip(lower=0).rolling(n).mean()
    loss  = (-delta.clip(upper=0)).rolling(n).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(s, fast=12, slow=26, signal=9):
    line = ema(s, fast) - ema(s, slow)
    sig  = ema(line, signal)
    return line, sig

def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


# ---- Step 1: Scan / ingest -------------------------------------------------
def fetch(ticker, period="2y"):
    df = yf.download(ticker, period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


# ---- Step 2: Trend (Minervini Trend Template + Weinstein phase) ------------
def trend_analysis(df):
    c = df["Close"]
    s50, s150, s200 = sma(c, 50), sma(c, 150), sma(c, 200)
    price = c.iloc[-1]
    low52, high52 = c.tail(252).min(), c.tail(252).max()
    s200_slope_up = s200.iloc[-1] > s200.iloc[-21]  # rising over ~1 month

    checks = {
        "Price > 150 & 200 SMA":      price > s150.iloc[-1] and price > s200.iloc[-1],
        "150 SMA > 200 SMA":          s150.iloc[-1] > s200.iloc[-1],
        "200 SMA rising >= 1 month":  bool(s200_slope_up),
        "50 > 150 > 200 SMA":         s50.iloc[-1] > s150.iloc[-1] > s200.iloc[-1],
        "Price > 50 SMA":             price > s50.iloc[-1],
        "Price >= 30% above 52w low": price >= low52 * 1.30,
        "Price within 25% of 52w high": price >= high52 * 0.75,
    }
    passed = sum(checks.values())

    # Weinstein phase (simplified)
    if s50.iloc[-1] > s150.iloc[-1] > s200.iloc[-1] and price > s50.iloc[-1]:
        phase = "Phase 2 (uptrend)"
    elif s50.iloc[-1] < s200.iloc[-1] and price < s200.iloc[-1]:
        phase = "Phase 4 (downtrend)"
    elif price < s50.iloc[-1] and s50.iloc[-1] > s200.iloc[-1]:
        phase = "Phase 3 (distribution)"
    else:
        phase = "Phase 1 (basing)"
    return checks, passed, phase


# ---- Step 3: Momentum ------------------------------------------------------
def momentum_analysis(df):
    c = df["Close"]
    r = rsi(c).iloc[-1]
    line, sig = macd(c)
    macd_bull = line.iloc[-1] > sig.iloc[-1]
    vol_confirm = df["Volume"].iloc[-1] > df["Volume"].tail(50).mean()
    return {"rsi": round(float(r), 1), "macd_bull": bool(macd_bull),
            "volume_confirm": bool(vol_confirm)}


# ---- Step 4: Relative strength vs benchmark --------------------------------
def relative_strength(df, bench):
    def ret(x): return x["Close"].iloc[-1] / x["Close"].iloc[-63] - 1  # ~3 months
    stock_r, bench_r = ret(df), ret(bench)
    return {"stock_3m": round(stock_r * 100, 1),
            "bench_3m": round(bench_r * 100, 1),
            "outperforming": bool(stock_r > bench_r)}


# ---- Step 5: Risk engine ---------------------------------------------------
def risk_engine(df):
    price = float(df["Close"].iloc[-1])
    a = float(atr(df).iloc[-1])
    stop = price - ATR_MULT * a
    risk_per_share = price - stop
    target = price + MIN_RR * risk_per_share
    dollars_at_risk = ACCOUNT_SIZE * RISK_PER_TRADE
    shares = int(dollars_at_risk / risk_per_share) if risk_per_share > 0 else 0
    return {"entry": round(price, 2), "stop": round(stop, 2),
            "target": round(target, 2), "risk_per_share": round(risk_per_share, 2),
            "reward_risk": MIN_RR, "shares": shares,
            "position_value": round(shares * price, 2),
            "max_loss": round(dollars_at_risk, 2)}


# ---- Step 6: Decision ------------------------------------------------------
def decide(passed, phase, mom, rs):
    score = 0
    score += passed                      # 0-7 from trend template
    score += 2 if "Phase 2" in phase else (-3 if "Phase 4" in phase else 0)
    score += 1 if mom["macd_bull"] else -1
    score += 1 if 40 <= mom["rsi"] <= 70 else (-1 if mom["rsi"] > 80 else 0)
    score += 1 if mom["volume_confirm"] else 0
    score += 2 if rs["outperforming"] else -1

    if score >= 9 and "Phase 2" in phase:
        return "BUY", score
    if score <= 2 or "Phase 4" in phase:
        return "SELL / AVOID", score
    return "HOLD / WAIT", score


# ---- Orchestrator ----------------------------------------------------------
def analyze(ticker, bench_df):
    df = fetch(ticker)
    if len(df) < 210:
        return f"{ticker}: not enough data."
    checks, passed, phase = trend_analysis(df)
    mom = momentum_analysis(df)
    rs  = relative_strength(df, bench_df)
    risk = risk_engine(df)
    action, score = decide(passed, phase, mom, rs)

    lines = [
        f"\n{'='*60}",
        f" {ticker}  ->  {action}   (score {score})",
        f"{'='*60}",
        f" Phase:            {phase}",
        f" Trend template:   {passed}/7 criteria passed",
        f" RSI(14):          {mom['rsi']}   MACD bullish: {mom['macd_bull']}   Vol confirm: {mom['volume_confirm']}",
        f" Rel. strength 3m: stock {rs['stock_3m']}% vs {BENCHMARK} {rs['bench_3m']}%  (outperform: {rs['outperforming']})",
        f" --- Risk plan (risk {RISK_PER_TRADE*100:.0f}% of ${ACCOUNT_SIZE:,}) ---",
        f" Entry: ${risk['entry']}   Stop: ${risk['stop']}   Target: ${risk['target']}",
        f" Reward:Risk: {risk['reward_risk']}:1   Buy {risk['shares']} shares (${risk['position_value']:,})",
        f" Max loss if stopped out: ${risk['max_loss']}",
    ]
    if action.startswith("BUY"):
        failed = ", ".join(k for k, v in checks.items() if not v)
        lines.append(" Failed checks: " + (failed or "none"))
    return "\n".join(lines)


def main():
    tickers = [t.upper() for t in sys.argv[1:]] or ["TSLA"]
    bench_df = fetch(BENCHMARK)
    for t in tickers:
        print(analyze(t, bench_df))
    print("\nEducational use only. Not financial advice. Always use a stop-loss.")


if __name__ == "__main__":
    main()
