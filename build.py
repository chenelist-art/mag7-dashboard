"""
Mag 7 Dip Dashboard — daily data builder.

What it does, in order:
  1. Downloads daily prices for the Mag 7 + SPY/QQQ (Yahoo Finance, free)
  2. Calculates indicators (moving averages, RSI, % from 52-week high)
  3. Checks today's dip signal for each Mag 7 stock
  4. Backtests the dip rule since 2015 and compares each trade to SPY
  5. Grabs recent headlines and (optionally) asks Gemini for a short summary
  6. Saves everything to docs/data.json, which the dashboard page reads

Run:  python build.py            (real data)
      python build.py --sample   (fake data, for testing without internet)
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import config as C

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "data.json")


# ----------------------------------------------------------------------------
# 1. Prices
# ----------------------------------------------------------------------------
def fetch_prices_yahoo(symbols, start):
    """Return {symbol: DataFrame[Close]} using yfinance, with retries."""
    import yfinance as yf

    out = {}
    for sym in symbols:
        for attempt in range(3):
            try:
                df = yf.Ticker(sym).history(start=start, auto_adjust=True)
                if df is not None and not df.empty:
                    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                    df = df[~df.index.duplicated(keep="last")].sort_index()  # Yahoo sometimes repeats the last day
                    out[sym] = df[["Close"]].dropna()
                    break
            except Exception as e:  # network hiccup / rate limit
                print(f"  {sym}: attempt {attempt + 1} failed ({e})")
            time.sleep(2 * (attempt + 1))
        if sym not in out:
            print(f"  WARNING: no price data for {sym}")
        else:
            print(f"  {sym}: {len(out[sym])} days, last {out[sym].index[-1].date()}")
    return out


def fake_prices(symbols, start):
    """Random-walk prices so the pipeline can be tested offline. NOT real data."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range(start, pd.Timestamp.today().normalize())
    market = rng.normal(0.0004, 0.011, len(dates))
    out = {}
    for i, sym in enumerate(symbols):
        vol = 0.012 if sym in C.BENCHMARKS else 0.02 + 0.002 * i
        r = market + rng.normal(0.0003, vol, len(dates))
        # sprinkle in a few sharp sell-offs so the dip rule has something to catch
        for k in rng.choice(len(dates) - 10, 6, replace=False):
            r[k:k + 5] -= rng.uniform(0.03, 0.05)
        out[sym] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(r))}, index=dates)
    return out


# ----------------------------------------------------------------------------
# 2. Indicators
# ----------------------------------------------------------------------------
def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def add_indicators(df):
    c = df["Close"]
    df["sma50"] = c.rolling(50).mean()
    df["sma200"] = c.rolling(200).mean()
    df["rsi14"] = rsi(c)
    df["ret_week"] = c / c.shift(C.LOOKBACK_DAYS) - 1
    df["high_52w"] = c.rolling(252, min_periods=20).max()
    return df


def pct_change_since(c, when):
    past = c[c.index <= when]
    return None if past.empty else float(c.iloc[-1] / past.iloc[-1] - 1)


# ----------------------------------------------------------------------------
# 3 + 4. Signal and backtest
# ----------------------------------------------------------------------------
def backtest(df, bench_close):
    """
    Rule: if the stock is down >= DIP_THRESHOLD over LOOKBACK_DAYS, buy at that
    day's close and sell HOLD_DAYS trading days later. No new buy while holding.
    """
    closes = df["Close"].values
    wk = df["ret_week"].values
    dates = df.index
    trades = []
    i = 0
    n = len(df)
    while i < n:
        if not np.isnan(wk[i]) and wk[i] <= -C.DIP_THRESHOLD:
            j = i + C.HOLD_DAYS
            is_open = j >= n
            j = min(j, n - 1)
            entry_d, exit_d = dates[i], dates[j]
            ret = closes[j] / closes[i] - 1
            b = bench_close.reindex([entry_d, exit_d], method="ffill") if bench_close is not None else None
            bench_ret = float(b.iloc[1] / b.iloc[0] - 1) if b is not None and b.notna().all() else None
            trades.append({
                "entry_date": entry_d.strftime("%Y-%m-%d"),
                "entry_price": round(float(closes[i]), 2),
                "drop": round(float(wk[i]), 4),
                "exit_date": None if is_open else exit_d.strftime("%Y-%m-%d"),
                "exit_price": None if is_open else round(float(closes[j]), 2),
                "days_held": int(j - i),
                "return": round(float(ret), 4),
                "spy_return": None if bench_ret is None else round(bench_ret, 4),
                "open": is_open,
            })
            i = j + 1 if not is_open else n
        else:
            i += 1
    return trades


