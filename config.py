"""
Settings for the dashboard. Change things here — no need to touch build.py.
"""

# Stocks the dip strategy trades
MAG7 = {
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "MSFT": "Microsoft",
    "META": "Meta Platforms",
    "AAPL": "Apple",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
}

# Benchmarks: shown on the dashboard for comparison, but NOT traded
BENCHMARKS = {
    "SPY": "S&P 500 ETF",
    "QQQ": "Nasdaq-100 ETF",
}

# ---- Dip strategy ----
DIP_THRESHOLD = 0.15    # buy when the stock falls 15% or more over 5 trading days
WATCH_THRESHOLD = 0.10  # show "Watch" when it's down 10%+ (getting close)
LOOKBACK_DAYS = 5       # 5 trading days = 1 week
HOLD_DAYS = 63          # hold ~3 months (63 trading days), then sell

# ---- Backtest ----
BACKTEST_START = "2015-01-01"
BENCHMARK_FOR_BACKTEST = "SPY"  # each trade is compared to SPY over the same dates

# ---- Chart ----
CHART_DAYS = 504        # ~2 years of daily prices sent to the page

# ---- AI news summary (optional) ----
# Only runs if the GEMINI_API_KEY environment variable is set.
GEMINI_MODEL = "gemini-3.5-flash-lite"   # free-tier model; change if Google retires it
NEWS_PER_STOCK = 5
