# IPO Post-Listing Price Continuation — Research Repository

## Hypothesis

Eligible US IPOs exhibit short-term post-listing price continuation: the average
close-to-close return from the first trading day's close to the second trading
day's close is positive and statistically distinguishable from zero, net of an
estimated bid-ask-spread cost and the contemporaneous market return.

See `research_report.md` for the full research question, methodology, results,
robustness checks, limitations, and conclusion. **Short version: the hypothesis
was not supported** — see the report for why, and for an important caveat about
SPAC classification in the reported results (see Known Limitations below).

## Setup

```bash
git clone <your-repo-url>
cd quant_application
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
# then edit .env and paste in your own MASSIVE_API_KEY - never commit this file
```

## Running the Analysis

Two steps: pull the data, then test it.

```bash
python src/pull_ipo_data.py
```

This pulls the historical IPO list, classifies and excludes likely SPACs (via SIC
code, a price/name heuristic, and ticker-suffix "U" for SPAC unit offerings),
pulls day-1/day-2 daily bars for each eligible ticker plus a SPY benchmark,
computes a Corwin-Schultz spread-cost estimate, and applies a $3-$500
price-plausibility filter (see Known Limitations). Produces:

- `ipo_day1_day2_returns.csv` — the final, filtered sample used for analysis
- `ipo_day1_day2_returns_excluded_implausible_price.csv` — rows excluded by the
  price filter, kept for manual review rather than silently discarded
- `spac_classification_mismatches.csv` — tickers where the SIC-code and heuristic
  signals disagreed, for validating the SPAC filter

```bash
python src/analyze_results.py
```

Reads `ipo_day1_day2_returns.csv` and runs a one-sample t-test and a Wilcoxon
signed-rank test against zero on each return measure (raw, market-adjusted, and
both cost-adjusted versions), reporting the mean, win rate, and both p-values.
Saves `significance_test_results.csv`.

### Optional: re-filtering an existing file

`src/filter_extreme_prices.py <csv>` applies the same $3-$500 price filter to any
already-pulled CSV. Mainly useful if you have an older export from before the
filter was integrated into the main pipeline; not needed for a fresh run.

## Credential Handling

The Massive API key is read from a `.env` file via `python-dotenv` and is never
hardcoded or committed. `.env` is listed in `.gitignore`; only `.env.example` (a
placeholder template) is version-controlled. All requests authenticate via a
Bearer token in the request header, not a URL query parameter — this was changed
mid-project after realizing query-param auth would leak the key into any printed
error message or traceback (see decision log, 2026-09-10).

## Data Note

Raw pulled market data is intentionally excluded from version control (see
`.gitignore`) to avoid redistributing licensed data. Anyone reproducing this
analysis needs their own Massive API key and should re-run `src/pull_ipo_data.py`
to regenerate it locally.

## Known Limitations

Full details are in `research_report.md`, but the most important one to know
before reading any results: **the reported 2020-2026 backtest used an earlier,
imperfect SPAC classification.** A validation check performed after that backtest
was run found the SIC-based filter missed roughly 70% of true SPACs in a spot
check (SIC code often reflects a SPAC's stated target industry, not a generic
blank-check code). The classification logic in this repo has since been
corrected — adding the ticker-suffix "U" signal and treating either SIC-6770 or
the heuristic as sufficient evidence — but the historical backtest was not
re-run with the fix given time constraints. Any *new* run of this pipeline uses
the corrected logic; the numbers in the current report do not.

## Repository Structure

```
├── src/
│   ├── pull_ipo_data.py         # data acquisition, SPAC classification, return calculation
│   ├── analyze_results.py       # significance testing (t-test + Wilcoxon)
│   └── filter_extreme_prices.py # standalone price filter for re-filtering old exports
├── research_report.md           # full research report
├── decision_log.csv             # research decisions made throughout the project
├── experiment_record.csv        # meaningful experiments, including rejected/superseded ones
├── requirements.txt
├── .env.example
└── README.md
```

## Assistance and Source Disclosure

- **AI tools used:** Claude (Anthropic) was used throughout this project —
  brainstorming and stress-testing candidate hypotheses, refining the final
  hypothesis wording for falsifiability, researching Massive's documented API
  endpoints and fields, drafting and debugging the data pipeline and analysis
  scripts, diagnosing data-quality issues (including the SPAC-classification bug
  and the reverse-split price-distortion issue) found while reviewing pipeline
  output, and drafting the research report, decision log, and experiment record
  from the underlying results. All code, analysis, and conclusions were reviewed
  and run by me, and I am able to explain and defend each part of them.
- **External sources consulted:** Massive/Polygon.io REST API documentation
  (massive.com/docs). The Corwin-Schultz high-low spread estimator follows
  Corwin, S. A., & Schultz, P. (2012), "A Simple Way to Estimate Bid-Ask Spreads
  from Daily High and Low Prices," *Journal of Finance*, 67(2), 719-760.
  [Add any other papers, articles, or repos you personally consulted.]
- **Other assistance:** None
