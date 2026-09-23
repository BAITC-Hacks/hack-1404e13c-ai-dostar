# Задачи команды (4 часа, 3 человека)

Перед стартом прочитать: `docs/architecture.md` (что и почему), `app/schema.py` (контракт), `docs/team-memory.md` (факты о данных).

Актуализация 2026-09-23: задачи человека 1 и продукта 3.1–3.10 реализованы. Незаконченные задачи, интеграционные замечания и ограничения данных вынесены в [план завершения](completion-plan.md). Пункт 2.4 реализован тестами, но исходный критерий устойчивости итогового заказа №4 ещё не доказан; это отдельно указано в плане. Пункты 2.2–2.3 остаются частичными.

## 0. Подготовка (каждый, 5 минут)

```bash
git pull
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.adapters.build --raw datasets   # -> data/clean/*.parquet (исходники партнера лежат в datasets/)
.venv/bin/python -m pytest -q               # run after building real data
```

## 1. Кто чем владеет

Файл правит только его владелец. Нужно изменить чужой файл — пишешь владельцу.

| | Человек 1 — Спрос | Человек 2 — Расчет | Человек 3 — Продукт |
|---|---|---|---|
| Суть | Разовые заказы, дефициты → очищенный месячный ряд | Прогноз, потребность, обоснование, сборка pipeline | Интерфейс, утверждение, экспорт, демо |
| Файлы | `app/engine/oneoffs.py`<br>`app/engine/demand.py`<br>`tests/test_demand.py`<br>`docs/methodology-demand.md` | `app/schema.py`<br>`app/engine/forecast.py`<br>`app/engine/replenish.py`<br>`app/engine/explain.py`<br>`app/pipeline.py`<br>`tests/test_acceptance.py`<br>`docs/methodology-forecast.md` | `app/ui/*`<br>`app/export.py`<br>`app/copilot.py`<br>`app/mock.py`<br>`README.md`<br>`docs/demo.md` |
| Must-have из ТЗ | №3 дефициты, №4 разовые заказы | №1 все источники, №2 сезонность/рост, №5 обоснование | №5 группировка по поставщику, утверждение, экспорт |

Общие файлы:

- `app/schema.py` — владелец Человек 2. Колонки можно **добавлять**, переименовывать и удалять нельзя.
- `requirements.txt` — новая библиотека дописывается одной строкой в конец.
- `docs/team-memory.md` — у каждого своя секция внизу (`## Спрос`, `## Расчет`, `## Продукт`), в чужие не писать.
- `app/adapters/*` — готово, не трогать. Нашли баг в данных — сообщить всем, чинит один человек.

## 2. Поток данных

```
load_clean() ──> sales_lines ──[1] oneoffs.flag_oneoffs() ──> sales_flagged
                 stock_monthly ─┐
                 sales_flagged ─┴─[1] demand.build_monthly() ──> DEMAND_MONTHLY
DEMAND_MONTHLY + monthly_sales + seasonality + products ──[2] forecast.forecast() ──> FORECAST
FORECAST + stock_now + in_transit + products ──[2] replenish.calc() ──> ORDER_LINES
ORDER_LINES ──[2] explain.add_rationale() ──> ORDER_LINES (с rationale)
pipeline.run(data, params) -> PipelineResult ──[3] UI / export
```

Промежуточные таблицы (Человек 2 добавляет их в `schema.py` в задаче 2.0):

