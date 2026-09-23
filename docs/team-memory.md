# AI-Dostar: team memory

This file is committed with the project and read by coding agents at the start of a task. Add verified, durable facts here before each relevant commit or push. Replace outdated entries when a decision changes; do not accumulate contradictory notes.

## Project

- Repository: `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar`.
- Purpose: HackAlem AI case «Электрокомплект» — сервис рекомендованных заказов поставщикам (IEK, Systeme Electric).
- Architecture for the 4h MVP: `docs/architecture.md` (Python modular monolith + Streamlit, no DB/microservices). The long `SupplyAI_ARCHITECTURE.md` is the post-hackathon target; its domain rules are folded into `docs/architecture.md`.

## Progress (обновлять при каждом push)

Статус на 2026-09-23, код проверен по `660a167`: готовы 2.0, 2.1 (Человек 2), реализованы и отправлены в `main` модули и материалы 1.1–1.5 (Человек 1). Для полного подключения 1.2 человек 2 должен передать таблицу сезонности в `build_monthly`; сейчас в общем pipeline коррекция дефицита работает с коэффициентом 1. Подробная передача результатов — в разделе «Спрос» ниже; владельцы файлов — `docs/tasks.md`.

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
| Каркас приемочных тестов; актуальные результаты и оставшаяся метка `xfail` указаны ниже | `tests/test_acceptance.py`, `tests/test_demand.py` | `960393f` |
| **Задача 2.1**: прогноз с сезонностью (SKU → группа → компания), устойчивый тренд, робастная σ; методика | `app/engine/forecast.py`, `docs/methodology-forecast.md` | `dcc294b` |
| **Задача 1.1** (Человек 1): поиск разовых строк накладных | `app/engine/oneoffs.py` | `ef7cd5d` |
| **Задача 1.2**: оценка упущенного спроса по месяцам, сезонные коэффициенты через необязательный аргумент | `app/engine/demand.py` | `5365e55` |
| **Задача 1.3**: синтетические и реальные проверки спроса, исправление границы дня `as_of` | `tests/test_demand.py`, `app/engine/oneoffs.py` | `099d736` |
| **Задача 1.4**: типичный объём и единица измерения в отчёте о разовых продажах | `app/engine/oneoffs.py`, `tests/test_demand.py` | `d531b8a` |
| **Задача 1.5**: методика с формулами, порогами и ограничениями | `docs/methodology-demand.md` | `660a167` |
| Конвертер xlsx → csv (Windows-пути `C:/Hackathon/datasets`) — вспомогательный, pipeline читает xlsx через адаптеры | `scripts/excel_to_csv.py` | `d3c84ef` |

**Последний полный прогон:** 34 passed, 1 xpassed на реальных parquet-данных (Windows, Python 3.13). В `tests/test_demand.py` теперь 21 проверка, все проходят. `test_3_stockout_fix_raises_demand` тоже проходит, но пока имеет `xfail(strict=False)`, поэтому отображается как XPASS. Человеку 2 нужно снять устаревшую метку; это не провал теста. После подключения сезонности в pipeline нужно повторить полный прогон.

**Что в каркасе заглушка, а что уже настоящее:**

| Модуль | Настоящее | Заглушка → кто делает |
|---|---|---|
| `engine/oneoffs.py` | **готово (1.1, 1.4)**: median/MAD, доля месяца, повторение по месяцам, fallback по категории, отчёт с типичным объёмом | — |
| `engine/demand.py` | **реализовано (1.2)**: регулярный ряд, оценка дефицита, сезонные коэффициенты, неполный месяц, переключатель коррекции | передать `seasonality=data["seasonality"]` из pipeline → Человек 2 |
| `engine/forecast.py` | **готово (2.1)**: сезонность с усадкой, тренд, рост, робастная σ | — |
| `engine/replenish.py` | вся формула: в пути в горизонте, z·σ·√LT, кратность, срочность, `needs_review` | мелкие доработки → Человек 2, задача 2.2 |
| `engine/explain.py` | шаблонное обоснование из чисел | формулировки → Человек 2, задача 2.3 |
| `app/ui/app.py` | таблица по поставщикам, переключатель мок/реальные | вкладки, редактирование, утверждение → Человек 3, 3.1–3.7 |
| `app/export.py` | `to_table`, `to_xlsx`, защита от формул | кнопки в UI → Человек 3, 3.3 |

