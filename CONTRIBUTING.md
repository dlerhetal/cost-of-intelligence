# Contributing to Cost of Intelligence

The world is invited. There is no maintainer review queue — CI is the gate. If the validation workflow passes, your PR gets auto-merged on the next bot pass.

## Three ways in

### 1. Just report a price change
Open an Issue using the **Price update** template. Fill in the form. A bot picks it up, writes a PR against `data/prices.json`, and the daily refresh re-publishes the index.

This is the lowest-friction path. Use it if you don't write code.

### 2. Add a provider or model
Edit `data/providers.json`:
```json
{
  "id": "newprovider",
  "name": "New Provider",
  "pricing_url": "https://newprovider.example/pricing",
  "models": [
    {"id": "model-x", "tier": "frontier", "context_window": 200000, "active": true}
  ]
}
```
Then add a scraper function in `scrapers/fetch_prices.py` named `fetch_newprovider()`. Return a list of observation dicts. Stubs return `[]` — that's fine for a first pass, the model gets tracked from the next manual price-update Issue.

### 3. Improve the index math
Edit `scrapers/index_calc.py`. The current implementation is intentionally simple — there's plenty of room to do better. PRs that move the math should include:
- A short justification in the PR description.
- A before/after of the headline numbers on the current dataset.
- Updated tests in `tests/test_index_calc.py` if you add a new component.

## Adding a benchmark

The "effective cost per task" calc currently uses a fixed token mix (2000 in / 600 out). To make this real, we want runners for established benchmarks:

- MMLU
- GPQA Diamond
- HumanEval
- SWE-Bench Verified
- Plus the COI custom 10-prompt corpus (see `benchmarks/coi_corpus.json`)

A benchmark runner is a Python script under `benchmarks/<name>/` that:
1. Loads its prompt set from JSON.
2. Sends each prompt to a configured provider/model.
3. Records actual input and output token counts.
4. Emits a JSON record per (provider, model, benchmark) into `data/benchmark_runs.json`.

Once benchmark runs exist for a model, `effective_per_task_usd` switches from the default-mix estimate to the empirical mean. The index calculator handles this automatically.

## Data sources welcome

- **SemiAnalysis cost-to-serve bands**: anyone with an active subscription can refresh `data/cost_to_serve.json`. Cite the report date and edition; do not paste copyrighted content beyond the numbers.
- **Hyperscaler capex**: append to `data/capacity_overhang.json` after each Q1/Q2/Q3/Q4 earnings cycle. Source the underlying 10-Q / 10-K filings.
- **CloudZero / Goldman / public token-demand estimates**: cite the source URL in the observation record.

## License

By contributing you agree your contributions are released under MIT (for code) and CC0 (for data).

## What we don't accept

- Paywalled data pasted verbatim without permission.
- Scrapers that require an API key with a billing component (this project never pays for data).
- Benchmark runners that hit production endpoints in volume — use cached responses or batch APIs.
- Forecasts based on private channel chatter without a published source.

## Governance

Dale Linn is the nominal maintainer but does not intervene in the data pipeline. Major methodology changes get an Issue with a 14-day comment window before merge. After that, if no veto, it ships.

The project is designed to outlive any single maintainer. If you want to fork and run a competing index, the license explicitly allows it — and the better methodology wins.
