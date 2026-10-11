"""
Market breadth for the whole S&P 500 — how many stocks are rising or falling,
overall and in each of the 11 sectors.

build.py calls build_market() after the Mag 7 part. It:
  1. Downloads the current S&P 500 member list (with GICS sectors)
  2. Downloads ~2 years of daily closes for every member + index/sector ETFs
  3. Works out, for every stock: returns over 1D/1W/1M/3M/YTD/1Y, distance from
     its 50/200-day average and 52-week high, RSI, and new 52-week highs/lows
  4. Counts rising vs falling stocks per sector, and builds a daily history of
     breadth (advancers/decliners, % above 50/200-day average, new highs/lows)
  5. Adds technical indicators for every stock (RSI, MACD, Bollinger Bands)
  6. Scans for common technical setups ("trade ideas") and checks how each one
     actually played out over the past few years (a quick backtest)
  7. Saves it all to docs/market.json, which the dashboard page reads

Run on its own:  python market.py
"""

import csv
import io
import json
import os
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import config as C

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "market.json")
PERIODS = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "1y": 252}   # trading days back; YTD handled separately


# ----------------------------------------------------------------------------
# 1 + 2. Download
# ----------------------------------------------------------------------------
def fetch_members():
    """{symbol: (company name, GICS sector)} for the current S&P 500."""
    r = requests.get(C.SP500_LIST_URL, timeout=30)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    # Yahoo writes class shares with a dash: BRK.B -> BRK-B
    return {row["Symbol"].replace(".", "-"): (row["Security"], row["GICS Sector"]) for row in rows}


def fetch_closes(symbols, period=None, batch=100):
    """Daily closes (split-adjusted, no dividends) as one DataFrame: dates x symbols."""
    import yfinance as yf

    period = period or getattr(C, "MARKET_PERIOD", "3y")
    frames = []
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        for attempt in range(3):
            try:
                df = yf.download(chunk, period=period, interval="1d", auto_adjust=False,
                                 group_by="column", threads=True, progress=False)
                close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": chunk[0]})
                if not close.dropna(how="all").empty:
                    frames.append(close)
                    break
            except Exception as e:  # rate limit / network hiccup
                print(f"  market batch {i // batch + 1}: attempt {attempt + 1} failed ({e})")
            time.sleep(3 * (attempt + 1))
        time.sleep(1)
    if not frames:
        return pd.DataFrame()
    px = pd.concat(frames, axis=1)
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
    px = px[~px.index.duplicated(keep="last")].sort_index()
    px = px.loc[:, ~px.columns.duplicated()]
    return px.dropna(axis=1, how="all")


# ----------------------------------------------------------------------------
# 3 + 4. Analysis (pure pandas — no network, so it can be tested offline)
# ----------------------------------------------------------------------------
def _r(x, nd=4):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def _rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def _snapshot(c, L, ytd_i):
    """Latest numbers for one price series."""
    last = c.iloc[L]
    out = {"price": _r(last, 2)}
    for k, n in PERIODS.items():
        out[f"chg_{k}"] = _r(last / c.iloc[L - n] - 1) if L - n >= 0 and pd.notna(c.iloc[L - n]) else None
    out["chg_ytd"] = _r(last / c.iloc[ytd_i] - 1) if ytd_i >= 0 and pd.notna(c.iloc[ytd_i]) else None
    s50, s200 = c.rolling(50).mean().iloc[L], c.rolling(200).mean().iloc[L]
    out["vs_sma50"], out["vs_sma200"] = _r(last / s50 - 1), _r(last / s200 - 1)
    out["above_sma50"] = None if pd.isna(s50) else bool(last > s50)
    out["above_sma200"] = None if pd.isna(s200) else bool(last > s200)
    win, prior = c.iloc[max(0, L - 251):L + 1], c.iloc[max(0, L - 251):L]
    full = win.notna().sum() >= 252           # needs a full year to call a 52-week high/low
    out["from_52w_high"] = _r(last / win.max() - 1) if full else None
    out["new_52w_high"] = bool(full and last > prior.max())
    out["new_52w_low"] = bool(full and last < prior.min())
    out["rsi14"] = _r(_rsi(c.dropna()).iloc[-1], 1) if c.notna().sum() > 42 else None
    return out