**Следующие шаги:**

- Человек 1 — реализация 1.1–1.5 и отдельные коммиты уже в `main`; при интеграционных вопросах использовать описание и тесты из раздела «Спрос».
- Человек 2 — подключить таблицу сезонности к коррекции дефицита и снять прошедший `xfail` (точный вызов ниже); далее 2.2, 2.3 и оставшиеся приемочные проверки 2.4.
- Человек 3 — подключать `PipelineResult.demand_monthly`, `sales_flagged` и `oneoffs.report()`; примеры и названия полей ниже. Продолжить интерфейс, утверждение и экспорт по своим задачам.

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
- Tests (Linux/macOS): `.venv/bin/python -m pytest -q`. Windows: `.\.venv\Scripts\python.exe -m pytest -q`. Последний полный результат: 34 passed, 1 xpassed. Синтетические тесты спроса запускаются без данных; проверки реальных выгрузок пропускаются при отсутствии `data/clean`.
- Pipeline: `from app.pipeline import run; r = run()` → `PipelineResult(order_lines, forecast, demand_monthly, sales_flagged, params, as_of)`; ~3 s on real data.
- UI: `.venv/bin/streamlit run app/ui/app.py` (sidebar toggle «Мок-данные» switches mock ↔ real pipeline).

## Open questions

- How the manager's «Кэф. Роста», «Кэф. Сез-ти» and «Запас» are computed in the SE file (not reverse-engineered yet).
- What the monthly sales report includes/excludes compared to invoices (ask partner).
- Real lead times per supplier (IEK transit headers suggest 12–40 days).

## Спрос

### Передача результатов команде от 2026-09-23

Все пять задач человека 1 реализованы в своей зоне и запушены отдельными коммитами (см. таблицу Progress). Изменены `app/engine/oneoffs.py`, `app/engine/demand.py`, `tests/test_demand.py`, `docs/methodology-demand.md` и эта память. Контрактные колонки в `app/schema.py` не менялись. `app/pipeline.py` и приемочные тесты человека 2 в этой работе не редактировались; оставшаяся интеграция описана ниже.

### 1.1 Поиск разовых заказов

- Вход: `flag_oneoffs(sales_lines, params)`, выход — `SALES_FLAGGED` с прежними колонками плюс `is_oneoff`, `oneoff_excess_qty`, `oneoff_reason` по существующему контракту.
- Анализируются положительные строки отдельно для `(supplier, sku)`. Порог: медиана + `oneoff_k × 1.4826 × MAD`, по умолчанию `oneoff_k=5`; при нулевом MAD — строго больше `10 × медиана`. Дополнительно строка должна давать строго больше 30% положительных продаж товара за месяц.
- Крупный опт сохраняется, если сопоставимый объём (строка ≥ половины объёма кандидата) встречается хотя бы в `oneoff_min_months` разных месяцах, по умолчанию в трёх. Несколько строк в одном месяце считаются одним месяцем повторения.
- Из регулярного ряда вычитается только избыток над типичным количеством. Реальная продажа, её `qty`, дата и накладная остаются в исходных данных. Возвраты не помечаются как разовые.
- Для единственной продажи SKU собственная медиана непригодна: у контрольной LOOP она равна самому выбросу 210 000. Реализирован общий fallback по поставщику и категории (первые четыре цифры кода): при ≥100 положительных строк порог `10 × P99`, типичный объём `P90`. Коды контрольных товаров не зашиты в алгоритм. Это эвристика: категории могут содержать разные объёмы отпуска.
- На реальных данных LOOP `IEK / 130200305_`, 210 000 от 09.06.2025, помечена; типичный объём 10, исключённый избыток 209 990. Все 10 проверенных строк коробок `SE / 030200192_` с количеством ≥36 000 сохранены. На исходном наборе помечены 704 строки.
- `use_oneoff_filter=False` возвращает нулевые исключения. Явный `params.as_of` включает весь указанный день и исключает будущие строки из статистики и проверки повторения. Ошибку отсечения продаж после полуночи нашли и исправили тестом в 1.3.

