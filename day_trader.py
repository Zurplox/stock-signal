"""
Day-trading signal engine -- non-stop intraday analysis.

Runs the 6-step analysis on INTRADAY bars (default 5-minute) and keeps
re-running on a loop so it behaves like a live co-pilot. Every cycle it:
  - pulls fresh intraday data for each ticker (+ SPY benchmark)
  - computes VWAP, EMA9/EMA20, RSI, MACD, ATR, relative volume, opening range
  - outputs BUY / SELL / HOLD with an ATR-based risk plan
  - prints an ALERT line whenever a ticker's signal flips
  - rewrites report.html, a live dashboard that auto-refreshes in your browser

Usage:
  python day_trader.py TSLA AAPL NVDA            # loop every 60s (default)
  python day_trader.py --interval 30 TSLA AAPL   # loop every 30s
  python day_trader.py --once TSLA               # run a single pass and exit
  python day_trader.py --bar 1m --once TSLA      # use 1-minute bars

Educational use only. Not financial advice.
"""
import sys
import time
from datetime import datetime, timezone
try:  # data libs are only needed for live analysis, not for rendering
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError:  # pragma: no cover
    np = pd = yf = None

# ---- Your settings (the "safest risk" knobs) -------------------------------
ACCOUNT_SIZE   = 10_000    # your total capital
RISK_PER_TRADE = 0.01      # risk 1% of account per trade (0.01 = safest)
MIN_RR         = 2.0       # target = entry + MIN_RR * risk
ATR_MULT       = 1.5       # intraday stop = entry - 1.5 * ATR (tighter for day trades)
BENCHMARK      = "SPY"
BAR            = "5m"      # intraday bar size: 1m, 2m, 5m, 15m
LOOKBACK       = "5d"      # how much intraday history to pull
REFRESH_SECS   = 60        # default loop interval


# ---- Indicators ------------------------------------------------------------
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(s, fast=12, slow=26, signal=9):
    line = ema(s, fast) - ema(s, slow)
    return line, ema(line, signal)

def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def vwap(df):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    day = pd.Series(df.index.date, index=df.index)
    pv = (tp * df["Volume"]).groupby(day).cumsum()
    vv = df["Volume"].groupby(day).cumsum().replace(0, np.nan)
    return pv / vv


