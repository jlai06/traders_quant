"""
Pull historical IPO events and day-1 / day-2 daily bars from the Massive API.

Setup:
    See README.md at the repo root for full setup instructions.
    Quick version: copy .env.example to .env, fill in your key, then:
        pip install -r requirements.txt
        python src/pull_ipo_data.py

This is a starting scaffold, not the finished pipeline. It handles:
    1. Pulling historical IPO events (with pagination)
    2. SPAC classification via SIC code (6770 = Blank Checks), with a price/name
       heuristic as a fallback when a SIC lookup isn't available
    3. Pulling daily OHLCV bars for each ticker's first two trading days
    4. Pulling the benchmark (SPY) over the same range
    5. Computing raw and market-adjusted close-to-close returns

Still to do (see README / decision log):
    - Validate the SPAC filter against a manual sample before trusting it
    - Decide how to handle IPOs with a halted or partial first trading day
    - Add a spread-cost estimate (e.g., Corwin-Schultz high-low estimator)
    - Run the significance test (t-test + a non-parametric check) on the results
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current directory, if present

API_KEY = os.environ["MASSIVE_API_KEY"]
BASE_URL = "https://api.massive.com"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})  # key lives in a header, never in a URL


def get_historical_ipos(start_date: str, end_date: str, limit: int = 1000) -> pd.DataFrame:
    """Pull all historical (status='history') IPO events with listing_date in [start_date, end_date]."""
    url = f"{BASE_URL}/vX/reference/ipos"
    params = {
        "ipo_status": "history",
        "listing_date.gte": start_date,
        "listing_date.lte": end_date,
        "limit": limit,
        "sort": "listing_date",
        "order": "asc",
    }

    results = []
    while True:
        resp = SESSION.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))

        next_url = data.get("next_url")
        if not next_url:
            break
        url, params = next_url, {}  # next_url already carries its own query params; auth comes from the session header
        time.sleep(0.2)  # be polite to rate limits

    return pd.DataFrame(results)


def get_sic_code(ticker: str) -> str | None:
    """Look up a ticker's SIC code via Massive's Ticker Overview endpoint.
    SIC 6770 = 'Blank Checks' - the SEC's own classification for SPACs.
    Returns None if the lookup fails (e.g. an old delisted ticker with no reference record)."""
    url = f"{BASE_URL}/v3/reference/tickers/{ticker}"
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("sic_code")
    except requests.RequestException:
        return None


def looks_like_spac_heuristic(row: pd.Series) -> bool:
    """Fallback heuristic when a SIC lookup isn't available. Price ~$10 or 'acquisition' in the name."""
    price_fields = [row.get("final_issue_price"), row.get("lowest_offer_price"), row.get("highest_offer_price")]
    price_fields = [p for p in price_fields if pd.notna(p)]
    near_ten = any(abs(p - 10.0) < 0.05 for p in price_fields)
    name_hint = "acquisition" in str(row.get("issuer_name", "")).lower()
    return near_ten or name_hint


def classify_spacs(ipo_df: pd.DataFrame) -> pd.DataFrame:
    """Classify each IPO as a likely SPAC, preferring the authoritative SIC code (6770)
    and falling back to the price/name heuristic when the SIC lookup is unavailable.
    Also reports how often the two methods agree - worth logging as a validation check."""
    df = ipo_df.copy()
    total = len(df)

    sic_codes = []
    print(f"Looking up SIC codes for {total} tickers - this makes one API call per ticker...")
    for i, ticker in enumerate(df["ticker"], start=1):
        if i % 25 == 0 or i == total:
            print(f"  ...checked {i}/{total} tickers")
        sic_codes.append(get_sic_code(ticker))
        time.sleep(0.1)
    df["sic_code"] = sic_codes

    df["heuristic_spac"] = df.apply(looks_like_spac_heuristic, axis=1)
    df["sic_spac"] = df["sic_code"] == "6770"

    # Prefer the SIC result when we have one; fall back to the heuristic otherwise
    df["is_likely_spac"] = df["sic_spac"].where(df["sic_code"].notna(), df["heuristic_spac"])

    both_known = df["sic_code"].notna()
    if both_known.any():
        agreement = (df.loc[both_known, "sic_spac"] == df.loc[both_known, "heuristic_spac"]).mean()
        print(f"SIC vs. heuristic agreement on {both_known.sum()} tickers with a known SIC code: {agreement:.1%}")

        mismatches = df.loc[
            both_known & (df["sic_spac"] != df["heuristic_spac"]),
            ["ticker", "issuer_name", "final_issue_price", "sic_code", "sic_spac", "heuristic_spac"],
        ]
        if len(mismatches) > 0:
            mismatches.to_csv("spac_classification_mismatches.csv", index=False)
            print(f"Saved {len(mismatches)} disagreements to spac_classification_mismatches.csv for manual review")

    return df