def analyse(px, members, mag7=()):
    """px: DataFrame dates x symbols of closes. members: {symbol: (name, sector)}."""
    stock_cols = [s for s in members if s in px.columns]
    # Yahoo sometimes returns rows for US holidays (only an index or two has data).
    # Keep only real trading days: at least half the stocks have a price.
    px = px[px[stock_cols].notna().sum(axis=1) >= 0.5 * len(stock_cols)].ffill()
    dates = px.index
    L = len(dates) - 1
    ytd_i = int(np.where(dates < pd.Timestamp(dates[L].year, 1, 1))[0][-1]) if (dates < pd.Timestamp(dates[L].year, 1, 1)).any() else -1
    syms = [s for s in members if s in px.columns]

    ind = indicators(px[syms])
    scan = scan_setups(px[syms], ind, L)
    stocks = [{"symbol": s, "name": members[s][0], "sector": members[s][1], "mag7": s in mag7,
               **_snapshot(px[s], L, ytd_i), **_indicator_snapshot(ind, s, L),
               "setups": [x["id"] for x in SETUPS if bool(scan["today"][x["id"]].get(s, False))]} for s in syms]
    benchmarks = [{"symbol": s, "name": name, "group": grp or "", **_snapshot(px[s], L, ytd_i)}
                  for s, (name, grp) in C.MARKET_BENCHMARKS.items() if s in px.columns]

    groups = {"S&P 500": syms}
    for sec in sorted({members[s][1] for s in syms}):
        groups[sec] = [s for s in syms if members[s][1] == sec]

    # --- rising vs falling per sector, every period ---
    st = pd.DataFrame(stocks)
    etf_of = {b["group"]: b for b in benchmarks if b["group"]}
    sectors = []
    for g, mem in groups.items():
        rows = st[st.symbol.isin(mem)]
        etf = etf_of.get(g, {})
        out = {"group": g, "etf": etf.get("symbol"), "stocks": len(rows),
               "rising": {}, "falling": {}, "median": {}, "etf_chg": {}}
        for p in ["1d", "1w", "1m", "3m", "ytd", "1y"]:
            v = rows[f"chg_{p}"].dropna()
            out["rising"][p] = int((v > 0).sum())
            out["falling"][p] = int((v < 0).sum())
            out["median"][p] = _r(v.median()) if len(v) else None
            out["etf_chg"][p] = etf.get(f"chg_{p}")
        a50, a200 = rows.above_sma50.dropna(), rows.above_sma200.dropna()
        out["pct_above_50"] = _r(a50.astype(bool).mean()) if len(a50) else None
        out["pct_above_200"] = _r(a200.astype(bool).mean()) if len(a200) else None
        out["new_highs"] = int(rows.new_52w_high.sum())
        out["new_lows"] = int(rows.new_52w_low.sum())
        sectors.append(out)

    # --- daily breadth history ---
    n = C.MARKET_HISTORY_DAYS
    S = px[syms]
    has = S.notna() & S.shift(1).notna()
    up, dn = (S.diff() > 0) & has, (S.diff() < 0) & has
    sma50, sma200 = S.rolling(50).mean(), S.rolling(200).mean()
    a50, a200 = (S > sma50) & sma50.notna(), (S > sma200) & sma200.notna()
    full = S.shift(1).rolling(251).count() >= 251
    nh = (S > S.shift(1).rolling(251).max()) & full
    nl = (S < S.shift(1).rolling(251).min()) & full
    tail = slice(max(1, L - n + 1), L + 1)
    breadth = {"dates": [d.strftime("%Y-%m-%d") for d in dates[tail]], "groups": {}}
    for g, mem in groups.items():
        n50 = sma50[mem].notna().sum(axis=1).replace(0, np.nan)
        n200 = sma200[mem].notna().sum(axis=1).replace(0, np.nan)
        breadth["groups"][g] = {
            "adv": up[mem].sum(axis=1).iloc[tail].astype(int).tolist(),
            "dec": dn[mem].sum(axis=1).iloc[tail].astype(int).tolist(),
            "a50": [_r(x) for x in (a50[mem].sum(axis=1) / n50).iloc[tail]],
            "a200": [_r(x) for x in (a200[mem].sum(axis=1) / n200).iloc[tail]],
            "nh": nh[mem].sum(axis=1).iloc[tail].astype(int).tolist(),
            "nl": nl[mem].sum(axis=1).iloc[tail].astype(int).tolist(),
        }

    history = {"dates": breadth["dates"],
               "closes": {s: [_r(x, 2) for x in px[s].iloc[tail]] for s in C.MARKET_BENCHMARKS if s in px.columns}}

    by_sym = {x["symbol"]: x for x in stocks}
    ideas = {"horizon_days": HORIZON, "stats_from": scan["stats_from"], "stats_to": scan["stats_to"],
             "baseline": scan["baseline"], "setups": []}
    for x in SETUPS:
        matched = [by_sym[s] for s in syms if bool(scan["today"][x["id"]].get(s, False))]
        key, rev = x["sort"]
        matched.sort(key=lambda r: (r.get(key) is None, -(r.get(key) or 0) if rev else (r.get(key) or 0)))
        ideas["setups"].append({k: x[k] for k in ("id", "name", "bias", "rule", "explain")} |
                               {"stats": scan["stats"][x["id"]], "matches": [m["symbol"] for m in matched]})

    return {
        "as_of": dates[L].strftime("%Y-%m-%d"),
        "ideas": ideas,
        "stocks": stocks,
        "benchmarks": benchmarks,
        "sectors": sectors,
        "breadth": breadth,
        "history": history,
    }