# ---- Step 1: intraday ingest ----------------------------------------------
def fetch(ticker):
    df = yf.download(ticker, period=LOOKBACK, interval=BAR,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def session_slice(df):
    """Rows belonging to the most recent trading day."""
    last_day = df.index.date[-1]
    return df[pd.Series(df.index.date, index=df.index) == last_day]


# ---- Steps 2-6: analyze one ticker ----------------------------------------
def analyze(ticker, spy_day_ret):
    df = fetch(ticker)
    if len(df) < 40:
        return None
    c = df["Close"]
    price = float(c.iloc[-1])
    vw = float(vwap(df).iloc[-1])
    e9, e20 = float(ema(c, 9).iloc[-1]), float(ema(c, 20).iloc[-1])
    r = float(rsi(c).iloc[-1])
    ml, sl = macd(c)
    macd_bull = bool(ml.iloc[-1] > sl.iloc[-1])
    a = float(atr(df).iloc[-1])
    rel_vol = float(df["Volume"].iloc[-1] / df["Volume"].tail(20).mean())

    # opening range = first 30 minutes of the current session
    sess = session_slice(df)
    bars_30m = max(1, int(30 / int(BAR.replace("m", ""))))
    orng = sess.head(bars_30m)
    or_high, or_low = float(orng["High"].max()), float(orng["Low"].min())
    or_breakout = price > or_high

    # intraday relative strength vs SPY (return since today's open)
    day_open = float(sess["Open"].iloc[0])
    stock_day = (price / day_open - 1) * 100
    outperforming = stock_day > spy_day_ret

    above_vwap = price > vw
    ema_bull = e9 > e20

    # ---- scoring (long-biased intraday) ----
    score = 0
    score += 2 if above_vwap else -2
    score += 2 if ema_bull else -2
    score += 1 if macd_bull else -1
    score += 1 if 50 <= r <= 70 else (-2 if r > 75 else 0)
    score += 1 if rel_vol > 1.2 else 0
    score += 1 if or_breakout else 0
    score += 1 if outperforming else 0

    if score >= 5 and above_vwap:
        action = "BUY"
    elif score <= -1 or (not above_vwap and (r > 70 or not macd_bull)):
        action = "SELL / AVOID"
    else:
        action = "HOLD / WATCH"

    # ---- risk plan ----
    stop = price - ATR_MULT * a
    risk_ps = price - stop
    target = price + MIN_RR * risk_ps
    dollars = ACCOUNT_SIZE * RISK_PER_TRADE
    shares = int(dollars / risk_ps) if risk_ps > 0 else 0

    return {
        "ticker": ticker, "action": action, "score": score, "price": round(price, 2),
        "vwap": round(vw, 2), "above_vwap": above_vwap, "ema_bull": ema_bull,
        "e9": round(e9, 2), "e20": round(e20, 2), "rsi": round(r, 1),
        "macd_bull": macd_bull, "rel_vol": round(rel_vol, 2),
        "or_high": round(or_high, 2), "or_low": round(or_low, 2),
        "or_breakout": or_breakout, "stock_day": round(stock_day, 2),
        "spy_day": round(spy_day_ret, 2), "outperforming": outperforming,
        "entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2),
        "reward_risk": MIN_RR, "shares": shares,
        "position_value": round(shares * price, 2), "max_loss": round(dollars, 2),
    }


def spy_day_return():
    df = fetch(BENCHMARK)
    sess = session_slice(df)
    return (float(sess["Close"].iloc[-1]) / float(sess["Open"].iloc[0]) - 1) * 100


# ---- Text line -------------------------------------------------------------
def line(r):
    return (f"{r['ticker']:<6} {r['action']:<13} score {r['score']:>3} | "
            f"${r['price']:<8} VWAP {'above' if r['above_vwap'] else 'below':<5} "
            f"RSI {r['rsi']:<5} EMA {'bull' if r['ema_bull'] else 'bear':<4} "
            f"relVol {r['rel_vol']} | stop ${r['stop']} tgt ${r['target']} "
            f"{r['shares']}sh (max -${r['max_loss']:.0f})")


# ---- HTML dashboard --------------------------------------------------------
def _theme(action):
    if action.startswith("BUY"):  return ("BUY", "#46A171", "#E8F1EC")
    if action.startswith("SELL"): return ("SELL / AVOID", "#E56458", "#FCE9E7")
    return ("HOLD / WATCH", "#D5803B", "#FBEBDE")


def _card(r):
    label, accent, soft = _theme(r["action"])
    span = max(r["target"] - r["stop"], 1e-9)
    risk_pct = max(0.0, min(100.0, (r["entry"] - r["stop"]) / span * 100))
    rsi_pos = max(0.0, min(100.0, r["rsi"]))
    relvol_w = max(0.0, min(100.0, r["rel_vol"] / 3 * 100))
    vwap_chip = ('<span class="chip good">Above VWAP</span>' if r["above_vwap"]
                 else '<span class="chip bad">Below VWAP</span>')
    ema_chip = ('<span class="chip good">EMA9&gt;EMA20</span>' if r["ema_bull"]
                else '<span class="chip bad">EMA9&lt;EMA20</span>')
    macd_chip = ('<span class="chip good">MACD ↑</span>' if r["macd_bull"]
                 else '<span class="chip bad">MACD ↓</span>')
    or_chip = ('<span class="chip good">ORB breakout</span>' if r["or_breakout"]
               else '<span class="chip muted">Inside range</span>')
    op_chip = ('<span class="chip good">Beats SPY</span>' if r["outperforming"]
               else '<span class="chip bad">Lags SPY</span>')
    return f"""
    <article class="card" style="--accent:{accent};--soft:{soft}">
      <header class="card-head">
        <div class="tk"><span class="ticker">{r['ticker']}</span>
          <span class="phase">${r['price']} · day {r['stock_day']:+.2f}%</span></div>
        <div class="badge">{label}</div>
      </header>
      <div class="score-row"><span class="score-num">{r['score']}</span>
        <span class="score-lbl">signal score</span></div>
      <div class="chips">{vwap_chip}{ema_chip}{macd_chip}{or_chip}{op_chip}</div>
      <div class="section"><div class="sec-title">Price plan</div>
        <div class="ladder"><div class="risk-zone" style="width:{risk_pct:.1f}%"></div>
          <div class="reward-zone" style="width:{100-risk_pct:.1f}%"></div>
          <div class="entry-mark" style="left:{risk_pct:.1f}%"></div></div>
        <div class="ladder-lbls"><span><b class="stop">${r['stop']:,.2f}</b>Stop</span>
          <span class="mid"><b class="entry">${r['entry']:,.2f}</b>Entry</span>
          <span class="right"><b class="target">${r['target']:,.2f}</b>Target</span></div></div>
      <div class="section"><div class="sec-title">Momentum</div>
        <div class="rsi"><div class="rsi-track"><div class="rsi-mark" style="left:{rsi_pos:.1f}%"></div></div>
          <div class="rsi-lbl">RSI {r['rsi']}</div></div>
        <div class="bar-row"><span>Rel vol</span><div class="bar"><i style="width:{relvol_w:.0f}%"></i></div><b>{r['rel_vol']}x</b></div></div>
      <footer class="risk">
        <div><span>Buy</span><b>{r['shares']} sh</b></div>
        <div><span>Position</span><b>${r['position_value']:,.0f}</b></div>
        <div><span>R:R</span><b>{r['reward_risk']:.0f}:1</b></div>
        <div><span>Max loss</span><b class="loss">${r['max_loss']:,.0f}</b></div>
      </footer>
    </article>"""


_CSS = """
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#F9F8F7;color:#2C2C2B;line-height:1.5;padding:28px 16px 48px}
  .wrap{max-width:1120px;margin:0 auto}
  .top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
  .top h1{font-size:28px;font-weight:700;letter-spacing:-.02em}
  .top p{color:#7D7A75;font-size:14px;margin-top:6px}
  .live{display:inline-flex;align-items:center;gap:7px;background:#E8F1EC;color:#46A171;font-weight:600;font-size:13px;padding:6px 12px;border-radius:999px}
  .live .dot{width:8px;height:8px;border-radius:50%;background:#46A171;animation:pulse 1.6s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
  .summary{display:flex;gap:12px;margin:20px 0 8px;flex-wrap:wrap}
  .pill{background:#fff;border:1px solid #E6E5E3;border-radius:12px;padding:12px 18px;display:flex;flex-direction:column;min-width:104px}
  .pill b{font-size:24px;font-weight:700;line-height:1}
  .pill span{font-size:13px;color:#7D7A75;margin-top:4px}
  .pill.buy b{color:#46A171}.pill.hold b{color:#D5803B}.pill.sell b{color:#E56458}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(325px,1fr));gap:16px;margin-top:16px}
  .card{background:#fff;border:1px solid #E6E5E3;border-top:3px solid var(--accent);border-radius:12px;padding:20px;box-shadow:0 1px 2px rgba(0,0,0,.05),0 4px 12px rgba(0,0,0,.04)}
  .card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  .ticker{font-size:22px;font-weight:700;letter-spacing:-.01em}
  .phase{display:block;font-size:12px;color:#7D7A75;margin-top:2px}
  .badge{background:var(--soft);color:var(--accent);font-weight:700;font-size:12px;padding:6px 12px;border-radius:999px;white-space:nowrap}
  .score-row{display:flex;align-items:baseline;gap:8px;margin:14px 0 10px}
  .score-num{font-size:26px;font-weight:700;color:var(--accent)}
  .score-lbl{font-size:12px;color:#7D7A75}
  .section{margin-top:16px}
  .sec-title{font-size:12px;font-weight:600;color:#7D7A75;text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px}
  .ladder{position:relative;height:10px;border-radius:6px;display:flex}
  .risk-zone{background:#FCE9E7;height:100%;border-radius:6px 0 0 6px}.reward-zone{background:#E8F1EC;height:100%;border-radius:0 6px 6px 0}
  .entry-mark{position:absolute;top:-3px;width:2px;height:16px;background:#2783DE;transform:translateX(-1px)}
  .ladder-lbls{display:flex;justify-content:space-between;margin-top:8px;font-size:11px;color:#7D7A75}
  .ladder-lbls .mid{text-align:center}.ladder-lbls .right{text-align:right}
  .ladder-lbls b{display:block;font-size:14px;margin-bottom:2px}
  b.stop{color:#E56458}b.entry{color:#2783DE}b.target{color:#46A171}
  .rsi{display:flex;align-items:center;gap:10px;margin-bottom:6px}
  .rsi-track{position:relative;flex:1;height:8px;border-radius:6px;background:linear-gradient(90deg,#E8F1EC 0%,#F0EFED 30%,#F0EFED 70%,#FCE9E7 100%)}
  .rsi-mark{position:absolute;top:-3px;width:2px;height:14px;background:#2C2C2B;transform:translateX(-1px)}
  .rsi-lbl{font-size:13px;font-weight:600;white-space:nowrap}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{font-size:12px;font-weight:600;padding:4px 10px;border-radius:999px;background:#F0EFED;color:#7D7A75}
  .chip.good{background:#E8F1EC;color:#46A171}.chip.bad{background:#FCE9E7;color:#E56458}
  .chip.muted{background:#F0EFED;color:#7D7A75}
  .bar-row{display:flex;align-items:center;gap:10px;margin-top:8px;font-size:13px}
  .bar-row span{width:52px;color:#7D7A75}.bar-row b{width:44px;text-align:right}
  .bar{flex:1;height:8px;background:#F0EFED;border-radius:6px;overflow:hidden}
  .bar i{display:block;height:100%;background:#5E9FE8;border-radius:6px}
  .risk{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:18px;padding-top:16px;border-top:1px solid #E6E5E3}
  .risk div{display:flex;flex-direction:column}
  .risk span{font-size:11px;color:#7D7A75}
  .risk b{font-size:15px;margin-top:2px}.risk b.loss{color:#E56458}
  .note{margin-top:26px;padding:16px 20px;background:#FBEBDE;border:1px solid #F0D9C4;border-radius:12px;font-size:13px}
  @media (max-width:420px){.risk{grid-template-columns:repeat(2,1fr)}}
"""


def render_html(results, refresh):
    when = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")
    buys  = sum(1 for r in results if r["action"].startswith("BUY"))
    holds = sum(1 for r in results if r["action"].startswith("HOLD"))
    sells = sum(1 for r in results if r["action"].startswith("SELL"))
    cards = "".join(_card(r) for r in results)
    head = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="refresh" content="{refresh}">\n'
        f'<title>Day-Trading Signals — {when}</title>\n<style>{_CSS}</style></head>\n'
    )
    body = f"""<body><div class="wrap">
  <div class="top">
    <div><h1>⚡ Day-Trading Signals</h1>
      <p>{BAR} bars · updated {when} · auto-refresh {refresh}s · risk {RISK_PER_TRADE*100:.0f}% of ${ACCOUNT_SIZE:,}/trade</p></div>
    <div class="live"><span class="dot"></span>LIVE</div>
  </div>
  <div class="summary">
    <div class="pill buy"><b>{buys}</b><span>Buy</span></div>
    <div class="pill hold"><b>{holds}</b><span>Hold / Watch</span></div>
    <div class="pill sell"><b>{sells}</b><span>Sell / Avoid</span></div>
  </div>
  <div class="grid">{cards}</div>
  <div class="note"><b>Educational use only — not financial advice.</b> Day trading is high-risk; intraday signals can flip fast. Always use a stop-loss and never risk money you can't afford to lose.</div>
</div></body></html>"""
    return head + body