def summarize(trades):
    closed = [t for t in trades if not t["open"]]
    if not closed:
        return {"trades": 0}
    r = np.array([t["return"] for t in closed])
    s = np.array([t["spy_return"] for t in closed if t["spy_return"] is not None])
    return {
        "trades": len(closed),
        "win_rate": round(float((r > 0).mean()), 4),
        "avg_return": round(float(r.mean()), 4),
        "median_return": round(float(np.median(r)), 4),
        "best": round(float(r.max()), 4),
        "worst": round(float(r.min()), 4),
        "avg_spy_return": round(float(s.mean()), 4) if len(s) else None,
        "avg_excess": round(float(r.mean() - s.mean()), 4) if len(s) else None,
    }


def signal_status(df, trades):
    last_wk = df["ret_week"].iloc[-1]
    open_trade = next((t for t in trades if t["open"]), None)
    if not np.isnan(last_wk) and last_wk <= -C.DIP_THRESHOLD:
        return "BUY", f"Down {abs(last_wk):.1%} this week — dip rule triggered today."
    if open_trade:
        left = C.HOLD_DAYS - open_trade["days_held"]
        return "HOLDING", (f"Bought {open_trade['entry_date']} after a {abs(open_trade['drop']):.1%} drop. "
                           f"{open_trade['return']:+.1%} so far, ~{left} trading days left.")
    if not np.isnan(last_wk) and last_wk <= -C.WATCH_THRESHOLD:
        return "WATCH", f"Down {abs(last_wk):.1%} this week — close to the {C.DIP_THRESHOLD:.0%} trigger."
    return "NONE", f"{last_wk:+.1%} this week — no dip."


# ----------------------------------------------------------------------------
# 5. News + AI summary
# ----------------------------------------------------------------------------
def fetch_news(sym):
    import yfinance as yf
    try:
        items = yf.Ticker(sym).news or []
    except Exception as e:
        print(f"  {sym}: news failed ({e})")
        return []
    out = []
    for it in items[: C.NEWS_PER_STOCK]:
        c = (it.get("content") or it) if isinstance(it, dict) else {}  # yfinance changed formats; handle both
        if not isinstance(c, dict):
            continue
        title = c.get("title")
        url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link")
        source = (c.get("provider") or {}).get("displayName") or c.get("publisher")
        when = c.get("pubDate")
        if not when and c.get("providerPublishTime"):
            when = datetime.fromtimestamp(c["providerPublishTime"], tz=timezone.utc).isoformat()
        if title:
            out.append({"title": title, "url": url, "source": source, "date": when})
    return out


