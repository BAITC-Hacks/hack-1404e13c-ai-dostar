# AI-Dostar: team memory

This file is committed with the project and read by coding agents at the start of a task. Add verified, durable facts here before each relevant commit or push. Replace outdated entries when a decision changes; do not accumulate contradictory notes.

## Project

- Repository: `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar`.
- Purpose: HackAlem AI case «Электрокомплект» — сервис рекомендованных заказов поставщикам (IEK, Systeme Electric).
- Architecture for the 4h MVP: `docs/architecture.md` (Python modular monolith + Streamlit, no DB/microservices). The long `SupplyAI_ARCHITECTURE.md` is the post-hackathon target; its domain rules are folded into `docs/architecture.md`.

## Progress (обновлять при каждом push)

Статус на 2026-09-23: готовы 2.0, 2.1 (Человек 2) и 1.1 (Человек 1). Подробные задачи и владельцы — `docs/tasks.md`.

**Сделано (в `main`):**

| Что | Где | Коммит |
|---|---|---|
| Анализ ТЗ и реальных данных, расхождения с ТЗ и допущения | `docs/architecture.md` §2 | `defea03` |
| MVP-архитектура на 4 часа (монолит + Streamlit); `SupplyAI_ARCHITECTURE.md` — целевая, не для хакатона | `docs/architecture.md` | `defea03` |
| Контракт данных | `app/schema.py` | `defea03`, `960393f` |
| Адаптеры IEK и SE → parquet (8 таблиц, ~8 с), smoke-тесты | `app/adapters/`, `tests/test_adapters.py` | `defea03` |
| Разделение на 3 человека, владение файлами, таймлайн, правила git, шаблон промпта | `docs/tasks.md` | `d2b98bc` |
| **Задача 2.0**: каркас движка, `pipeline.run()` работает на реальных данных (~3 с) | `app/engine/`, `app/pipeline.py` | `960393f` |
| Заготовки для Продукта: Streamlit (мок ↔ реальный расчет), мок, экспорт, copilot | `app/ui/app.py`, `app/mock.py`, `app/export.py`, `app/copilot.py` | `960393f` |
| Тесты приемки (must-have 2–4 пока `xfail`) | `tests/test_acceptance.py`, `tests/test_demand.py` | `960393f` |
| **Задача 2.1**: прогноз с сезонностью (SKU → группа → компания), устойчивый тренд, робастная σ; методика | `app/engine/forecast.py`, `docs/methodology-forecast.md` | `dcc294b` |
| **Задача 1.1** (Человек 1): поиск разовых строк накладных | `app/engine/oneoffs.py` | `ef7cd5d` |
| Конвертер xlsx → csv (Windows-пути `C:/Hackathon/datasets`) — вспомогательный, pipeline читает xlsx через адаптеры | `scripts/excel_to_csv.py` | `d3c84ef` |

**Тесты сейчас:** 14 passed, 1 xfailed. Закрыты must-have №2 (сезонность и рост) и №4 (разовые заказы: Петля исключена, Коробки нет). Остался `xfail`: дефициты (1.2).

**Что в каркасе заглушка, а что уже настоящее:**

| Модуль | Настоящее | Заглушка → кто делает |
|---|---|---|
| `engine/oneoffs.py` | **готово (1.1)**: median/MAD + доля месяца + нерегулярность, fallback по категории | — |
| `engine/demand.py` | сетка месяцев 2025-01..as_of, нетто продажи, вычет разовых, флаг stockout, неполный текущий месяц | uplift за дефицит = 0 → Человек 1, задача 1.2 |
| `engine/forecast.py` | **готово (2.1)**: сезонность с усадкой, тренд, рост, робастная σ | — |
| `engine/replenish.py` | вся формула: в пути в горизонте, z·σ·√LT, кратность, срочность, `needs_review` | мелкие доработки → Человек 2, задача 2.2 |
| `engine/explain.py` | шаблонное обоснование из чисел | формулировки → Человек 2, задача 2.3 |
| `app/ui/app.py` | таблица по поставщикам, переключатель мок/реальные | вкладки, редактирование, утверждение → Человек 3, 3.1–3.7 |
| `app/export.py` | `to_table`, `to_xlsx`, защита от формул | кнопки в UI → Человек 3, 3.3 |

**Следующие шаги:**

- Человек 1 — 1.2 uplift за дефицит (снять `xfail` с `test_3_stockout_fix_raises_demand` — скажи Человеку 2 или сними сам), 1.3 тесты, 1.4 отчет для UI.
- Человек 2 — 2.2 (проверить крайние случаи пополнения), 2.3 формулировки обоснования, 2.4 оставшиеся приемочные тесты.
- Человек 3 — 3.1–3.3 на моке; в 1:10 выключить «Мок-данные» и работать с `pipeline.run()`.

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

