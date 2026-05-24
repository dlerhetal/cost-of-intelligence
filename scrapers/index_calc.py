"""
Subsidy Index calculator.

Reads:
  data/prices.json
  data/providers.json
  data/cost_to_serve.json
  data/capacity_overhang.json
  data/benchmark_runs.json (optional; produced by benchmark runners)

Writes:
  site/index.json          — current snapshot for the dashboard headline
  site/history.json        — time series of effective-$/task by tier (all dates)
  site/forecast.json       — linear-regression projection forward 6 months
  data/index_history.json  — append-only run log

Run unattended via GitHub Actions. No side effects beyond writing those files.
"""

import json
import statistics
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site"

# Token mix assumption for "effective per task" — average frontier-tier agentic
# workload reported by CloudZero / SemiAnalysis.
DEFAULT_INPUT_TOKENS = 2000
DEFAULT_OUTPUT_TOKENS = 600

# How far forward to project, in days.
FORECAST_HORIZON_DAYS = 180


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def effective_per_task(obs, input_tokens=DEFAULT_INPUT_TOKENS, output_tokens=DEFAULT_OUTPUT_TOKENS):
    """Cost of a single representative task at this provider's quoted rate,
    inflated by the model's tokenizer factor (which captures changes in tokens
    consumed for identical text vs the provider's previous baseline)."""
    if obs.get("input_per_mtok_usd") is None or obs.get("output_per_mtok_usd") is None:
        return None
    factor = obs.get("tokenizer_factor") or 1.0
    in_cost = (input_tokens * factor / 1_000_000) * obs["input_per_mtok_usd"]
    out_cost = (output_tokens * factor / 1_000_000) * obs["output_per_mtok_usd"]
    return round(in_cost + out_cost, 6)


def load_active_models(providers):
    active = set()
    for p in providers["providers"]:
        for m in p["models"]:
            if m.get("active"):
                active.add((p["id"], m["id"]))
    return active


def latest_per_model_active(observations, active_models):
    """Most recent verified observation per (provider, model), restricted to
    currently-active models. Used for the headline floor."""
    latest = {}
    for obs in observations:
        if not obs.get("verified"):
            continue
        key = (obs["provider"], obs["model"])
        if key not in active_models:
            continue
        if key not in latest or obs["observed_on"] > latest[key]["observed_on"]:
            latest[key] = obs
    return latest


def floor_by_tier(latest, tier_predicate):
    """Lowest effective_per_task across latest observations matching tier."""
    tier_obs = [o for o in latest.values() if tier_predicate(o["tier"])]
    costs = [(effective_per_task(o), o) for o in tier_obs]
    costs = [(c, o) for c, o in costs if c is not None]
    if not costs:
        return None
    cheapest_cost, cheapest_obs = min(costs, key=lambda x: x[0])
    return {
        "effective_per_task_usd": cheapest_cost,
        "input_per_mtok_usd": cheapest_obs["input_per_mtok_usd"],
        "output_per_mtok_usd": cheapest_obs["output_per_mtok_usd"],
        "tokenizer_factor": cheapest_obs.get("tokenizer_factor", 1.0),
        "provider": cheapest_obs["provider"],
        "model": cheapest_obs["model"],
        "observed_on": cheapest_obs["observed_on"],
    }


def is_frontier(tier):
    return tier in ("frontier", "frontier-reasoning")


def is_budget(tier):
    return tier == "budget"


def historical_floor_series(observations, tier_predicate):
    """Walk forward through history. For each observation date, compute the
    cheapest then-available model's effective_per_task across providers.
    A model is 'then-available' if we have an observation for it on or before
    that date and no later observation for the same model showing it discontinued.
    Simpler heuristic used: at each date d, consider the most recent observation
    per (provider, model) where observed_on <= d, filter to the tier, take the
    min of effective_per_task."""
    if not observations:
        return []
    obs_by_date = defaultdict(list)
    for o in observations:
        if not o.get("verified"):
            continue
        obs_by_date[o["observed_on"]].append(o)

    all_dates = sorted(obs_by_date.keys())
    latest_per_pm = {}
    series = []
    for d in all_dates:
        for o in obs_by_date[d]:
            key = (o["provider"], o["model"])
            latest_per_pm[key] = o
        tier_obs = [o for o in latest_per_pm.values() if tier_predicate(o["tier"])]
        costs = []
        for o in tier_obs:
            c = effective_per_task(o)
            if c is not None:
                costs.append((c, o))
        if not costs:
            continue
        cheapest_cost, cheapest_obs = min(costs, key=lambda x: x[0])
        series.append({
            "date": d,
            "effective_per_task_usd": cheapest_cost,
            "leader_provider": cheapest_obs["provider"],
            "leader_model": cheapest_obs["model"],
        })
    return series


