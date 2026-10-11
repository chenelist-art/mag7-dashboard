# Market & Mag 7 Dashboard

A free, auto-updating dashboard with two parts:

- **S&P 500 market breadth**: how many of the ~500 stocks are rising or falling, overall and in each of the 11 sectors, over 1 day to 1 year. Also shows the share of stocks above their 50/200-day averages, new 52-week highs and lows, sector fund returns, top movers and a searchable table of every stock.
- **Mag 7 dip strategy**: the Magnificent 7 (NVDA, GOOGL, MSFT, META, AAPL, TSLA, AMZN), with SPY and QQQ as benchmarks.

Every weekday after the US market closes, GitHub runs a script that:

1. Downloads prices from Yahoo Finance
2. Checks the **dip rule**: buy when a stock falls **15%+ in 5 trading days**, then hold for **63 trading days (~3 months)**
3. Backtests that rule since 2015 and compares every trade with SPY over the same dates
4. Grabs the latest headlines and (optionally) asks Gemini for a 2–3 sentence summary
5. Builds the S&P 500 market breadth numbers (`market.py`)
6. Publishes the updated website on GitHub Pages

Cost: **$0** (public GitHub repo + Gemini free tier).

---

## What's in the folder

| File | What it does |
|---|---|
| `config.py` | All settings: tickers, 15% threshold, hold period, AI model. **Edit this one.** |
| `build.py` | Downloads data, computes signals + backtest, writes `docs/data.json`, then runs `market.py` |
| `market.py` | S&P 500 market breadth: downloads every member's prices, counts rising/falling stocks by sector, writes `docs/market.json` |
| `docs/index.html` | The dashboard page (reads `data.json` and `market.json`) |
| `docs/chart.umd.js` | Chart.js library (bundled so the site doesn't depend on a CDN) |
| `.github/workflows/daily.yml` | The daily schedule on GitHub Actions |

---

## Setup (about 15 minutes)

### 1. Put it on GitHub
1. Create a GitHub account if you don't have one.
2. Create a **new public repository** (e.g. `mag7-dashboard`). Public is required for free GitHub Pages.
3. Upload everything in this folder, **including the hidden `.github` folder**.
   - Easiest: install [GitHub Desktop](https://desktop.github.com/), clone your empty repo, copy these files in, then commit and push.
   - Uploading in the browser can skip the `.github` folder. If it does, create the file by hand: **Add file → Create new file**, name it `.github/workflows/daily.yml`, then paste in the contents.

### 2. Turn on GitHub Pages
Repo → **Settings → Pages** → under "Build and deployment", set **Source = GitHub Actions**.

### 3. (Optional) Add the AI summary
1. Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: your key

Without this key everything else still works; the AI box just won't appear.

### 4. Run it once
Repo → **Actions** tab → enable workflows if asked → **Daily update → Run workflow**.
After ~2 minutes your site is live at:

```
https://<your-username>.github.io/<repo-name>/
```

After that it updates automatically **Tue–Sat at 5:30am Malaysia time** (right after each US trading day).

---

## Run it on your own computer (optional)

```bash
pip install -r requirements.txt
python build.py              # real data (add --no-ai to skip Gemini, --no-market to skip market breadth)
python -m http.server -d docs
```
Open http://localhost:8000. You can't open `index.html` by double-clicking, because the browser blocks it from loading `data.json`. Serve the folder as shown above.

`python build.py --sample` makes **fake** random prices, so you can test the page without internet.

---

## Changing things

Everything is in `config.py`:

- **Different threshold or hold period**: change `DIP_THRESHOLD`, `HOLD_DAYS`, `LOOKBACK_DAYS`
- **Add or remove stocks**: edit the `MAG7` dictionary (the name doesn't matter; every stock in it gets traded)
- **Longer or shorter backtest**: change `BACKTEST_START`
- **AI model**: change `GEMINI_MODEL` if Google retires the current one (see the [models list](https://ai.google.dev/gemini-api/docs/models))
- **Update time**: edit the `cron` line in `.github/workflows/daily.yml` (times are in UTC; Malaysia is UTC+8)

---

## How the market breadth works

- **Members and sectors:** the current S&P 500 list with GICS sectors, from the free [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies) list on GitHub (it updates when the index changes)
- **Prices:** ~2 years of daily closes for every member plus the index (^GSPC), SPY, RSP (equal weight), QQQ, DIA, IWM, VIX and the 11 SPDR sector funds, from Yahoo Finance. Returns are price changes only (no dividends)
- **Rising / falling:** a stock is "rising" over a period if its close is higher than at the start of the period. Periods: 1 day, 1 week (5 trading days), 1 month (21), 3 months (63), year to date, 1 year (252)
- **Median stock:** the middle stock's return. If the index beats the median stock, a few big companies are carrying it (a "narrow" market)
- **% above 50/200-day average:** share of stocks whose close is above the mean of their last 50/200 closes. Above 50% = most stocks in an uptrend
- **New 52-week high/low:** today's close is above/below every close in the previous 251 trading days
- Takes about 1–2 minutes extra in the daily run. If it fails (e.g. Yahoo rate-limits), the Mag 7 part still updates and the page keeps yesterday's `market.json`

## How the backtest works (for your write-up)

- **Entry:** at the close on the day the 5-day return first hits −15% or worse
- **Exit:** at the close 63 trading days later
- **One position per stock at a time:** new signals are ignored while holding
- **Benchmark:** SPY's return over the exact same dates as each trade, which shows whether buying the dip beat simply holding the market
- Prices are adjusted for splits and dividends (`auto_adjust=True`)

**Limitations to mention honestly:** no fees, taxes or slippage; buying at the exact close of the signal day is optimistic; the Mag 7 were picked *because* they did well (survivorship / hindsight bias); a small number of trades makes averages noisy.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Action fails at "Build data" with no prices | Yahoo sometimes rate-limits. Re-run it. The site keeps yesterday's data until then. |
| Action fails at "deploy" | Check **Settings → Pages → Source = GitHub Actions** |
| Action fails at "git push" | **Settings → Actions → General → Workflow permissions → Read and write** |
| Market breadth section says "No market data yet" | Check the Action log for "Market breadth failed". Usually Yahoo rate-limiting — re-run the workflow. |
| AI summary missing | Check the secret name is exactly `GEMINI_API_KEY`, and look at the Action log for "AI summary failed" |
| Updates stopped after a couple of months | GitHub pauses schedules on inactive repos. Open the **Actions** tab and re-enable the workflow. |

---

*Not financial advice. A personal learning project. yfinance is an unofficial tool that uses Yahoo Finance's public data; it is for personal/educational use.*
