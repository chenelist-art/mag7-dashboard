# Mag 7 Dip Dashboard

A free, auto-updating dashboard for the Magnificent 7 (NVDA, GOOGL, MSFT, META, AAPL, TSLA, AMZN), with SPY and QQQ as benchmarks.

Every weekday after the US market closes, GitHub runs a script that:

1. Downloads prices from Yahoo Finance
2. Checks the **dip rule**: buy when a stock falls **15%+ in 5 trading days**, then hold for **63 trading days (~3 months)**
3. Backtests that rule since 2015 and compares every trade with SPY over the same dates
4. Grabs the latest headlines and (optionally) asks Gemini for a 2–3 sentence summary
5. Publishes the updated website on GitHub Pages

Cost: **$0** (public GitHub repo + Gemini free tier).

---

## What's in the folder

| File | What it does |
|---|---|
| `config.py` | All settings: tickers, 15% threshold, hold period, AI model. **Edit this one.** |
| `build.py` | Downloads data, computes signals + backtest, writes `docs/data.json` |
| `docs/index.html` | The dashboard page (reads `data.json`) |
| `docs/chart.umd.js` | Chart.js library (bundled so the site doesn't depend on a CDN) |
| `.github/workflows/daily.yml` | The daily schedule on GitHub Actions |

---

## Setup (about 15 minutes)

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
| AI summary missing | Check the secret name is exactly `GEMINI_API_KEY`, and look at the Action log for "AI summary failed" |
| Updates stopped after a couple of months | GitHub pauses schedules on inactive repos. Open the **Actions** tab and re-enable the workflow. |

---

*Not financial advice. A personal learning project. yfinance is an unofficial tool that uses Yahoo Finance's public data; it is for personal/educational use.*