- 2026-09-23: `python scripts/excel_to_csv.py` converts every worksheet from `C:/Hackathon/datasets/IEK` and `C:/Hackathon/datasets/Systeme electric` into UTF-8 CSV in sibling `_CSV` folders. Verified output: 5 CSV from 5 IEK books and 8 CSV from 6 SE books; requires `openpyxl` from `requirements.txt`. Source workbooks are left unchanged.
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

- 2026-09-23: Task 1.5: `docs/methodology-demand.md` now documents implemented thresholds, singleton-category fallback, stockout formulas, partial months, switches, report fields and data limitations. Tasks 1.2–1.5 each have a separate commit. Final suite: 34 passed, 1 xpassed. Remaining integration for Person 2: pass company `seasonality` to `build_monthly` and remove the passing stockout acceptance test's xfail marker. Until then pipeline stockout correction uses coefficient 1 (module accepts and tests real company coefficients).
- 2026-09-23: Task 1.4: `oneoffs.report()` includes `typical_qty` (= original qty minus excluded excess) and `unit`, alongside supplier/SKU/date/invoice/reason. Only flagged lines are returned, largest first, with a fresh index; source facts are not mutated. Two report regression tests pass, including empty output.
- 2026-09-23: Task 1.3: 19 demand tests pass on Windows (`.venv\Scripts\python.exe -m pytest tests/test_demand.py -q`), including actual LOOP/SE cases and synthetic 50x injection, recurrence, returns, seasonality, partial months and switches. Only real-data fixtures skip when parquet is absent. A regression test exposed and fixed the one-off filter's date cutoff: include the entire as_of day, exclude future recurrence.
- 2026-09-23: Task 1.2 implemented. `build_monthly(..., as_of, seasonality=None)` estimates missing demand from the median of at least two complete stocked months, adjusted by company seasonality and observed fraction of the current month. No uplift before the product's first activity; returns and one-off reductions are applied before estimation. Final-day sales are included. Optional seasonality defaults to 1; Person 2 needs to pass `seasonality=data["seasonality"]` in `pipeline.run`. Real-data/module checks passed (1,399 estimated stockout months with company factors); suite: 14 passed, 1 xpassed (stockout acceptance marker remains owned by Person 2).
- 2026-09-23: Task 1.1 implemented in `app/engine/oneoffs.py`: positive invoice lines use per-SKU median/MAD, >30% share of SKU-month, and comparable-volume recurrence across months. A SKU with just one sale uses the 90th/99th category percentiles only when at least 100 peer lines exist. On real data, IEK LOOP 210,000 is excluded (typical category line 10); recurring SE boxes 36–90k are retained. Pytest: 11 passed, 2 xfailed, 1 xpassed (`test_4_loop_one_off_excluded`; Person 2 owns its xfail marker).

## Расчет

- 2026-09-23: Task 2.0 skeleton pushed. Engine files exist with working stubs: `flag_oneoffs` flags nothing, `build_monthly` builds the month grid 2025-01..as_of with stockout flag but uplift = 0, `forecast` = 12-month average with seasonal_index = trend = 1, `replenish.calc` implements the full formula (horizon transit, z·σ·√LT safety, pack rounding, urgency, needs_review when stock is missing), `explain` builds a template rationale.
- `as_of` defaults to the last sale date (2026-09-22). Every engine function takes `(…, params, as_of)`.
- 2026-09-23: Task 2.1 done. Forecast history = rescaled 2024 monthly report + invoice `qty_regular` from 2025 (full months only). Seasonal index per calendar month: ratio to centred 12-month MA, shrunk SKU → product group (n/(n+24)) → company (n/(n+12)), clipped 0.4–2.5. Trend only if sustained (OLS slope sign = last-6 vs prev-6 sign, ≥8 of 12 nonzero months), damped ×0.5, capped 0.8–1.25. σ = 1.4826·MAD of residuals. Details: `docs/methodology-forecast.md`.
- Seasonal demo SKU: IEK `130300792_` «Труба гибкая Ø50» — seasonal index 0.41 (Feb), 1.05 (Jun), 2.03 (Sep–Oct horizon). Also `130300791_` Ø40.
- Safety-stock issue resolved by robust σ: pipes safety 2 764 vs forecast 11 976 (was larger than forecast). Result now: 842 SKUs with recommended_qty > 0; ~38% SKUs have trend ≠ 1.
- `avg_daily_regular` is the deseasonalised base; the rationale shows seasonality/trend as separate factors.

## Продукт

(Person 3 notes)