```python
SALES_FLAGGED = SALES_LINES + {"is_oneoff": bool, "oneoff_excess_qty": float, "oneoff_reason": str}

DEMAND_MONTHLY = {  # один ряд на (supplier, sku, month), месяцы из накладных с 2025-01
    "supplier", "sku", "month",          # YYYY-MM
    "qty_raw",                           # нетто продажи из накладных
    "oneoff_excluded_qty",               # сколько срезано как разовое
    "stockout",                          # bool: месяц с нулевым начальным остатком
    "stockout_uplift_qty",               # сколько добавлено как упущенный спрос (оценка)
    "qty_regular",                       # = qty_raw - oneoff_excluded_qty + stockout_uplift_qty
    "days_in_month_observed",            # для неполного текущего месяца (сентябрь 2026 = 22)
}

FORECAST = {
    "supplier", "sku",
    "avg_daily_regular", "sigma_daily",
    "seasonal_index", "trend_factor", "growth_factor",
    "horizon_days", "forecast_H",
}

@dataclass
class PipelineResult:
    order_lines: pd.DataFrame      # ORDER_LINES
    forecast: pd.DataFrame         # FORECAST
    demand_monthly: pd.DataFrame   # DEMAND_MONTHLY
    sales_flagged: pd.DataFrame    # SALES_FLAGGED — для графиков и списка разовых заказов
    params: Params
    as_of: pd.Timestamp            # дата расчета, по умолчанию последняя продажа (2026-09-22)
```

Каркас (2.0) уже в `main`: все функции существуют и возвращают таблицы по контракту, `pipeline.run()` работает на реальных данных. Каждый заменяет заглушку в своих файлах. Тесты с `xfail` в `tests/test_acceptance.py` — это must-have, которые ждут вашей реализации: когда тест начинает проходить, снимите с него `xfail`.

## 3. Задачи

### Человек 2 — Расчет (начинает первым: он разблокирует остальных)

- [x] **2.0 Каркас (к 0:15, один коммит, сразу push).** Добавить в `schema.py` `SALES_FLAGGED`, `DEMAND_MONTHLY`, `FORECAST`, `PipelineResult`. Создать все файлы движка с правильными сигнатурами и **рабочими заглушками**: `flag_oneoffs` ставит `is_oneoff=False`, `build_monthly` агрегирует накладные по месяцам (`qty_regular = qty_raw`), `forecast` берет среднее, `calc` считает `Q = forecast_H − free − transit`. `pipeline.run` проходит от начала до конца. Создать пустые `tests/test_demand.py`, `app/ui/app.py`, `app/mock.py`, чтобы никто не создавал их параллельно.
- [x] **2.1 Прогноз** `forecast.forecast(demand_monthly, monthly_sales, seasonality, products, params, as_of) -> FORECAST`
  - база — средний `qty_regular` за последние 6–12 полных месяцев, десезонированный;
  - сезонный индекс SKU по месяцам горизонта: форма из `monthly_sales` 2024–2026 (нормированная, не уровень) + накладные; при коротком или редком ряде сжимать к `seasonality` компании (`w = n/(n+k)`);
  - тренд — наклон по десезонированным последним 12 мес., ограничить (например, 0.7–1.3);
  - `growth_pct[category]` — отдельный множитель сверх тренда;
  - `sigma_daily` — по остаткам регулярного ряда;
  - переключатели `use_seasonality`, `use_trend`.
- [ ] **2.2 Пополнение** `replenish.calc(fc, demand_monthly, stock_now, in_transit, products, params, as_of) -> ORDER_LINES` (формула уже реализована в каркасе — доработать)
  - `H = lead_time[supplier] + review_period`, `in_transit_H` = только поставки с `eta ≤ as_of + H`;
  - `safety = z(service_level) · sigma_daily · √lead_time`;
  - `Q_raw = max(0, forecast_H + safety − free_qty − in_transit_H)`; `Q = 0` или `pack · ceil(Q_raw/pack)`;
  - `days_of_cover = (free + transit) / avg_daily`; urgency: `< lead_time` critical, `< H` high, иначе normal;
  - нет продаж за 12 мес. → строка не нужна; нет остатка или странные данные → `flags="needs_review"`;
  - `final_qty = recommended_qty`, `status="draft"`.