# ---- Runner ----------------------------------------------------------------
def run_once(tickers, refresh, last_actions):
    stamp = datetime.now().strftime("%H:%M:%S")
    try:
        spy = spy_day_return()
    except Exception as e:
        print(f"[{stamp}] could not fetch {BENCHMARK}: {e}")
        return last_actions
    results = []
    for t in tickers:
        try:
            r = analyze(t, spy)
        except Exception as e:
            print(f"[{stamp}] {t}: {e}")
            continue
        if r is None:
            continue
        results.append(r)
        prev = last_actions.get(t)
        if prev and prev != r["action"]:
            print(f"[{stamp}] 🔔 ALERT {t}: {prev}  ->  {r['action']}  (score {r['score']})")
        last_actions[t] = r["action"]

    print(f"\n[{stamp}] SPY day {spy:+.2f}%")
    for r in results:
        print("  " + line(r))

    if results:
        with open("report.html", "w") as f:
            f.write(render_html(results, refresh))
    return last_actions


def main():
    args = sys.argv[1:]
    once = False
    refresh = REFRESH_SECS
    global BAR
    tickers = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--once":
            once = True
        elif a == "--interval":
            i += 1; refresh = int(args[i])
        elif a == "--bar":
            i += 1; BAR = args[i]
        else:
            tickers.append(a.upper())
        i += 1
    if not tickers:
        tickers = ["TSLA"]

    print(f"Day-trading engine | {BAR} bars | {len(tickers)} tickers | "
          f"{'single run' if once else f'looping every {refresh}s'}")
    print("Open report.html in your browser (it auto-refreshes). Ctrl+C to stop.\n")

    last_actions = {}
    if once:
        run_once(tickers, refresh, last_actions)
        return
    try:
        while True:
            last_actions = run_once(tickers, refresh, last_actions)
            time.sleep(refresh)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