def ai_summary(sym, name, info, news):
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not news:
        return None
    headlines = "\n".join(f"- {n['title']} ({n.get('source') or 'unknown'})" for n in news)
    prompt = (
        f"You are writing a short note on a stock dashboard for a student investor.\n"
        f"Stock: {name} ({sym}). Price ${info['price']:.2f}. "
        f"1-day {info['chg_1d']:+.1%}, 1-week {info['chg_5d']:+.1%}, "
        f"{info['from_52w_high']:+.1%} from 52-week high. Dip-rule status: {info['signal']}.\n"
        f"Recent headlines:\n{headlines}\n\n"
        f"In 2-3 plain-English sentences, explain what the headlines suggest is moving the stock. "
        f"Only use the information above. Do not give buy/sell advice. No markdown."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{C.GEMINI_MODEL}:generateContent"
    try:
        r = requests.post(url, headers={"x-goog-api-key": key},
                          json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"  {sym}: AI summary failed ({e})")
        return None


# ----------------------------------------------------------------------------
# 6. Put it together
# ----------------------------------------------------------------------------
def clean(x, nd=4):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="use fake prices (offline test)")
    ap.add_argument("--no-ai", action="store_true", help="skip the Gemini summary")
    args = ap.parse_args()

    names = {**C.MAG7, **C.BENCHMARKS}
    symbols = list(names)
    print("Fetching prices...")
    prices = fake_prices(symbols, C.BACKTEST_START) if args.sample else fetch_prices_yahoo(symbols, C.BACKTEST_START)
    if not prices:
        sys.exit("No price data at all — stopping so the live dashboard keeps yesterday's data.")

    bench = prices.get(C.BENCHMARK_FOR_BACKTEST)
    bench_close = bench["Close"] if bench is not None else None
    stocks = {}
    all_trades = []

    for sym in symbols:
        if sym not in prices:
            continue
        try:
            info, trades = process(sym, names, prices, bench_close, args)
        except Exception:
            print(f"  ERROR processing {sym} — skipping it:")
            traceback.print_exc()
            continue
        stocks[sym] = info
        for t in trades:
            all_trades.append({**t, "symbol": sym})
        print(f"  {sym}: {info['signal']}")

    if not stocks:
        sys.exit("Every stock failed — see the errors above.")
    finish(stocks, all_trades, symbols, args)


def process(sym, names, prices, bench_close, args):
    """Indicators, signal, backtest, news and AI summary for one stock."""
    df = add_indicators(prices[sym].copy())
    c = df["Close"]
    last = df.index[-1]
    is_bench = sym in C.BENCHMARKS

    info = {
        "symbol": sym,
        "name": names[sym],
        "benchmark": is_bench,
        "date": last.strftime("%Y-%m-%d"),
        "price": clean(c.iloc[-1], 2),
        "chg_1d": clean(c.iloc[-1] / c.iloc[-2] - 1),
        "chg_5d": clean(df["ret_week"].iloc[-1]),
        "chg_ytd": clean(pct_change_since(c, pd.Timestamp(last.year - 1, 12, 31))),
        "chg_1y": clean(pct_change_since(c, last - pd.DateOffset(years=1))),
        "from_52w_high": clean(c.iloc[-1] / df["high_52w"].iloc[-1] - 1),
        "sma50": clean(df["sma50"].iloc[-1], 2),
        "sma200": clean(df["sma200"].iloc[-1], 2),
        "rsi14": clean(df["rsi14"].iloc[-1], 1),
    }
    info["trend"] = ("Uptrend" if info["sma200"] and info["price"] > info["sma200"] else "Downtrend")

    if is_bench:
        info["signal"], info["signal_note"] = "BENCHMARK", "Benchmark — not traded."
        trades = []
    else:
        trades = backtest(df, bench_close)
        info["signal"], info["signal_note"] = signal_status(df, trades)
    info["trades"] = trades
    info["backtest"] = summarize(trades) if not is_bench else None

    tail = df.tail(C.CHART_DAYS)
    info["history"] = [
        [d.strftime("%Y-%m-%d"), clean(r.Close, 2), clean(r.sma50, 2), clean(r.sma200, 2)]
        for d, r in tail.iterrows()
    ]

    info["news"] = [] if args.sample else fetch_news(sym)
    info["ai_summary"] = None
    if not args.sample and not args.no_ai and not is_bench:
        info["ai_summary"] = ai_summary(sym, names[sym], info, info["news"])
        time.sleep(4)  # stay under the free-tier rate limit
    return info, trades


def finish(stocks, all_trades, symbols, args):
    all_trades.sort(key=lambda t: t["entry_date"], reverse=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": bool(args.sample),
        "settings": {
            "dip_threshold": C.DIP_THRESHOLD,
            "watch_threshold": C.WATCH_THRESHOLD,
            "lookback_days": C.LOOKBACK_DAYS,
            "hold_days": C.HOLD_DAYS,
            "backtest_start": C.BACKTEST_START,
            "benchmark": C.BENCHMARK_FOR_BACKTEST,
            "ai_model": C.GEMINI_MODEL if os.environ.get("GEMINI_API_KEY") else None,
        },
        "order": [s for s in symbols if s in stocks],
        "stocks": stocks,
        "all_trades": all_trades,
        "overall": summarize(all_trades),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Saved {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