- [ ] **2.3 Обоснование** `explain.add_rationale(order_lines)` — одна строка на русском из чисел. Пример: «Регулярный спрос 12/день (исключено разовое 210 000; +18% за 2 мес. дефицита), сезонность ×1.24, на 37 дн. нужно 520 + страховой 60; есть 140, в пути 100 → 340 (кратн. 20)».
- [x] **2.4 Приемочные тесты** (1.2 подключена; расхождение критерия №4 см. план) `tests/test_acceptance.py`, на реальных данных через `pipeline.run`:
  1) увеличили `in_transit` SKU → `recommended_qty` не вырос; уменьшили `free_qty` → вырос;
  2) сезонный SKU: прогноз на пиковый месяц > на спадовый;
  3) SKU с дефицитами: с `use_stockout_fix` потребность выше, чем без;
  4) вкололи строку ×50 медианы → рекомендация изменилась < 10%;
  5) у каждой строки есть `rationale`, `supplier ∈ {IEK, SE}`; при `Q_raw=0` → 0, иначе кратно `pack_multiple`.
- [x] **2.5** `docs/methodology-forecast.md` — формулы и параметры для README (10–20 строк).

### Человек 1 — Спрос

До коммита 2.0 — изучить данные в ноутбуке или скрипте (контрольные SKU ниже), писать код в своих файлах.

- [x] **1.1 Разовые заказы** `oneoffs.flag_oneoffs(sales_lines, params) -> SALES_FLAGGED`
  - только строки `qty > 0`, по каждому `(supplier, sku)`: `median`, `MAD`;
  - кандидат: `qty > median + oneoff_k · 1.4826·MAD` (при MAD=0: `qty > 10·median`) **и** строка > 30% объема SKU за месяц;
  - исключаем, только если строки сопоставимого размера (≥ 50% этой) у SKU были **меньше чем в `oneoff_min_months` разных месяцах**: регулярный крупный опт не трогаем;
  - `oneoff_excess_qty = qty − median` (срезаем до типичной строки, а не удаляем), `oneoff_reason` — текст с цифрами;
  - `use_oneoff_filter=False` → все `is_oneoff=False`.
  - Контрольные случаи: IEK `130200305_` «Петля LOOP» 210 000 шт 09.06.2025 → **разовый**; SE `030200192_` «Установочная коробка» строки 36–90 тыс. → **не разовый**.
- [x] **1.2 Месячный ряд** `demand.build_monthly(sales_flagged, stock_monthly, params, as_of) -> DEMAND_MONTHLY` (сетка месяцев и флаг stockout уже есть — добавить uplift)
  - агрегировать накладные с 2025-01 по `as_of` (возвраты вычитаются, отрицательный месяц → 0);
  - текущий неполный месяц: заполнить `days_in_month_observed`, чтобы прогноз мог масштабировать;
  - `stockout = stock_monthly.qty_start ≤ 0` в этом месяце **и** продажи ниже нормы;
  - `stockout_uplift_qty = max(0, ожидаемый − факт)`, где ожидаемый = медиана `qty` не-дефицитных месяцев SKU × сезонный коэффициент компании месяца / средний коэффициент;
  - `use_stockout_fix=False` → uplift 0.
- [x] **1.3 Тесты** `tests/test_demand.py`: петля исключена; коробки не исключены; вколотая строка ×50 исключена; у SKU с дефицитными месяцами uplift > 0; `qty_regular` ≥ 0.
- [x] **1.4 Отчет о разовых заказах** `oneoffs.report(sales_flagged) -> DataFrame` (дата, накладная, SKU, qty, типичный объем, причина) — для вкладки в UI.
- [x] **1.5** `docs/methodology-demand.md` — алгоритм выбросов и дефицитов для README. Это обязательный пункт ТЗ, писать конкретно, с порогами.

### Человек 3 — Продукт

Итоговый интерфейс работает только через `pipeline.run` на реальных данных Excel. `app/mock.py` остался исключительно вспомогательным генератором для модульных тестов.

- [x] **3.1 Каркас Streamlit** `app/ui/app.py` (запуск: `.venv/bin/streamlit run app/ui/app.py`)
  - `@st.cache_data` на `load_clean()`, `pipeline.run` по кнопке «Рассчитать»;
  - сайдбар: lead time по поставщику, review period, service level, рост по категориям, переключатели `use_*`.
