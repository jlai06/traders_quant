# IPO Post-Listing Price Continuation — Research Repository

## Hypothesis

Eligible US IPOs exhibit short-term post-listing price continuation: the average
close-to-close return from the first trading day's close to the second trading
day's close is positive and statistically distinguishable from zero, net of an
estimated bid-ask-spread cost and the contemporaneous market return.

## Setup

```bash
git clone <your-repo-url>
cd ipo-research
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
# then edit .env and paste in your own MASSIVE_API_KEY - never commit this file
```

## Running the main analysis

```bash
python src/pull_ipo_data.py
```

This pulls the historical IPO list, classifies and excludes likely SPACs
(via SIC code 6770, "Blank Checks"), pulls day-1/day-2 daily bars for each
eligible ticker plus a SPY benchmark, and writes the resulting sample to
`ipo_day1_day2_returns.csv` (not committed to this repo — see note below).

## Credential handling

The Massive API key is read from a `.env` file via `python-dotenv` and is
never hardcoded or committed. `.env` is listed in `.gitignore`; only
`.env.example` (a placeholder template) is version-controlled.

## Data note

Raw pulled market data is intentionally excluded from version control
(see `.gitignore`) to avoid redistributing licensed data. Anyone
reproducing this analysis needs their own Massive API key and should
re-run `src/pull_ipo_data.py` to regenerate it locally.

## Repository structure

```
├── src/
│   └── pull_ipo_data.py      # data acquisition + return calculation
├── decision_log.csv          # research decisions made throughout the project
├── experiment_record.csv     # meaningful experiments, including rejected ones
├── requirements.txt
├── .env.example
└── README.md
```

## Assistance and source disclosure

- **AI tools used:** Claude (Anthropic) was used to brainstorm and stress-test
  candidate hypotheses, refine the final hypothesis wording for falsifiability,
  research the Massive API's documented endpoints and fields, and draft/debug
  the data-pulling script in `src/pull_ipo_data.py`. All code was reviewed and
  run by me, and I am able to explain and defend each part of it.
- **External sources consulted:** Massive/Polygon.io REST API documentation
  (massive.com/docs). [Add any academic papers, articles, or other repos you
  personally consulted.]
- **Other assistance:** [Note any help from another person, or state "None."]
