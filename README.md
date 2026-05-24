# Cost of Intelligence (COI)

**What is the cost of intelligence — and when does the floor crack?**

A public, open dataset and forecast model tracking the per-token price of frontier and budget AI models across every major provider. The headline metric is the **Subsidy Index**, designed to estimate how many months of runway remain before below-cost pricing normalizes upward.

When subsidies end, the Subsidy Index becomes a footnote. COI keeps going — because the question "what does intelligence cost?" outlives any particular pricing regime.

---

## The thesis

Subsidy collapse is coming. OpenAI is reportedly losing $1.35 per dollar earned on inference. Anthropic, Google, Meta, xAI, and DeepSeek are all pricing inference below cost-to-serve to capture share. The headline $/MTok numbers are misleading — tokenizer drift (e.g. Opus 4.7's +35% tokens-per-text) inflates effective cost-per-task even when the sticker stays flat.

Enterprises are budgeting against 2024 token rates while consuming at 2026 agentic volumes. When the floor moves, planning spreadsheets break.

COI exists to instrument the floor.

---

## The Subsidy Index

A composite published continuously, with four components:

| Component | What it measures | Source |
|---|---|---|
| **Frontier Floor** | Cheapest frontier-tier $/effective-task (Opus 4.7, GPT-5, Gemini Ultra, Grok-4) | Provider APIs run against a fixed benchmark corpus |
| **Budget Floor** | Cheapest budget-tier $/effective-task (Haiku, Nano, Flash, DeepSeek V3, Mistral Small) | Same |
| **Implied Margin** | Market price ÷ SemiAnalysis cost-to-serve band | SemiAnalysis published estimates + GPU spot rates |
| **Capacity Overhang** | Announced hyperscaler capex divided by token demand growth | Earnings calls + Goldman macro |

**Headline output:** `Subsidy Runway = months until Frontier Floor stops falling`, derived from a rolling regression of effective price-per-task against the four components. Not a binary flag — a curve with a confidence band.

**Three signals must all flip before COI calls "subsidy ending":**

1. Frontier Floor flat or rising for 2+ consecutive months
2. Implied Margin crosses zero from below
3. Capacity Overhang shrinking

This distinguishes "prices stable because supply caught up" (good for buyers) from "prices stable because subsidy ran out" (bad for buyers). Identical on a price chart, totally different here.

---

## Why this isn't already done

Existing tools:

- **pricepertoken.com, CostGoat, BenchLM, TLDL** — snapshot price comparison
- **Langfuse** — track your own usage
- **CloudZero, Finout** — enterprise spend management

None of them publish a forward-looking subsidy-window estimate. They tell you what Opus costs today. COI tells you how long today's price is likely to last.

---

## Providers tracked (v1)

- Anthropic (Opus, Sonnet, Haiku families)
- OpenAI (GPT-5 series, Nano, o-series)
- Google (Gemini Ultra, Pro, Flash, Nano)
- DeepSeek (V3, R-series)
- Mistral (Large, Medium, Small)
- xAI (Grok-4 family)

Meta Llama is included via hosted-endpoint pricing (Together, DeepInfra, Groq) as a proxy until Meta publishes first-party rates.

---

## Benchmark corpora

"Effective $/task" requires a fixed reference. COI uses three layers stacked:

1. **Established public benchmarks**: MMLU, GPQA Diamond, HumanEval, SWE-Bench Verified
2. **A COI custom corpus**: 10 fixed prompts spanning short Q&A, long-context reasoning, code generation, tool use, and structured extraction
3. **A token-density probe**: a fixed 5,000-word reference text submitted monthly to detect tokenizer drift

Per-task cost is computed as `(input_tokens × input_price + output_tokens × output_price)` averaged across the three layers. The custom corpus is the most stable; the public benchmarks are the most comparable; the density probe is the canary for tokenizer changes.

---

## Cadence

- **Daily**: GitHub Actions workflow scrapes provider pricing pages and benchmark APIs, recomputes the index, commits any deltas.
- **Event-driven**: A `workflow_dispatch` trigger lets anyone fire an immediate refresh when a provider announces a price change.
- **Monthly**: A summary post is published with the prior month's deltas and forecast revision.

The maintainer (Dale) does not intervene in the daily pipeline. Everything runs unattended.

---

## How to contribute

The world is invited. See [`CONTRIBUTING.md`](CONTRIBUTING.md). Short version:

- **Add a provider or model**: PR to `data/providers.json`
- **Propose a new benchmark**: PR to `benchmarks/` with a runnable script
- **Improve the index math**: PR to `scrapers/index_calc.py` with a justification in the PR description
- **Just report a price change**: open an Issue using the "Price update" template; CI will validate and a maintainer auto-merges

No maintainer review queue. CI is the gate. The goal is for a 13-year-old in Bangladesh with better methodology to take this over.

---

## License

- **Code**: MIT
- **Data**: CC0 (public domain, no attribution required)

Use it, fork it, sell consulting on top of it, publish a paper, embed it in a product. No permission needed.

---

## Hosting

- **Canonical site**: [dlerhetal.tech/cost-of-intelligence/](https://dlerhetal.tech/cost-of-intelligence/) (embed)
- **Source + data + dashboard**: GitHub Pages on the public repo

Both stay in sync — dlerhetal.tech pulls from the same `index.json` the dashboard renders.

---

## Maintainer

Dale Linn. The project is intended to outlive my attention; design choices prefer "runs unattended" over "depends on me being awake."