- [x] **3.2 Вкладка «Заказ»**
  - фильтр поставщик / категория / срочность; итоги по поставщику (позиций, критичных);
  - `st.data_editor`: редактируются только `final_qty` и `override_reason`, `recommended_qty` read-only;
  - строка с `final_qty ≠ recommended_qty` без причины → предупреждение;
  - кнопка «Утвердить заказ поставщика» → `status=approved`, сохранить в `data/state/approvals.json` (gitignored). **Никакой автоотправки** — запрещено ТЗ.
- [x] **3.3 Экспорт** `app/export.py`: `to_xlsx(order_lines, supplier) -> bytes` и CSV, только утвержденные строки. Колонки: Код 1С, Артикул поставщика, Наименование, Ед., Количество, Поставщик, Склад, Обоснование. Экранировать значения, начинающиеся с `= + - @`.
- [x] **3.4 Вкладка «Товар»** — выбор SKU: график по месяцам `qty_raw` / `qty_regular` / прогноз, маркеры разовых заказов и месяцев дефицита, `rationale` и разложение формулы.
- [x] **3.5 Вкладка «Проверки»** — демо must-have: для выбранного SKU таблица «с фактором / без» по каждому `use_*` и по +N в пути. Это главный экран для жюри.
- [x] **3.6 Вкладка «Сравнение с менеджером»** (SE) — `manager_baseline` против нашего расчета: ср. за 12 мес., свободный остаток, наша рекомендация, где расходимся сильнее всего.
- [x] **3.7 Вкладка «Разовые заказы»** — `oneoffs.report()`.
- [x] **3.8 README** (после 3:00): описание, запуск, структура, вставить `methodology-demand.md` и `methodology-forecast.md`, допущения из `architecture.md` §2.
- [x] **3.9** `app/copilot.py` — «Объяснить подробнее» и сводка поставщика подключены к UI, передаются агрегированные факты без накладных; fallback на шаблон при отсутствии ключа/ошибке. Сводка учитывает `final_qty`, пропущенные числовые значения не вызывают падения, неподтвержденные числа (включая 0–12) отклоняются.
- [x] **3.10** `docs/demo.md` — сценарий на 3 минуты: Петля LOOP → SKU с дефицитами → сезонный SKU → +в пути → утверждение и экспорт → сравнение с менеджером.

## 4. Таймлайн

| Время | 1 — Спрос | 2 — Расчет | 3 — Продукт |
|---|---|---|---|
| 0:00–0:15 | Изучает данные, контрольные SKU | **2.0 каркас → push** | `mock.py`, скелет UI |
| 0:15–1:10 | 1.1 разовые заказы | 2.1 прогноз, 2.2 пополнение | 3.1–3.3 |
| **1:10** | push 1.1 | **pipeline.run на реальных данных** | подключает pipeline вместо мока |
| 1:10–2:30 | 1.2, 1.3, 1.4 | 2.3, 2.4 | 3.4–3.7 |
| **2:30** | | **все тесты зеленые** | |
| 2:30–3:15 | 1.5, помогает с тестами | 2.5, правит баги | 3.8, 3.9 |
| 3:15–3:45 | Прогон демо, фиксы | Прогон демо, фиксы | 3.10, репетиция |
| 3:45 | **Заморозка кода** | | |

## 5. Git

```bash
git pull --rebase                          # перед каждой задачей
git add <свои файлы>                        # не git add -A
git commit -m "demand: one-off detection"   # префикс = зона: demand / calc / ui
git pull --rebase && .venv/bin/python -m pytest -q && git push
```

Коммит каждые 20–30 минут. Если конфликт в чужом файле — `git checkout --theirs <file>` и написать владельцу.

## 6. Шаблон промпта для агента

```
Прочитай AGENTS.md, docs/tasks.md (задача N.M), docs/architecture.md, app/schema.py.
Реализуй задачу N.M. Меняй ТОЛЬКО файлы: <список>. app/schema.py и чужие модули не трогай;
если нужна новая колонка — остановись и скажи.
Вход и выход строго по app/schema.py. Данные: from app.adapters import load_clean.
В конце запусти .venv/bin/python -m pytest -q и покажи результат.
```