def implied_margin(latest, cost_bands):
    """Compare each verified frontier observation to SemiAnalysis cost band mid.
    Returns the median implied margin across frontier observations.
    Negative = subsidy (price below cost-to-serve)."""
    frontier_out = next((b for b in cost_bands["bands"] if b["tier"] == "frontier" and b["tokens"] == "output"), None)
    frontier_in = next((b for b in cost_bands["bands"] if b["tier"] == "frontier" and b["tokens"] == "input"), None)
    if not frontier_out or not frontier_in:
        return None

    margins = []
    for obs in latest.values():
        if not is_frontier(obs["tier"]) or obs.get("input_per_mtok_usd") is None:
            continue
        cost_per_task = (
            (DEFAULT_INPUT_TOKENS / 1_000_000) * frontier_in["mid_per_mtok_usd"]
            + (DEFAULT_OUTPUT_TOKENS / 1_000_000) * frontier_out["mid_per_mtok_usd"]
        )
        price_per_task = effective_per_task(obs)
        if cost_per_task <= 0 or price_per_task is None:
            continue
        margin = (price_per_task - cost_per_task) / cost_per_task
        margins.append(margin)
    if not margins:
        return None
    return round(statistics.median(margins), 4)


def latest_overhang(overhang):
    for obs in sorted(overhang["observations"], key=lambda x: x["observed_on"], reverse=True):
        if obs.get("overhang_ratio") is not None:
            return obs
    return None


def linear_fit(xs, ys):
    """Simple least-squares fit. xs are floats (days since epoch), ys are floats.
    Returns (slope, intercept, residual_std)."""
    n = len(xs)
    if n < 2:
        return 0.0, ys[0] if ys else 0.0, 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den != 0 else 0.0
    intercept = mean_y - slope * mean_x
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    if n > 2:
        residual_std = (sum(r ** 2 for r in residuals) / (n - 2)) ** 0.5
    else:
        residual_std = 0.0
    return slope, intercept, residual_std


def forecast_series(history, horizon_days=FORECAST_HORIZON_DAYS):
    """Linear projection forward from the last 12 months of frontier floor.
    Returns a list of {date, projected_per_task_usd, band_low, band_high}."""
    if len(history) < 4:
        return []
    cutoff = date.fromisoformat(history[-1]["date"]) - timedelta(days=365)
    recent = [h for h in history if date.fromisoformat(h["date"]) >= cutoff]
    if len(recent) < 4:
        recent = history[-12:] if len(history) >= 12 else history

    xs = [date.fromisoformat(h["date"]).toordinal() for h in recent]
    ys = [h["effective_per_task_usd"] for h in recent]

    # Fit in log-space so projections stay positive and decay multiplicatively.
    import math
    log_ys = [math.log(max(y, 1e-9)) for y in ys]
    slope, intercept, residual_std = linear_fit(xs, log_ys)

    last_x = xs[-1]
    out = []
    for d_offset in range(30, horizon_days + 1, 30):
        x = last_x + d_offset
        log_pred = slope * x + intercept
        pred = math.exp(log_pred)
        # 1-sigma band in log space
        low = math.exp(log_pred - residual_std)
        high = math.exp(log_pred + residual_std)
        out.append({
            "date": date.fromordinal(x).isoformat(),
            "projected_per_task_usd": round(pred, 6),
            "band_low_per_task_usd": round(low, 6),
            "band_high_per_task_usd": round(high, 6),
        })
    return out


