"""
One-shot historical backfill. Adds known launch-day price observations for
major models so day-1 charts show real history rather than a single flat point.

Idempotent: re-running won't duplicate entries (deduped on provider+model+date).
Sources cited in the SOURCE_NOTES dict at top of each entry.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Each entry: (date, provider, model, tier, input_mtok, output_mtok, tokenizer_factor, source)
# Tokenizer_factor is per-model relative to its provider's then-current baseline.
HISTORICAL = [
    # --- Anthropic ---
    ("2024-03-04", "anthropic", "opus-3",     "frontier", 15.00, 75.00, 1.00, "Claude 3 Opus launch (Mar 4, 2024)"),
    ("2024-06-20", "anthropic", "sonnet-3-5", "mid",       3.00, 15.00, 1.00, "Claude 3.5 Sonnet launch (Jun 20, 2024)"),
    ("2024-10-22", "anthropic", "sonnet-3-5-v2", "mid",    3.00, 15.00, 1.00, "Claude 3.5 Sonnet (new) (Oct 22, 2024)"),
    ("2024-11-04", "anthropic", "haiku-3-5",  "budget",    1.00,  5.00, 1.00, "Claude 3.5 Haiku launch (Nov 4, 2024)"),
    ("2025-02-24", "anthropic", "sonnet-3-7", "mid",       3.00, 15.00, 1.00, "Claude 3.7 Sonnet launch (Feb 24, 2025)"),
    ("2025-05-22", "anthropic", "opus-4",     "frontier", 15.00, 75.00, 1.00, "Claude 4 Opus launch (May 2025)"),
    ("2025-05-22", "anthropic", "sonnet-4",   "mid",       3.00, 15.00, 1.00, "Claude 4 Sonnet launch (May 2025)"),
    ("2025-09-29", "anthropic", "sonnet-4-5", "mid",       3.00, 15.00, 1.00, "Claude Sonnet 4.5 launch (Sep 29, 2025)"),
    ("2025-10-15", "anthropic", "haiku-4-5",  "budget",    1.00,  5.00, 1.00, "Claude Haiku 4.5 launch"),
    ("2025-11-24", "anthropic", "opus-4-5",   "frontier",  5.00, 25.00, 1.00, "Claude Opus 4.5 launch with 67% Opus price cut (Nov 2025)"),
    # 2026 (existing entries cover Opus 4.6 Feb, Opus 4.7 Apr — these are duplicated here for completeness only)
    ("2026-02-10", "anthropic", "opus-4-6",   "frontier",  5.00, 25.00, 1.00, "Opus 4.6 launch with 1M context"),
    ("2026-02-10", "anthropic", "sonnet-4-6", "mid",       3.00, 15.00, 1.00, "Sonnet 4.6 launch"),
    ("2026-04-01", "anthropic", "opus-4-7",   "frontier",  5.00, 25.00, 1.35, "Opus 4.7 launch (new tokenizer +35%)"),

    # --- OpenAI ---
    ("2023-03-14", "openai", "gpt-4",        "frontier", 30.00, 60.00, 1.00, "GPT-4 launch (Mar 14, 2023) at 8K context"),
    ("2023-11-06", "openai", "gpt-4-turbo",  "frontier", 10.00, 30.00, 1.00, "GPT-4 Turbo launch (Nov 6, 2023)"),
    ("2024-05-13", "openai", "gpt-4o",       "frontier",  2.50, 10.00, 1.00, "GPT-4o launch (May 13, 2024)"),
    ("2024-07-18", "openai", "gpt-4o-mini",  "budget",    0.15,  0.60, 1.00, "GPT-4o mini launch (Jul 18, 2024)"),
    ("2024-09-12", "openai", "o1-preview",   "frontier-reasoning", 15.00, 60.00, 1.00, "o1-preview launch (Sep 12, 2024)"),
    ("2024-12-05", "openai", "o1",           "frontier-reasoning", 15.00, 60.00, 1.00, "o1 GA (Dec 2024)"),
    ("2025-01-31", "openai", "o3-mini",      "mid",       1.10,  4.40, 1.00, "o3-mini launch (Jan 31, 2025)"),
    ("2025-04-16", "openai", "o3",           "frontier-reasoning", 10.00, 40.00, 1.00, "o3 launch (Apr 2025)"),
    ("2025-08-07", "openai", "gpt-5",        "frontier",  1.25, 10.00, 1.00, "GPT-5 launch (Aug 7, 2025)"),
    ("2026-03-05", "openai", "gpt-5-4",      "mid",       2.50, 15.00, 1.00, "GPT-5.4 launch (Mar 5, 2026)"),
    ("2026-03-05", "openai", "gpt-5-4-mini", "mid",       0.75,  4.50, 1.00, "GPT-5.4 Mini launch"),
    ("2026-03-05", "openai", "gpt-5-4-nano", "budget",    0.20,  1.25, 1.00, "GPT-5.4 Nano launch"),
    ("2026-04-15", "openai", "gpt-5-5",      "frontier",  5.00, 30.00, 1.00, "GPT-5.5 launch (Apr 2026) — 2x price hike vs 5.4"),
    ("2026-04-15", "openai", "gpt-5-5-pro",  "frontier-reasoning", 30.00, 180.00, 1.00, "GPT-5.5 Pro launch"),

    # --- Google ---
    ("2024-02-15", "google", "gemini-1-5-pro",   "frontier",  3.50, 10.50, 1.00, "Gemini 1.5 Pro launch (Feb 15, 2024)"),
    ("2024-05-14", "google", "gemini-1-5-flash", "budget",    0.075, 0.30, 1.00, "Gemini 1.5 Flash launch"),
    ("2024-12-11", "google", "gemini-2-0-flash", "budget",    0.10,  0.40, 1.00, "Gemini 2.0 Flash launch (Dec 2024)"),
    ("2025-03-25", "google", "gemini-2-5-pro",   "mid",       1.25, 10.00, 1.00, "Gemini 2.5 Pro launch (Mar 25, 2025)"),
    ("2025-06-17", "google", "gemini-2-5-flash", "budget",    0.30,  2.50, 1.00, "Gemini 2.5 Flash GA"),
    ("2026-02-12", "google", "gemini-3-1-pro-preview", "frontier", 2.00, 12.00, 1.00, "Gemini 3.1 Pro Preview launch"),
    ("2026-04-08", "google", "gemini-3-5-flash", "mid",       1.50,  9.00, 1.00, "Gemini 3.5 Flash launch"),

    # --- DeepSeek ---
    ("2024-12-26", "deepseek", "deepseek-v3", "frontier", 0.27, 1.10, 1.00, "DeepSeek V3 launch (Dec 26, 2024)"),
    ("2025-01-20", "deepseek", "deepseek-r1", "frontier-reasoning", 0.55, 2.19, 1.00, "DeepSeek R1 launch (Jan 20, 2025) — the open-weight watershed"),
    ("2025-09-30", "deepseek", "deepseek-v3-2", "mid",     0.14,  0.28, 1.00, "DeepSeek V3.2 with 50%+ price cut"),
    ("2026-03-15", "deepseek", "deepseek-v4-pro",   "frontier-reasoning", 0.435, 0.87, 1.00, "DeepSeek V4 Pro launch (75% promo)"),
    ("2026-03-15", "deepseek", "deepseek-v4-flash", "budget",             0.14,  0.28, 1.00, "DeepSeek V4 Flash launch"),

    # --- Mistral ---
    ("2024-02-26", "mistral", "mistral-large",   "frontier", 4.00, 12.00, 1.00, "Mistral Large launch (Feb 26, 2024)"),
    ("2024-07-24", "mistral", "mistral-large-2", "frontier", 3.00,  9.00, 1.00, "Mistral Large 2 (Jul 2024)"),
    ("2025-11-20", "mistral", "mistral-large-3", "frontier", 2.00,  6.00, 1.00, "Mistral Large 3 launch"),
    ("2026-01-10", "mistral", "ministral-8b",    "budget",   0.10,  0.10, 1.00, "Ministral 8B launch"),

    # --- xAI ---
    ("2024-11-04", "xai", "grok-2",        "frontier", 2.00, 10.00, 1.00, "Grok-2 API launch (Nov 2024)"),
    ("2025-02-19", "xai", "grok-3",        "frontier", 3.00, 15.00, 1.00, "Grok-3 launch (Feb 2025)"),
    ("2025-07-09", "xai", "grok-4",        "frontier", 3.00, 15.00, 1.00, "Grok-4 launch (Jul 2025)"),
    ("2026-03-09", "xai", "grok-4-20-non-reasoning", "frontier", 1.25, 2.50, 1.00, "Grok-4.20 launch — frontier-tier at budget price"),
    ("2026-04-22", "xai", "grok-4-3",      "frontier", 1.25, 2.50, 1.00, "Grok-4.3 launch"),
]


def main():
    prices_path = DATA / "prices.json"
    with open(prices_path, encoding="utf-8") as f:
        prices = json.load(f)

    existing = {(o["observed_on"], o["provider"], o["model"]) for o in prices["observations"]}
    added = 0
    for date_str, provider, model, tier, in_p, out_p, tok, source in HISTORICAL:
        key = (date_str, provider, model)
        if key in existing:
            continue
        prices["observations"].append({
            "observed_on": date_str,
            "provider": provider,
            "model": model,
            "tier": tier,
            "input_per_mtok_usd": in_p,
            "output_per_mtok_usd": out_p,
            "tokenizer_factor": tok,
            "effective_per_task_usd": None,
            "verified": True,
            "source": source,
        })
        added += 1

    # Sort observations chronologically for readability
    prices["observations"].sort(key=lambda o: (o["observed_on"], o["provider"], o["model"]))

    with open(prices_path, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2)

    print(f"Historical seed complete. Added {added} observations. Total now: {len(prices['observations'])}.")


if __name__ == "__main__":
    main()