def get_daily_bars(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Pull daily OHLCV bars for a ticker between two dates (inclusive)."""
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
    params = {"adjusted": "true", "sort": "asc"}
    resp = SESSION.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get("resultsCount", 0) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(data["results"])
    df["date"] = (
        pd.to_datetime(df["t"], unit="ms", utc=True)
        .dt.tz_convert("America/New_York")
        .dt.date
    )
    return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})


def build_sample(ipo_df: pd.DataFrame, benchmark_ticker: str = "SPY") -> pd.DataFrame:
    """For each eligible IPO, pull day-1/day-2 bars and compute raw + market-adjusted returns."""
    rows = []
    total = len(ipo_df)

    # Fetch the benchmark ONCE for the full span instead of once per ticker -
    # cuts API calls roughly in half and avoids re-requesting overlapping windows.
    min_date = ipo_df["listing_date"].min()
    max_date = (pd.to_datetime(ipo_df["listing_date"].max()) + timedelta(days=10)).strftime("%Y-%m-%d")
    print(f"Fetching benchmark ({benchmark_ticker}) once for {min_date} to {max_date}...")
    bench_bars = get_daily_bars(benchmark_ticker, min_date, max_date)
    bench_by_date = dict(zip(bench_bars["date"], bench_bars["close"]))

    for i, (_, ipo) in enumerate(ipo_df.iterrows(), start=1):
        if i % 25 == 0 or i == total:
            print(f"  ...processed {i}/{total} tickers, {len(rows)} kept so far")

        ticker = ipo["ticker"]
        listing_date = ipo["listing_date"]
        window_end = (pd.to_datetime(listing_date) + timedelta(days=10)).strftime("%Y-%m-%d")

        bars = get_daily_bars(ticker, listing_date, window_end)
        if len(bars) < 2:
            continue  # not enough trading days yet, or ticker had no eligible trades

        day1, day2 = bars.iloc[0], bars.iloc[1]
        stock_return = (day2["close"] - day1["close"]) / day1["close"]

        if day1["date"] not in bench_by_date or day2["date"] not in bench_by_date:
            continue  # benchmark didn't trade on one of these dates - shouldn't normally happen
        bench_return = (bench_by_date[day2["date"]] - bench_by_date[day1["date"]]) / bench_by_date[day1["date"]]

        rows.append({
            "ticker": ticker,
            "listing_date": listing_date,
            "day1_date": day1["date"],
            "day2_date": day2["date"],
            "day1_close": day1["close"],
            "day2_close": day2["close"],
            "raw_return": stock_return,
            "benchmark_return": bench_return,
            "market_adjusted_return": stock_return - bench_return,
        })
        time.sleep(0.15)

    return pd.DataFrame(rows)


if __name__ == "__main__":
    start_time = time.time()

    # Adjust this range once you've confirmed how far back your plan's history actually goes
    ipos = get_historical_ipos(start_date="2018-01-01", end_date="2025-12-31")
    print(f"Pulled {len(ipos)} historical IPO events")

    if len(ipos) == 0:
        raise SystemExit(
            "No IPO events returned - check your API key, date range, and plan access "
            "before continuing. Nothing else in this script will work until this is non-empty."
        )

    ipos = classify_spacs(ipos)
    print(f"Flagged {ipos['is_likely_spac'].sum()} as likely SPACs (excluded from sample)")

    eligible = ipos[~ipos["is_likely_spac"]].copy()
    print(f"Building sample from {len(eligible)} eligible tickers - this can take a few minutes...")
    sample = build_sample(eligible)

    output_path = os.path.abspath("ipo_day1_day2_returns.csv")
    sample.to_csv(output_path, index=False)
    elapsed = time.time() - start_time

    print(f"\nDone in {elapsed:.0f}s.")
    print(f"Saved {len(sample)} eligible IPO observations to:\n  {output_path}")
    if len(sample) == 0:
        print("WARNING: sample is empty - check for silent errors above, or narrow the date range and re-run.")
    else:
        print(sample[["raw_return", "market_adjusted_return"]].describe())