def subsidy_runway_months(history, asymptote):
    """Months until projected frontier floor reaches the asymptote (estimated
    cost-to-serve floor). Returns 0 if already at or below."""
    if len(history) < 4 or asymptote is None:
        return None
    import math
    recent = history[-12:] if len(history) >= 12 else history
    xs = [date.fromisoformat(h["date"]).toordinal() for h in recent]
    ys = [math.log(max(h["effective_per_task_usd"], 1e-9)) for h in recent]
    slope, intercept, _ = linear_fit(xs, ys)
    last = recent[-1]["effective_per_task_usd"]
    if slope >= 0 or last <= asymptote:
        return 0
    # Solve slope * x + intercept = log(asymptote)
    target = math.log(asymptote)
    x_target = (target - intercept) / slope
    days_remaining = x_target - xs[-1]
    return round(days_remaining / 30.0, 1)


def asymptote_from_cost(cost_bands):
    """Cost-to-serve mid for a frontier task at the default mix."""
    f_out = next((b for b in cost_bands["bands"] if b["tier"] == "frontier" and b["tokens"] == "output"), None)
    f_in = next((b for b in cost_bands["bands"] if b["tier"] == "frontier" and b["tokens"] == "input"), None)
    if not f_out or not f_in:
        return None
    return (
        (DEFAULT_INPUT_TOKENS / 1_000_000) * f_in["mid_per_mtok_usd"]
        + (DEFAULT_OUTPUT_TOKENS / 1_000_000) * f_out["mid_per_mtok_usd"]
    )


def compute():
    prices = load(DATA / "prices.json")
    providers = load(DATA / "providers.json")
    costs = load(DATA / "cost_to_serve.json")
    overhang = load(DATA / "capacity_overhang.json")
    history_path = DATA / "index_history.json"
    run_log = load(history_path).get("snapshots", []) if history_path.exists() else []

    active_models = load_active_models(providers)
    latest = latest_per_model_active(prices["observations"], active_models)

    frontier_floor = floor_by_tier(latest, is_frontier)
    budget_floor = floor_by_tier(latest, is_budget)
    margin = implied_margin(latest, costs)
    overhang_obs = latest_overhang(overhang)

    # Build full historical series (uses ALL observations, not just active)
    frontier_history = historical_floor_series(prices["observations"], is_frontier)
    budget_history = historical_floor_series(prices["observations"], is_budget)

    asym = asymptote_from_cost(costs)
    runway = subsidy_runway_months(frontier_history, asym)
    forecast = forecast_series(frontier_history)

    # History-based signal checks
    flat_2mo = False
    if len(frontier_history) >= 3:
        last3 = frontier_history[-3:]
        if last3[0]["effective_per_task_usd"] <= last3[1]["effective_per_task_usd"] <= last3[2]["effective_per_task_usd"]:
            flat_2mo = True

    overhang_shrinking = False
    if run_log:
        prev_overhang = run_log[-1].get("capacity_overhang") if run_log else None
        if prev_overhang and overhang_obs and prev_overhang.get("overhang_ratio") and overhang_obs.get("overhang_ratio"):
            if overhang_obs["overhang_ratio"] < prev_overhang["overhang_ratio"]:
                overhang_shrinking = True

    signals = {
        "frontier_floor_flat_2mo": flat_2mo,
        "implied_margin_positive": (margin is not None and margin > 0),
        "capacity_overhang_shrinking": overhang_shrinking,
    }

    if signals["frontier_floor_flat_2mo"] and signals["implied_margin_positive"] and signals["capacity_overhang_shrinking"]:
        verdict = "subsidy_ending"
    elif not signals["implied_margin_positive"]:
        verdict = "active_subsidy"
    else:
        verdict = "transitioning"

    snapshot = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "frontier_floor": frontier_floor,
        "budget_floor": budget_floor,
        "implied_margin": margin,
        "capacity_overhang": overhang_obs,
        "subsidy_runway_months": runway,
        "cost_to_serve_asymptote_per_task_usd": round(asym, 6) if asym else None,
        "signals": signals,
        "verdict": verdict,
    }

    SITE.mkdir(parents=True, exist_ok=True)
    with open(SITE / "index.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    with open(SITE / "history.json", "w", encoding="utf-8") as f:
        json.dump({
            "frontier": frontier_history,
            "budget": budget_history,
        }, f, indent=2)
    with open(SITE / "forecast.json", "w", encoding="utf-8") as f:
        json.dump({
            "horizon_days": FORECAST_HORIZON_DAYS,
            "asymptote_per_task_usd": round(asym, 6) if asym else None,
            "frontier_projection": forecast,
        }, f, indent=2)

    run_log.append(snapshot)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump({"snapshots": run_log}, f, indent=2)

    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    compute()
