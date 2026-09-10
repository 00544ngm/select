# Universal Product Stickiness V2 Verification

Date: 2026-07-29
Branch: `codex/universal-product-stickiness-v2`
Model contract: `combination_model_v2.0`

## Automated checks

- Python focused domain/service/integration checks: passed.
- Full-category regression matrix: `8 passed`.
- Full Python suite: `271 passed` with Redis temporarily started at `127.0.0.1:6379`; two existing async cleanup warnings remain.
- Frontend suite: `108 passed` across `18` files.
- `npm run typecheck`: passed.
- `npm run build`: passed with Next.js production output.
- Targeted Ruff checks for changed backend files: passed.

## Regression matrix

The fixture covers kitchen, printing, oral care, cameras, bedding, automotive, and apparel. Lifecycle, dependency, refill, compatibility, protection, and maintenance relationships outrank same-category/weak-context candidates. Included products and incompatible automotive/camera products are hard-rejected before scoring.

No candidate can claim E4 from this fixture. E4 is reserved for transaction evidence that is not produced by the Walmart search verifier.

## Data integrity checks

- Final score, cap, recommendation, rejection codes, evidence records, and product profile are persisted in JSON and exported to Excel from saved DTO values.
- Historical highlights ignore rejected directions and use `final_score`, with a legacy `score` fallback.
- Market search failures retain `failure_reason` without downgrading an existing E1 source-fact evidence level.
- The LLM contract contains no model-authored final score, evidence level, cap, or recommendation field.
- Product, keyword, scraper, provider, judgment, and profit-calculation paths were not changed.

## Link-driven pairing filter update

- Main-product input remains the user-provided product URL; no爆品 label is used in the core pairing score.
- 粘性 score is five-dimensional: functional necessity (30), usage continuity (25), scene fit (20), enhancement/maintenance/protection (15), and natural co-purchase (10).
- Edible food, drinks, seasonings, ingredients, and ingestible supplements are hard-filtered. Non-food consumables such as ink cartridges, filters, batteries, blades, and cleaning tools remain eligible.
- Context-aware filtering prevents false food matches for Spice Rack, Food Processor, and Spice Grinder; Camera Lens, USB-C Cable, and Kitchen Scissors remain eligible for scoring.
- Relation reasons, purchase chain, extended scenarios with assumptions, food-filter status, confidence, and market-evidence status are persisted in JSON, Excel, history, and the structured workbench.
- Legacy directions without new fields remain readable; their scorecard shows pending verification and raw deep-analysis fields under a collapsed view.

## Updated automated checks

- Backend full suite: `280 passed`, 2 pre-existing async cleanup warnings.
- Frontend full suite: `109 passed` across 18 files.
- Targeted structured workbench regression: `17 passed`.
- `npm run typecheck`: passed.
- `npm run build`: passed with Next.js production output.

## Real provider run

Not executed in this verification pass. The worktree has no usable provider secret/configuration and Redis is unavailable, so a real custom Anthropic-compatible task cannot be honestly marked complete. The automated path is ready for a run once the existing provider configuration and Redis service are available; credentials must not be written to this document.