### 1.2 Регулярный месячный ряд и дефицит

- Сигнатура: `build_monthly(sales_flagged, stock_monthly, params, as_of, *, seasonality=None)`. Выход — прежний контракт `DEMAND_MONTHLY`; `seasonality` является необязательным именованным аргументом, поэтому старый вызов продолжает работать.
- Для товаров с накладными строится полная сетка от 2025-01 до месяца `as_of`. Весь последний день учитывается; последующие продажи исключаются. Пустой вход возвращает пустую таблицу с правильными типами и колонками.
- `qty_raw` — фактические нетто-продажи со знаком, включая возвраты. Перед коррекцией `base_regular = max(0, qty_raw - oneoff_excluded_qty)`. Отрицательный факт сохраняется для объяснения, но регулярный спрос не уходит ниже нуля.
- Норма `M` — медиана `base_regular` минимум двух полных месяцев с положительным начальным остатком; нулевые продажи в таких месяцах тоже входят в оценку. Ожидание: `M × coef_month / mean(coef_available_months) × observed_days / calendar_days`.
- `stockout=True`, только если начальный остаток ≤0 (отсутствующий принимается за 0), базовый спрос ниже ожидания, хватает доступной истории и товар уже имел продажу либо положительный остаток. До первой активности товара спрос не восстанавливается.
- Для отмеченного месяца добавляется `max(0, expected - base_regular)` в `stockout_uplift_qty`; итог `qty_regular = base_regular + stockout_uplift_qty`. **Этот прирост уже включён в регулярный ряд; в прогнозе или заказе нельзя добавлять его второй раз.**
- Неполный месяц получает ожидание пропорционально прошедшим дням и не служит полным опорным месяцем для `M`. При нехватке истории добавка равна нулю. `use_stockout_fix=False` обнуляет добавку, сохраняя признаки дефицита.
- Переданная сезонность использует контракт `SEASONALITY`: уникальные `(supplier, month_num)`, месяц 1–12, положительный конечный `coef`. Некорректная таблица отклоняется. При отсутствии коэффициента/таблицы либо `use_seasonality=False` применяется 1; скрытой загрузки файлов нет.
- Прямой вызов модуля с реальными коэффициентами на подготовленных данных дал 56 994 товарных месяца и 1 399 месяцев с положительной оценкой упущенного спроса. Это проверка модуля с явным `seasonality`, а не результат текущего вызова pipeline.

### 1.3 Проверки и среда

- В `tests/test_demand.py` 21 проходящая проверка (19 после 1.3 и две добавлены с отчётом 1.4). Синтетические тесты не зависят от локальных выгрузок; только fixture реальных данных пропускается при отсутствии parquet.
- Покрыты всплеск ×50, MAD и нулевой MAD, доля месяца, повторение в разных/одном месяце, разделение поставщиков, возвраты, отключение фильтра, дата отсечения и будущие продажи, сезонность, неполный месяц, отключение коррекции, отсутствие истории, месяцы до появления товара, недопустимые коэффициенты, пустые входы, неизменность входных данных и отчёт.
- Реальные проверки требуют непустых выборок LOOP и коробок, проверяют контракт месячного ряда, отсутствие дубликатов/отрицательного регулярного спроса и увеличение спроса при включённой коррекции.
- Локально создана `.venv` на Python 3.13, установлены зависимости из `requirements.txt`. Два архива партнёра распакованы с декодированием имён cp866; `python -m app.adapters.build` собрал 8 parquet-таблиц, включая 248 875 строк накладных. `.venv`, `data/raw`, `data/clean` этой работой в Git не добавлялись.
- Проверенные команды Windows: `.\.venv\Scripts\python.exe -m app.adapters.build`; `.\.venv\Scripts\python.exe -m pytest tests/test_demand.py -q`; `.\.venv\Scripts\python.exe -m pytest -q`. Последний полный прогон кода `660a167`: **34 passed, 1 xpassed**, около 30 секунд. Этот XPASS — устаревшая метка теста дефицита, подробности ниже.

### 1.4 Отчёт для человека 3

