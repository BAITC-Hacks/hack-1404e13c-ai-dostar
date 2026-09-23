# AI-Dostar: team memory

This file is committed with the project and read by coding agents at the start of a task. Add verified, durable facts here before each relevant commit or push. Replace outdated entries when a decision changes; do not accumulate contradictory notes.

## Project

- Repository: `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar`.
- Purpose: HackAlem AI case «Электрокомплект» — сервис рекомендованных заказов поставщикам (IEK, Systeme Electric).
- Architecture for the 4h MVP: `docs/architecture.md` (Python modular monolith + Streamlit, no DB/microservices). The long `SupplyAI_ARCHITECTURE.md` is the post-hackathon target; its domain rules are folded into `docs/architecture.md`.

## Decisions

- 2026-09-23: Team memory lives in this Markdown file and is shared through Git. No Mem0 account or plugin is required for this repository. The repo-level Codex config disables an already-installed Mem0 plugin here.
- 2026-09-23: Agents read this file at task start and update it with meaningful, verified changes before pushing.

- 2026-09-23: Real data verified: no client_id, no price, no stockout file, no lead times, no BOM; sales only warehouse «Алматы»; usable transactions from 01.2025, monthly sales/stock from 01.2024. Gaps and workarounds are listed in `docs/architecture.md` §2.
- 2026-09-23: One-off detection unit = invoice line (`doc_id`+SKU). Control cases: IEK «Петля металлическая LOOP» 210000 шт 09.06.2025 must be excluded; SE «Установочная коробка» 36–90k шт recurring must not.
- 2026-09-23: SE «Товар в пути» xlsx is the manager's current Excel calculation — use as baseline for comparison in the demo.
- Raw partner xlsx live in `data/raw/` (gitignored). Unzip with `unzip -O cp866` (Cyrillic names).

- 2026-09-23: Invoice lines are the primary demand source; the monthly sales report is used only for the 2024 seasonality shape. The two disagree (SE report ≈ 50% of invoices, gap is wholesale box orders) — see `docs/architecture.md` §2.
- 2026-09-23: `products.category` = first 4 digits of the 1C code for both suppliers; SE «Категория 2026» is kept as `manager_baseline.category_abc`. IEK current stock is estimated (Sep start stock − Sep sales), SE current stock comes from the manager file.
- 2026-09-23: Work split and file ownership are in `docs/tasks.md`: Person 1 «Спрос» (oneoffs, demand series), Person 2 «Расчет» (schema owner, forecast, replenish, explain, pipeline, acceptance tests), Person 3 «Продукт» (Streamlit UI, approval, export, README, demo). Split is by file ownership inside the monolith, not by microservices. Person 2 pushes the skeleton (task 2.0) first.
- 2026-09-23: Git: work directly on `main`, `git add` only own files, `git pull --rebase` + pytest before push, commit prefixes `demand:` / `calc:` / `ui:`. `app/schema.py` columns may be added, never renamed or removed.
- 2026-09-23: Approvals are stored in `data/state/approvals.json` (gitignored). No automatic sending to suppliers.

## Working commands

- Setup: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` (pandas 3.x works).
- Data: unzip partner archives into `data/raw/` (`unzip -O cp866 IEK.zip -d data/raw`), then `.venv/bin/python -m app.adapters.build` → `data/clean/*.parquet` (~8 s).
- In code: `from app.adapters import load_clean; data = load_clean()` → dict of contract tables from `app/schema.py`.
- Tests: `.venv/bin/python -m pytest -q` (tests skip if data/clean is missing). After task 2.0: 11 passed, 3 xfailed (xfail = must-have waiting for its engine step; remove the xfail mark when it passes).
- Pipeline: `from app.pipeline import run; r = run()` → `PipelineResult(order_lines, forecast, demand_monthly, sales_flagged, params, as_of)`; ~3 s on real data.
- UI: `.venv/bin/streamlit run app/ui/app.py` (sidebar toggle «Мок-данные» switches mock ↔ real pipeline).

## Open questions

- How the manager's «Кэф. Роста», «Кэф. Сез-ти» and «Запас» are computed in the SE file (not reverse-engineered yet).
- What the monthly sales report includes/excludes compared to invoices (ask partner).
- Real lead times per supplier (IEK transit headers suggest 12–40 days).

## Спрос

(Person 1 notes)

## Расчет

- 2026-09-23: Task 2.0 skeleton pushed. Engine files exist with working stubs: `flag_oneoffs` flags nothing, `build_monthly` builds the month grid 2025-01..as_of with stockout flag but uplift = 0, `forecast` = 12-month average with seasonal_index = trend = 1, `replenish.calc` implements the full formula (horizon transit, z·σ·√LT safety, pack rounding, urgency, needs_review when stock is missing), `explain` builds a template rationale.
- `as_of` defaults to the last sale date (2026-09-22). Every engine function takes `(…, params, as_of)`.
- Known issue for 2.1/2.2: with σ from monthly std, safety stock is often larger than forecast_H for volatile SKUs (e.g. IEK pipes) — revisit σ once one-offs and seasonality are in.
- Stub result: 2460 SKUs with demand, 1040 with recommended_qty > 0.

## Продукт

(Person 3 notes)
