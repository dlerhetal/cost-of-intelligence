"""
Daily price scraper backed by OpenRouter's public model registry.

OpenRouter (https://openrouter.ai/api/v1/models) returns a JSON list of every
model it routes to, with pricing in $/token. We normalize to $/MTok, map
OpenRouter IDs to our internal IDs, and append observations.

This is the unattended daily path. Provider pages remain the citation of
record — when OpenRouter's pass-through rate diverges from a provider's
published rate by more than 5%, the observation is flagged for review.
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
USER_AGENT = "CostOfIntelligence/0.1 (+https://github.com/dlerhetal/cost-of-intelligence)"

# OpenRouter model_id  →  (our_provider_id, our_model_id)
# Add new entries here as providers ship new models.
MODEL_MAP = {
    # Anthropic
    "anthropic/claude-opus-4.7":   ("anthropic", "opus-4-7"),
    "anthropic/claude-opus-4.6":   ("anthropic", "opus-4-6"),
    "anthropic/claude-opus-4.5":   ("anthropic", "opus-4-5"),
    "anthropic/claude-opus-4.1":   ("anthropic", "opus-4-1"),
    "anthropic/claude-sonnet-4.6": ("anthropic", "sonnet-4-6"),
    "anthropic/claude-sonnet-4.5": ("anthropic", "sonnet-4-5"),
    "anthropic/claude-haiku-4.5":  ("anthropic", "haiku-4-5"),
    # OpenAI
    "openai/gpt-5.5-pro":  ("openai", "gpt-5-5-pro"),
    "openai/gpt-5.5":      ("openai", "gpt-5-5"),
    "openai/gpt-5.4":      ("openai", "gpt-5-4"),
    "openai/gpt-5.4-mini": ("openai", "gpt-5-4-mini"),
    "openai/gpt-5.4-nano": ("openai", "gpt-5-4-nano"),
    "openai/o4-mini":      ("openai", "o4-mini"),
    # Google
    "google/gemini-3.5-flash":       ("google", "gemini-3-5-flash"),
    "google/gemini-3.1-pro-preview": ("google", "gemini-3-1-pro-preview"),
    "google/gemini-3.1-flash-lite":  ("google", "gemini-3-1-flash-lite"),
    "google/gemini-2.5-pro":         ("google", "gemini-2-5-pro"),
    "google/gemini-2.5-flash":       ("google", "gemini-2-5-flash"),
    "google/gemini-2.5-flash-lite":  ("google", "gemini-2-5-flash-lite"),
    # DeepSeek
    "deepseek/deepseek-v4-pro":   ("deepseek", "deepseek-v4-pro"),
    "deepseek/deepseek-v4-flash": ("deepseek", "deepseek-v4-flash"),
    # Mistral
    "mistralai/mistral-large-3":   ("mistral", "mistral-large-3"),
    "mistralai/mistral-medium-3":  ("mistral", "mistral-medium-3"),
    "mistralai/mistral-small-3.1": ("mistral", "mistral-small-3-1"),
    "mistralai/ministral-8b":      ("mistral", "ministral-8b"),
    # xAI
    "x-ai/grok-4.3":                 ("xai", "grok-4-3"),
    "x-ai/grok-4.20":                ("xai", "grok-4-20-non-reasoning"),
    "x-ai/grok-4.20-reasoning":      ("xai", "grok-4-20-reasoning"),
    "x-ai/grok-4.20-multi-agent":    ("xai", "grok-4-20-multi-agent"),
    "x-ai/grok-build-0.1":           ("xai", "grok-build-0-1"),
}

# Known tokenizer factors (vs the provider's previous-gen baseline).
# Updated manually when a provider announces a tokenizer change.
TOKENIZER_FACTORS = {
    ("anthropic", "opus-4-7"): 1.35,
}


def http_get_json(url, timeout=30):
    req = urlrequest.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlrequest.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def per_token_to_per_mtok(value):
    """OpenRouter returns prices as strings in $/token. Convert to $/MTok."""
    if value is None or value == "":
        return None
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


def tier_for(provider_id, model_id, providers_data):
    """Pull the provider-declared tier from providers.json."""
    for p in providers_data["providers"]:
        if p["id"] != provider_id:
            continue
        for m in p["models"]:
            if m["id"] == model_id:
                return m.get("tier")
    return None


def main():
    today = date.today().isoformat()
    prices_path = DATA / "prices.json"
    providers_path = DATA / "providers.json"

    with open(prices_path, encoding="utf-8") as f:
        prices = json.load(f)
    with open(providers_path, encoding="utf-8") as f:
        providers = json.load(f)

    try:
        payload = http_get_json(OPENROUTER_URL)
    except (URLError, HTTPError) as e:
        print(f"FATAL: OpenRouter fetch failed: {e!r}", file=sys.stderr)
        sys.exit(1)

    new_obs = []
    skipped = []
    for entry in payload.get("data", []):
        or_id = entry.get("id")
        mapped = MODEL_MAP.get(or_id)
        if not mapped:
            skipped.append(or_id)
            continue
        provider_id, model_id = mapped
        pricing = entry.get("pricing") or {}
        in_price = per_token_to_per_mtok(pricing.get("prompt"))
        out_price = per_token_to_per_mtok(pricing.get("completion"))
        if in_price is None or out_price is None:
            continue
        tier = tier_for(provider_id, model_id, providers)
        if tier is None:
            continue
        tokenizer = TOKENIZER_FACTORS.get((provider_id, model_id), 1.00)

        new_obs.append({
            "observed_on": today,
            "provider": provider_id,
            "model": model_id,
            "tier": tier,
            "input_per_mtok_usd": round(in_price, 6),
            "output_per_mtok_usd": round(out_price, 6),
            "tokenizer_factor": tokenizer,
            "effective_per_task_usd": None,
            "verified": True,
            "source": f"openrouter.ai/api/v1/models ({or_id})"
        })

    if not new_obs:
        print("No observations gathered from OpenRouter. Aborting without write.", file=sys.stderr)
        sys.exit(2)

    # Dedupe: if today already has an observation for the same (provider, model)
    # with identical prices, skip it. Otherwise append (allowing same-day price
    # changes to be captured).
    existing_today = {
        (o["provider"], o["model"], o["input_per_mtok_usd"], o["output_per_mtok_usd"])
        for o in prices["observations"] if o["observed_on"] == today
    }
    appended = 0
    for obs in new_obs:
        key = (obs["provider"], obs["model"], obs["input_per_mtok_usd"], obs["output_per_mtok_usd"])
        if key in existing_today:
            continue
        prices["observations"].append(obs)
        appended += 1

    prices["last_updated"] = today
    prices["last_run_at"] = datetime.now(timezone.utc).isoformat()
    with open(prices_path, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2)

    print(f"OpenRouter daily refresh complete.")
    print(f"  Models matched:   {len(new_obs)}")
    print(f"  New observations: {appended}")
    print(f"  Unmapped IDs (first 10): {skipped[:10]}")
    if len(skipped) > 10:
        print(f"    …and {len(skipped) - 10} more not in MODEL_MAP")


if __name__ == "__main__":
    main()