```python
from app.engine import oneoffs
report = oneoffs.report(result.sales_flagged)
monthly = result.demand_monthly
```

`report` содержит только помеченные строки, отсортированные по исходному `qty` по убыванию, с новым последовательным индексом. Колонки: `supplier`, `sku`, `date`, `doc_id`, `unit`, `qty`, `typical_qty`, `oneoff_excess_qty`, `oneoff_reason`. `typical_qty = qty - oneoff_excess_qty`. Пустой отчёт сохраняет колонки. Входная таблица не изменяется.

Для карточки товара фильтровать одновременно по `supplier` и `sku`; показывать `qty_raw` и `qty_regular` по `month`, отдельно `oneoff_excluded_qty`, `stockout_uplift_qty`, `stockout` и `days_in_month_observed`. Выводить единицу `unit`, дату и накладную из отчёта. Количества разных единиц измерения нельзя трактовать как общую сопоставимую сумму. Значения исключений и дефицита уже учтены в `qty_regular`.

### 1.5 Методика и ограничения

`docs/methodology-demand.md` готов для переноса в README и подготовки демо: точные пороги, формулы, контрольные случаи, переключатели, интерфейс и команды тестов. В реальных данных нет ID клиентов, поэтому единица анализа — строка накладной. Нет точных периодов stockout: нулевой остаток в начале месяца не доказывает отсутствие товара весь месяц. Добавленный спрос является оценкой, а не наблюдавшейся продажей; это следует показывать в интерфейсе.

### Что осталось человеку 2

1. В `app/pipeline.py` передать таблицу, которая уже есть в `data`:

   ```python
   demand_monthly = demand.build_monthly(
       sales_flagged, data["stock_monthly"], params, as_of,
       seasonality=data["seasonality"],
   )
   ```

   До этой правки коррекция дефицита в pipeline **работает**, но использует нейтральный коэффициент 1. Сезонность прогноза — отдельный этап, она уже подключена; это замечание относится именно к оценке спроса за дефицитные месяцы.
2. Убрать `@pytest.mark.xfail` у `test_3_stockout_fix_raises_demand` в `tests/test_acceptance.py`: тест проходит. Метку у проверки LOOP человек 2 уже снял; дополнительных действий по ней не требуется.
3. После подключения коэффициентов повторить весь pytest и обновить текущий статус. Актуализировать эту заметку и раздел подключения в `docs/methodology-demand.md`, чтобы они не продолжали говорить о нейтральном коэффициенте после интеграции.

## Расчет

- 2026-09-23: Task 2.0 skeleton pushed. Engine files exist with working stubs: `flag_oneoffs` flags nothing, `build_monthly` builds the month grid 2025-01..as_of with stockout flag but uplift = 0, `forecast` = 12-month average with seasonal_index = trend = 1, `replenish.calc` implements the full formula (horizon transit, z·σ·√LT safety, pack rounding, urgency, needs_review when stock is missing), `explain` builds a template rationale.
- `as_of` defaults to the last sale date (2026-09-22). Every engine function takes `(…, params, as_of)`.
- 2026-09-23: Task 2.1 done. Forecast history = rescaled 2024 monthly report + invoice `qty_regular` from 2025 (full months only). Seasonal index per calendar month: ratio to centred 12-month MA, shrunk SKU → product group (n/(n+24)) → company (n/(n+12)), clipped 0.4–2.5. Trend only if sustained (OLS slope sign = last-6 vs prev-6 sign, ≥8 of 12 nonzero months), damped ×0.5, capped 0.8–1.25. σ = 1.4826·MAD of residuals. Details: `docs/methodology-forecast.md`.
- Seasonal demo SKU: IEK `130300792_` «Труба гибкая Ø50» — seasonal index 0.41 (Feb), 1.05 (Jun), 2.03 (Sep–Oct horizon). Also `130300791_` Ø40.
- Safety-stock issue resolved by robust σ: pipes safety 2 764 vs forecast 11 976 (was larger than forecast). Result now: 842 SKUs with recommended_qty > 0; ~38% SKUs have trend ≠ 1.
- `avg_daily_regular` is the deseasonalised base; the rationale shows seasonality/trend as separate factors.

## Продукт

(Person 3 notes)