# ----------------------------------------------------------------------------
# Technical indicators (for every stock at once: DataFrames of dates x symbols)
# ----------------------------------------------------------------------------
def indicators(S):
    """RSI(14), MACD(12, 26, 9) and Bollinger Bands(20, 2) for every column of S."""
    d = S.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    ema12 = S.ewm(span=12, adjust=False).mean()
    ema26 = S.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    mid = S.rolling(20).mean()
    sd = S.rolling(20).std(ddof=0)
    up, lo = mid + 2 * sd, mid - 2 * sd
    width = (up - lo) / mid
    return {
        "rsi": rsi, "macd": macd, "sig": sig, "hist": macd - sig,
        "bb_mid": mid, "bb_up": up, "bb_lo": lo, "pctb": (S - lo) / (up - lo), "width": width,
        # squeeze = bands at their narrowest 10% of the last 6 months
        "squeeze": width <= width.rolling(126, min_periods=126).quantile(0.10),
        "sma200": S.rolling(200).mean(),
        "new_high": (S > S.shift(1).rolling(251).max()) & (S.shift(1).rolling(251).count() >= 251),
    }


def _indicator_snapshot(ind, s, L):
    g = lambda k, nd=4: _r(ind[k][s].iloc[L], nd)
    m, sg = ind["macd"][s].iloc[L], ind["sig"][s].iloc[L]
    return {
        "macd": g("macd"), "macd_signal": g("sig"), "macd_hist": g("hist"),
        "macd_state": None if pd.isna(m) or pd.isna(sg) else ("bullish" if m > sg else "bearish"),
        "bb_upper": g("bb_up", 2), "bb_mid": g("bb_mid", 2), "bb_lower": g("bb_lo", 2),
        "bb_pctb": g("pctb", 3), "bb_width": g("width"), "bb_squeeze": bool(ind["squeeze"][s].iloc[L]),
    }


# ----------------------------------------------------------------------------
# Trade-idea scanner: rule-based setups + how each played out in the past
# ----------------------------------------------------------------------------
HORIZON = 21   # judge each past signal by the stock's return over the next 21 trading days (~1 month)


def _crossed_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def _setup_conditions(S, ind):
    """True on each (day, stock) where the setup is present."""
    up200 = S > ind["sma200"]
    within3 = lambda x: x.astype(float).rolling(3, min_periods=1).max() > 0
    return {
        "pullback": up200 & (ind["rsi"] < 35),
        "lower_band_bounce": (S.shift(1) < ind["bb_lo"].shift(1)) & (S > ind["bb_lo"]),
        "macd_bull": within3(_crossed_up(ind["macd"], ind["sig"])) & up200 & (ind["macd"] > ind["sig"]),
        "squeeze": ind["squeeze"].fillna(False).astype(bool),
        "new_high": ind["new_high"],
        "overbought": (ind["rsi"] > 75) & (S > ind["bb_up"]),
        "macd_bear": within3(_crossed_up(ind["sig"], ind["macd"])) & (S < ind["sma200"]) & (ind["macd"] < ind["sig"]),
    }


