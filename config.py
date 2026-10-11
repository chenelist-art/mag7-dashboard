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

# ---- Market breadth (whole S&P 500, by sector) ----
# Turn off with MARKET_ENABLED = False, or run build.py --no-market
MARKET_ENABLED = True
# Current S&P 500 members with GICS sectors (free, community-maintained list on GitHub)
SP500_LIST_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
MARKET_HISTORY_DAYS = 252   # ~1 year of daily breadth history for the charts
# Index + sector funds shown next to the breadth numbers: symbol -> (name, sector it tracks)
MARKET_BENCHMARKS = {
    "^GSPC": ("S&P 500 index", "S&P 500"),
    "SPY": ("SPDR S&P 500 ETF", None),
    "RSP": ("S&P 500 Equal Weight ETF", None),
    "QQQ": ("Nasdaq-100 ETF", None),
    "DIA": ("Dow Jones ETF", None),
    "IWM": ("Russell 2000 small caps ETF", None),
    "^VIX": ("VIX volatility index", None),
    "XLC": ("Communication Services SPDR", "Communication Services"),
    "XLY": ("Consumer Discretionary SPDR", "Consumer Discretionary"),
    "XLP": ("Consumer Staples SPDR", "Consumer Staples"),
    "XLE": ("Energy SPDR", "Energy"),
    "XLF": ("Financials SPDR", "Financials"),
    "XLV": ("Health Care SPDR", "Health Care"),
    "XLI": ("Industrials SPDR", "Industrials"),
    "XLK": ("Technology SPDR", "Information Technology"),
    "XLB": ("Materials SPDR", "Materials"),
    "XLRE": ("Real Estate SPDR", "Real Estate"),
    "XLU": ("Utilities SPDR", "Utilities"),
}