SETUPS = [
    {"id": "pullback", "name": "Pullback in an uptrend", "bias": "bullish", "sort": ("rsi14", False),
     "rule": "Price above its 200-day average, but RSI(14) below 35",
     "explain": "A stock in a long-term uptrend has had a sharp short-term drop. Some traders look for these as 'buy the dip' candidates; the risk is that the drop is the start of a bigger fall."},
    {"id": "lower_band_bounce", "name": "Bounce off the lower Bollinger Band", "bias": "bullish", "sort": ("bb_pctb", False),
     "rule": "Closed below the lower Bollinger Band yesterday, back above it today",
     "explain": "The price was unusually low compared with its last 20 days and has just turned back up. A classic mean-reversion signal."},
    {"id": "macd_bull", "name": "MACD bullish crossover", "bias": "bullish", "sort": ("macd_hist", True),
     "rule": "MACD crossed above its signal line in the last 3 days, price above 200-day average",
     "explain": "Short-term momentum has turned up inside a long-term uptrend. A trend-following signal."},
    {"id": "squeeze", "name": "Bollinger squeeze", "bias": "watch", "sort": ("bb_width", False),
     "rule": "Bollinger Bands at their narrowest 10% of the last 6 months",
     "explain": "The stock has gone unusually quiet. Quiet periods are often followed by a bigger move, but the signal doesn't say which direction."},
    {"id": "new_high", "name": "Breakout to a 52-week high", "bias": "bullish", "sort": ("chg_1m", True),
     "rule": "Closed above every close of the previous 251 trading days",
     "explain": "Momentum: stocks making new highs have no sellers 'stuck' above them. Often keeps going, but can also mark a top."},
    {"id": "overbought", "name": "Overbought and stretched", "bias": "caution", "sort": ("rsi14", True),
     "rule": "RSI(14) above 75 and price above the upper Bollinger Band",
     "explain": "The stock has run up very fast. Not a sell signal on its own, but chasing it here carries higher risk of a pullback."},
    {"id": "macd_bear", "name": "MACD bearish crossover in a downtrend", "bias": "bearish", "sort": ("vs_sma200", False),
     "rule": "MACD crossed below its signal line in the last 3 days, price below 200-day average",
     "explain": "Short-term momentum has turned down inside a long-term downtrend. Traders who short look for these; holders may see it as a warning."},
]


def scan_setups(S, ind, L):
    conds = _setup_conditions(S, ind)
    fwd = S.shift(-HORIZON) / S - 1
    # Judge only days with a full warm-up (200-day average exists) and a known forward return
    start = 200
    end = L - HORIZON
    window = S.index[start:end + 1]

    def stats(mask):
        v = fwd.where(mask).iloc[start:end + 1].stack()
        v = v[np.isfinite(v)]
        if not len(v):
            return {"signals": 0}
        return {"signals": int(len(v)), "pct_up": _r((v > 0).mean()), "median": _r(v.median()),
                "avg": _r(v.mean())}

    base = stats(S.notna() & fwd.notna())
    out = {"stats": {}, "today": {}, "baseline": base,
           "stats_from": window[0].strftime("%Y-%m-%d") if len(window) else None,
           "stats_to": window[-1].strftime("%Y-%m-%d") if len(window) else None}
    for x in SETUPS:
        c = conds[x["id"]].fillna(False).astype(bool)
        first_day = c & ~c.shift(1, fill_value=False)     # count each signal once, on the day it starts
        out["stats"][x["id"]] = stats(first_day)
        out["today"][x["id"]] = c.iloc[L].to_dict()
    return out


# ----------------------------------------------------------------------------
# 5. Put it together
# ----------------------------------------------------------------------------
def build_market(mag7=()):
    """Download, analyse, save docs/market.json. Returns True on success."""
    print("Market breadth: fetching S&P 500 members...")
    members = fetch_members()
    symbols = list(members) + list(C.MARKET_BENCHMARKS)
    print(f"Market breadth: downloading {len(symbols)} price histories...")
    px = fetch_closes(symbols)
    missing = [s for s in symbols if s not in px.columns]
    if missing:
        print(f"  WARNING: no prices for {len(missing)} symbols: {', '.join(missing[:20])}")
    if "^GSPC" not in px.columns or len(missing) > 0.1 * len(symbols):
        print("  Too much missing — keeping yesterday's market.json.")
        return False
    data = analyse(px, members, mag7)
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["source"] = {"prices": "Yahoo Finance (via yfinance), daily closes", "members": C.SP500_LIST_URL}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    n_ideas = sum(len(x["matches"]) for x in data["ideas"]["setups"])
    print(f"  Trade-idea scanner: {n_ideas} matches across {len(SETUPS)} setups")
    tot = data["sectors"][0]
    print(f"Saved {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1024:.0f} KB) — as of {data['as_of']}: "
          f"{tot['rising']['1d']} up, {tot['falling']['1d']} down, {tot['pct_above_50']:.0%} above 50-day avg")
    return True


if __name__ == "__main__":
    build_market(mag7=tuple(C.MAG7))
