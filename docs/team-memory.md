# AI-Dostar: team memory

This file is committed with the project and read by coding agents at the start of a task. Add verified, durable facts here before each relevant commit or push. Replace outdated entries when a decision changes; do not accumulate contradictory notes.

## Project

- Repository: `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar`.
- Purpose: HackAlem AI case «Электрокомплект» — сервис рекомендованных заказов поставщикам (IEK, Systeme Electric).
- Architecture for the 4h MVP: `docs/architecture.md` (Python modular monolith + Streamlit, no DB/microservices). The long `SupplyAI_ARCHITECTURE.md` is the post-hackathon target; its domain rules are folded into `docs/architecture.md`.

## Progress (обновлять при каждом push)

- 2026-09-23: При публикации нового README интегрирован параллельный `569ab56`: добавлены шестая вкладка «Ассистент», поиск обычными словами, жизненный цикл и ссылка на методику. Баннер локальный, схема Mermaid; показатели ML приведены как результаты сохранённого эксперимента с ограничениями, а не обещание точности.

- 2026-09-23: README переработан как витрина проекта: локальный SVG-баннер, навигация, пять экранов, запуск Windows/Linux/macOS, схема Mermaid, два метода прогноза, измеренные результаты ML с ограничениями, контрольные примеры, утверждение/экспорт, тесты и troubleshooting. Перед работой подтянут `b0bc121`, новый ML раздел сохранён и раскрыт. Цифры набора сверены с Parquet, метрики — с docs/ml-evaluation.json; ссылки, якоря, блоки кода и XML баннера проверены. Обучение и полный pytest для этой документационной правки не запускались; код приложения не изменялся.

**Дополнение от 2026-09-23 — обучаемый ML:** по запросу пользователя добавлен `app/ml` и выбор метода в UI. Ранее прогноз был только статистическим, а LLM объяснял числа. Теперь обучен общий градиентный бустинг на реальных данных по август 2026: 86 094 примера, 2 523 товара. Методика и измеренные ограничения — `docs/methodology-ml.md`, отчет — `docs/ml-evaluation.json`. При интеграции получен командный `86e1d81`; его проверки данных, кратность и источник разовой продажи в обосновании сохранены для обоих методов.

Статус на 2026-09-23: по запросу пользователя исправлены все воспроизведённые замечания ревью, включая чужие зоны UI/copilot/forecast. Спрос 1.1–1.5, расчет и интерфейс интегрированы. Реальный режим работает из datasets и data/raw; восемь таблиц совпадают. Реальный AppTest проверил расчет, обе кнопки объяснения, утверждение/экспорт и семь сценариев. Подробности исправлений и ограничения — в разделе «Спрос». Задачи 2.2 и 2.3 закрыты (флаги `bad_stock`/`bad_transit`/`bad_pack`, кратность и источник разовой продажи в обосновании); полный pytest на macOS — **98 passed**. Открыто только партнерское: фактический остаток IEK, сроки поставки, расхождение отчета SE.

**Сделано (в `main`):**

| Что | Где | Коммит |
|---|---|---|
| Анализ ТЗ и реальных данных, расхождения с ТЗ и допущения | `docs/architecture.md` §2 | `defea03` |
| **Ассистент и жизненный цикл**: рекомендации, поиск по заказу обычными словами (ChatGPT → JSON-фильтр, без ключа — правила), угасающий спрос / новинки / кандидаты в замену модели с проверкой ИИ; количества не меняются | `app/assistant.py`, `app/engine/lifecycle.py`, `app/ui/tab_assistant.py`, `docs/methodology-assistant.md`, `tests/test_assistant.py` | «assistant: …» |
| **Задачи 2.2, 2.3**: явные `needs_review` для некорректных остатков/поставок/кратности, правило «нет базы спроса — нет строки»; обоснование с кратностью и крупнейшей разовой строкой (дата, накладная) | `app/engine/replenish.py`, `app/engine/explain.py`, `app/pipeline.py`, `tests/test_acceptance.py` | «calc: flag invalid inputs…» |
| MVP-архитектура на 4 часа (монолит + Streamlit); `SupplyAI_ARCHITECTURE.md` — целевая, не для хакатона | `docs/architecture.md` | `defea03` |
| Контракт данных | `app/schema.py` | `defea03`, `960393f` |
| Адаптеры IEK и SE → parquet (8 таблиц, ~8 с), smoke-тесты | `app/adapters/`, `tests/test_adapters.py` | `defea03` |
| Разделение на 3 человека, владение файлами, таймлайн, правила git, шаблон промпта | `docs/tasks.md` | `d2b98bc` |
| **Задача 2.0**: каркас движка, `pipeline.run()` работает на реальных данных (~3 с) | `app/engine/`, `app/pipeline.py` | `960393f` |
| Заготовки для Продукта: Streamlit (мок ↔ реальный расчет), мок, экспорт, copilot | `app/ui/app.py`, `app/mock.py`, `app/export.py`, `app/copilot.py` | `960393f` |
| Первые тесты приемки | `tests/test_acceptance.py`, `tests/test_demand.py` | `960393f` |
| **Задача 2.1**: прогноз с сезонностью (SKU → группа → компания), устойчивый тренд, робастная σ; методика | `app/engine/forecast.py`, `docs/methodology-forecast.md` | `dcc294b` |
| **Задача 1.1** (Человек 1): поиск разовых строк накладных | `app/engine/oneoffs.py` | `ef7cd5d` |
| **Задача 1.2**: оценка упущенного спроса по месяцам, сезонные коэффициенты через необязательный аргумент | `app/engine/demand.py` | `5365e55` |
| **Задача 1.3**: синтетические и реальные проверки спроса, исправление границы дня `as_of` | `tests/test_demand.py`, `app/engine/oneoffs.py` | `099d736` |
| **Задача 1.4**: типичный объём и единица измерения в отчёте о разовых продажах | `app/engine/oneoffs.py`, `tests/test_demand.py` | `d531b8a` |
| **Задача 1.5**: методика с формулами, порогами и ограничениями | `docs/methodology-demand.md` | `660a167` |
| **Copilot** (ChatGPT): объяснение строки и сводка по поставщику с защитой от выдуманных чисел | `app/copilot.py`, `tests/test_copilot.py`, `.env.example` | «calc: copilot…» |
| **Задача 2.4**: приемка must-have №1 по каждому источнику (в пути, поздний приход, остаток, продажи, рост категории, кратность, отчет 2024, сезонность компании, история остатков) и №4 (вколотая строка ×50) | `tests/test_acceptance.py` | «calc: copilot…» |
| Конвертер xlsx → csv (Windows-пути `C:/Hackathon/datasets`) — вспомогательный, pipeline читает xlsx через адаптеры | `scripts/excel_to_csv.py` | `d3c84ef` |
| **Продукт 3.1–3.8, 3.10**: пять вкладок Streamlit, редактирование и утверждение, экспорт CSV/XLSX, сравнение факторов и менеджера, README и сценарий демо; кнопка copilot 3.9 подключена | `app/ui/`, `app/export.py`, `README.md`, `docs/demo.md`, `tests/test_product.py` | `37580dd` |

**Проверка до добавления ML, после объединения с 48ab2fc:** `.\.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/integrated-full-a --tb=short` → **96 passed за 142.61 с**, без skip/xfail. Включён полный реальный UI-сценарий с редактированием, объяснениями, семью проверками, утверждением, CSV/XLSX и новой сессией. Платные API не вызывались, реальные утверждения не изменялись. Актуальный прогон ML — в разделе ниже.

**Состояние модулей:**

| Модуль | Что работает | Что осталось → кто |
|---|---|---|
| `engine/oneoffs.py` | **готово (1.1, 1.4)**: median/MAD, доля месяца, повторение по месяцам, fallback по категории, отчёт с типичным объёмом | — |
| `engine/demand.py` | **готово (1.2)**: сетка месяцев, вычет разовых, stockout (остаток 0 и продажи ниже ожидаемых, ≥2 месяцев с остатком), uplift с сезонностью компании | — |
| `engine/forecast.py` | **готово (2.1)**: сезонность с усадкой, тренд, рост, робастная σ | — |
| `engine/replenish.py` | расчет заказа, кратность, в пути, срочность; IEK помечен estimated_stock в flags/UI/обосновании | фактические остатки/поступления нужно получить у партнера |
| `engine/explain.py` | обоснование из чисел, кратность, источник разовой строки; отдельно именует ML без ложного разложения на статистические множители | — |
| `app/ml/` | обучение HistGradientBoostingRegressor, сохранение модели, временная проверка, месячные прогнозы, интеграция в pipeline/UI | новая временная проверка после сентября и квантили под уровень сервиса |
| `app/copilot.py` | обе функции, final_qty в сводке, защита неполных данных, явная текстовая модель, строгое отображение проверенных фактов | живой API проверяется отдельно при наличии ключа |
| `app/ui/app.py`, `app/ui/state.py` | пять вкладок, причины правок, сохранение нулевых решений, обе кнопки copilot, спиннер сценариев, актуальный экспорт | проверено на моках и реальных данных |
| `app/export.py` | XLSX/CSV утвержденных положительных строк, защита от формул, кнопки в UI | проверено тестами продукта |

**Для демо (проверено на реальных данных):**

- Разовый заказ: IEK `130200305_` «Петля металлическая LOOP», 210 000 шт одной накладной 09.06.2025 — исключена. Регулярный крупный опт SE `030200192_` «Установочная коробка» 36–90 тыс. — не исключен.
- Сезонность: IEK `130300792_` «Труба гибкая Ø50» — индекс 0.41 (февраль), 1.05 (июнь), 2.04 (горизонт сен–окт), тренд ×1.17, +3 373 м восстановлено за месяц дефицита; после смены оценки σ заказ 16 350 м.
- Итог после смены оценки σ: IEK — к заказу 678 из 1948 позиций, 401 критичная; SE — 163 из 534, 84 критичных. Изменение σ влияет на все товары; старые утверждения с другой подписью расчета не восстанавливаются.
- Сравнение с менеджером: `manager_baseline` (SE, 497 позиций) — вкладка 3.6.
- «Проверки» на трубе Ø50 после исправлений (реальный AppTest): все факторы 16 350; без разовых 16 350; без компенсации дефицита 14 500; без сезонности 9 250; без тренда 14 350; без в пути 16 350; в пути +100 → 16 250.
- Все must-have можно показать переключателями `Params(use_oneoff_filter / use_stockout_fix / use_seasonality / use_trend / use_in_transit)` — вкладка 3.5.

**Следующие шаги:**

- Человек 1 — задачи 1.1–1.5 готовы; при интеграционных вопросах — описание и тесты в разделе «Спрос». Свободен помогать с UI (вкладки «Товар», «Разовые заказы») по договоренности с Человеком 3.
- Человек 2 — учет неопределенности остатка IEK реализован; для дальнейшего улучшения нужны реальные поступления/остатки от партнера. Методика σ и приёмка актуализированы.
- Человек 3 — замечания ревью UI устранены и покрыты AppTest. Обновлённые значения для репетиции — docs/demo.md; учитывать, что ИИ выбирает проверенные факты, а тексты формируются приложением.

## Decisions

- 2026-09-23: По новому запросу ML включён в продукт вопреки первоначальному ограничению MVP. Используется scikit-learn HistGradientBoostingRegressor, а не CatBoost/LLM. Статистический метод остаётся по умолчанию; обученный ML выбирается явно, поскольку выигрыш зависит от метрики и группы.

- 2026-09-23: Team memory lives in this Markdown file and is shared through Git. No Mem0 account or plugin is required for this repository. The repo-level Codex config disables an already-installed Mem0 plugin here.
- 2026-09-23: Agents read this file at task start and update it with meaningful, verified changes before pushing.

- 2026-09-23: Real data verified: no client_id, no price, no stockout file, no lead times, no BOM; sales only warehouse «Алматы»; usable transactions from 01.2025, monthly sales/stock from 01.2024. Gaps and workarounds are listed in `docs/architecture.md` §2.
- 2026-09-23: One-off detection unit = invoice line (`doc_id`+SKU). Control cases: IEK «Петля металлическая LOOP» 210000 шт 09.06.2025 must be excluded; SE «Установочная коробка» 36–90k шт recurring must not.
- 2026-09-23: SE «Товар в пути» xlsx is the manager's current Excel calculation — use as baseline for comparison in the demo.
- Raw partner xlsx: committed in `datasets/` (team decision by commit `03b9ce7`), or unzipped locally into `data/raw/` (gitignored) with `unzip -O cp866` (Cyrillic names).
- 2026-09-23: `datasets/IEK` had every workbook under the wrong name (shifted by one; MOQ and the real «Сезонность ИЭК» missing), most likely from unzipping on Windows without cp866. Fixed by replacing the files with the originals from the archive and regenerating `datasets/IEK_CSV`. Adapters pick files by name keywords, so file names must match content.

- 2026-09-23: Invoice lines are the primary demand source; the monthly sales report is used only for the 2024 seasonality shape. The two disagree (SE report ≈ 50% of invoices, gap is wholesale box orders) — see `docs/architecture.md` §2.
- 2026-09-23: `products.category` = first 4 digits of the 1C code for both suppliers; SE «Категория 2026» is kept as `manager_baseline.category_abc`. IEK current stock is estimated (Sep start stock − Sep sales), SE current stock comes from the manager file.
- 2026-09-23: Work split and file ownership are in `docs/tasks.md`: Person 1 «Спрос» (oneoffs, demand series), Person 2 «Расчет» (schema owner, forecast, replenish, explain, pipeline, acceptance tests), Person 3 «Продукт» (Streamlit UI, approval, export, README, demo). Split is by file ownership inside the monolith, not by microservices. Person 2 pushes the skeleton (task 2.0) first.
- 2026-09-23: Git: work directly on `main`, `git add` only own files, `git pull --rebase` + pytest before push, commit prefixes `demand:` / `calc:` / `ui:`. `app/schema.py` columns may be added, never renamed or removed.
- 2026-09-23: Approvals are stored in `data/state/approvals.json` (gitignored). No automatic sending to suppliers.

## Working commands

- 2026-09-23: `python scripts/excel_to_csv.py` converts every worksheet from `C:/Hackathon/datasets/IEK` and `C:/Hackathon/datasets/Systeme electric` into UTF-8 CSV in sibling `_CSV` folders. Verified output: 5 CSV from 5 IEK books and 8 CSV from 6 SE books; requires `openpyxl` from `requirements.txt`. Source workbooks are left unchanged.
- Setup: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` (pandas 3.x works).
- Data: `.venv/bin/python -m app.adapters.build --raw datasets` → `data/clean/*.parquet` (~8 s). Alternative: unzip partner archives into `data/raw/` (`unzip -O cp866 IEK.zip -d data/raw`) and build without `--raw`.
- In code: `from app.adapters import load_clean; data = load_clean()` → dict of contract tables from `app/schema.py`.
- Tests (Linux/macOS): `.venv/bin/python -m pytest -q`. Windows: `.\.venv\Scripts\python.exe -m pytest -q`. Актуальный результат и обход ошибки временной папки — в Progress выше. Синтетические тесты спроса запускаются без данных; проверки реальных выгрузок пропускаются при отсутствии `data/clean`.
- Pipeline: `from app.pipeline import run; r = run()` → `PipelineResult(order_lines, forecast, demand_monthly, sales_flagged, params, as_of)`; ~3 s on real data.
- UI: `.venv/bin/streamlit run app/ui/app.py`; рабочий интерфейс использует только реальные таблицы.
- UI on Windows: `.venv\Scripts\python.exe -m streamlit run app/ui/app.py --server.port=8501`. Сначала собрать data/clean, затем нажать «Рассчитать». После обновления Python-модулей перезапустить сервер.

## Open questions

- How the manager's «Кэф. Роста», «Кэф. Сез-ти» and «Запас» are computed in the SE file (not reverse-engineered yet).
- What the monthly sales report includes/excludes compared to invoices (ask partner).
- 2026-09-23: Исходники datasets оставлены в Git решением команды (03b9ce7); имена IEK исправлены в 363c7ab. Дубликаты data/raw, подготовленные parquet, ключи и утверждения остаются локальными.
- Real lead times per supplier (IEK transit headers suggest 12–40 days).

## Спрос

### Исправления по итогам ревью — 2026-09-23

Пользователь явно поручил устранить все найденные проблемы, включая файлы других участников. База исправлений — `363c7ab`; исправление исходных IEK-книг от человека 2 сохранено и повторно проверено.

- **Кнопка объяснения:** `product_tab` передает полную строку с supplier/sku (после интеграции 48ab2fc — через query/iloc). Реальный AppTest проходит объяснение; неполные факты (NaN, inf, pd.NA, отсутствующее поле) приводят к шаблону без обращения к API.
- **Обязательная причина:** единая `clean_reason` применяется до валидации и сохранения. Очистка ячейки, пробелы и строковые `<NA>`/`nan`/`None` не разрешают изменить количество без причины. Старое некорректное утверждение из JSON не восстанавливается.
- **Нулевые решения:** утверждение сохраняет все строки поставщика, включая исключения с количеством 0 и их причины. Можно утвердить полностью нулевое решение; экспорт по-прежнему содержит только положительные строки. Пересчет с той же подписью сохраняет исключения, редактирование отзывает утверждение.
- **Экспорт:** CSV/XLSX теперь формируются отложенным callable при скачивании и тогда перечитывают состояние. AppTest проверяет: другая сессия отзывает SKU после отрисовки страницы, вызов уже показанного скачивания исключает SKU. Проверено на Streamlit 1.64.0; requirements требует 1.64+. Реальные утверждения в тестах не затрагивались.
- **ИИ:** удалена ненадежная проверка свободного текста по общему набору чисел (она разрешала «Order 7 units» вместо 120). Модель возвращает только массив fact_ids по строгой JSON-схеме, приложение проверяет его и отображает фиксированные предложения из каталога. Количество заказа, итог менеджера и предупреждение об оценочном остатке обязательны. Неизвестные/дублирующиеся ID, произвольный текст, добавочные поля, пустой ответ, ошибка API → шаблон. Подмена чисел словами также не проходит: свободный текст вообще не рендерится.
- **Модель:** по умолчанию gpt-4o-mini, без лексикографического поиска по models.list; настройка OPENAI_MODEL сохранена. Явные image/audio/embedding и другие несовместимые семейства отклоняются. Неподдерживаемая схема/недоступная модель на сервере → fallback. Совместимость проверена по официальной документации Structured Outputs; реальные платные вызовы не выполнялись.
- **Сводка:** supplier_facts считает final_qty, включая нулевые исключения; кнопка добавлена в UI. Объяснения строки и поставщика перестают показываться после изменения исходных для них данных.
- **Приёмка разового заказа:** проверка возвращена к `recommended_qty`, абсолютное изменение менее 10% исходного заказа. Причина прежних 530 → 783 (+47.74%) на IEK 200400166_ — скачок MAD страхового запаса на коротком окне после сохранения обычной части продажи (200 м). Оценка σ заменена на IQR/1.349 остатков, при IQR=0 используется 0.5·std. Теперь 621 → 650 (+4.67%); фильтр по-прежнему сохраняет типичную часть, алгоритм 1.1 не изменён. Методика и тест обновлены; изменение σ применяется ко всем SKU. Относительный предел не является гарантией для почти нулевого исходного заказа.
- **Остаток IEK:** расчёт не подменяет неизвестные поступления выдуманными значениями. Добавлены `needs_review:estimated_stock`, предупреждение в UI и в rationale/каталоге объяснений. Это ограничение входных данных, а не исправляемое кодом отсутствие фактов.
- **Презентация:** у семи сценариев есть спиннер, дата фиксирована к расчету; изменение добавочного прихода скрывает старый результат. График поясняет распределение потребности по дням горизонта. После интеграции 48ab2fc сравнение использует действительное арифметическое среднее фактического/регулярного спроса за 12 полных месяцев, а не десезонированную базу ×30.4. Актуализированы методики, README, демо и чекбоксы реализованных задач.
- **Данные:** `build(Path('datasets'))` повторно дал восемь таблиц, полностью равных локальному load_clean по assert_frame_equal. Исправленный реальный AppTest получил 2482 строки, прошёл обе кнопки объяснения с подменой API, утверждение и экспорт в изолированную временную папку, затем все семь сценариев на трубе Ø50.

### Передача результатов команде от 2026-09-23

Все пять задач человека 1 реализованы в своей зоне и запушены отдельными коммитами (см. таблицу Progress). Изменены `app/engine/oneoffs.py`, `app/engine/demand.py`, `tests/test_demand.py`, `docs/methodology-demand.md` и эта память. Контрактные колонки в `app/schema.py` не менялись. Изменения pipeline и приемочных тестов выполнил человек 2 в `dbd72f1`; подключение сезонности теперь проверено.

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

### Подключение человеком 2 завершено в dbd72f1

1. В `app/pipeline.py` теперь передаётся имеющаяся таблица:

   ```python
   demand_monthly = demand.build_monthly(
       sales_flagged, data["stock_monthly"], params, as_of,
       seasonality=data["seasonality"],
   )
   ```

   Коррекция дефицита и прогноз теперь оба получают сезонность компании. Старый вызов без именованного аргумента остаётся допустимым и использует коэффициент 1.
2. Метки `xfail` у `test_3_stockout_fix_raises_demand` и проверки LOOP сняты, оба теста проходят.
3. Интеграция сезонности и тесты дефицита завершены. Раздел подключения docs/methodology-demand.md и задача 2.4 актуализированы; результаты исправления copilot/UI описаны выше.

## Расчет

- `as_of` по умолчанию — последняя продажа (2026-09-22); pipeline передает сезонность компании в demand и forecast.
- История: приведенный к накладным отчет 2024 + регулярный спрос с 2025, только полные месяцы. Сезонность SKU → группа → компания; тренд затухает ×0.5 и ограничен 0.8–1.25. Подробности — docs/methodology-forecast.md.
- `avg_daily_regular` — десезонированная база. Робастная σ с 2026-09-23: IQR/1.349 остатков, fallback 0.5·std при IQR=0. Приемка разовой строки проверяет итоговый заказ, не потребность.
- Остаток IEK оценочный: начало месяца минус продажи, поступления неизвестны. Предупреждение и флаг обязательны; для повышения точности нужен источник фактических остатков.
- В pandas использовать `df["flags"]`: `df.flags` — встроенный атрибут, не колонка.
- Правило повторяемости 1.1 считает три различных месяца всего, включая месяц кандидата. Это закреплено тестами; изменять правило без пересмотра методики не нужно.

- 2026-09-23: Reviewed teammate fixes `48ab2fc` + `27350f9`: copilot now returns app-authored fact statements chosen by the model via strict JSON schema (default model `gpt-4o-mini`, override `OPENAI_MODEL`); σ uses IQR/1.349; IEK lines carry `needs_review:estimated_stock` and approval requires a stock-check checkbox. Real-data AppTest: explain, supplier summary, checks, blocked approval — no exceptions. Pipe `130300792_` order is now 16 350 (was 16 400 with MAD σ).
- 2026-09-23: Tasks 2.2/2.3 done. `explain.add_rationale(order_lines, products, sales_flagged)` — both optional; pipeline passes them.

- 2026-09-23: Assistant + lifecycle added (user request). `app/engine/lifecycle.py` (LIFECYCLE table in schema, `PipelineResult.lifecycle`): declining 128 (38 still ordered), new_item 144, replacement candidates 33 (29 likely variants, 4 unverified, 0 confirmed). Advisory only: `lifecycle:*` flags + rationale sentence, quantities unchanged; unverified pairs never reach order lines. `app/assistant.py`: NL search → strict JSON filter (LLM) or keyword rules; pair review with fixed verdict/reason enums; deterministic recommendations. UI: `app/ui/tab_assistant.py`, tab «Ассистент» (6th tab, `tests/test_ui_real.py` updated to 6 tabs). Method: `docs/methodology-assistant.md`. Tests: `tests/test_assistant.py`; full suite 108 passed, 4 skipped (ML artifacts). New dependency from ML commit: scikit-learn — run `pip install -r requirements.txt`.

- 2026-09-23: OpenAI key verified live (stored only in local gitignored `.env`; never commit or paste it into docs). `gpt-4o-mini` works for explain, supplier summary, search and pair review. New `assistant.ask(question, order_lines, lifecycle)` + «Спросить ассистента» box: LLM plan (intent + filter, strict JSON) → app computes facts → LLM answers from facts only → every number checked (else template + table). LLM pair verdict «replacement» is overruled when name parameters differ (both 4o-mini and 4.1-mini produced false replacements). `tests/conftest.py` sets `COPILOT_ENABLED=0` for all tests so a local key never triggers paid calls; LLM-path tests patch the client. Suite: 112 passed, 4 skipped.

## Продукт

- Интегрирован параллельный коммит человека 3 `48ab2fc`: рабочий UI использует только реальные таблицы, учитывает fingerprint parquet, предупреждает о смене параметров. Карточка доступна для всего каталога, график имеет маркеры событий, сравнение показывает фактическое и регулярное среднее за 12 полных месяцев. CSV/XLSX включают причину менеджера. Сохранены блокировка JSON в одном процессе и время утверждения. Оценочные остатки подтверждаются общей отметкой сверки; остальные проблемы данных требуют причины по строке.
- Подпись расчета включает as_of и все неизменяемые поля строки. При изменении расчета требуется новое утверждение; при том же расчете восстанавливаются и положительные, и нулевые решения.
- Объяснения строки и заказа используют проверенные факты. Сводка описывает итоговые количества менеджера. ИИ не утверждает и не отправляет заказ.
- tests/test_ui.py проверяет граничные случаи на синтетической фикстуре без режима моков в продукте. tests/test_ui_real.py выполняет полный путь на реальных данных через настоящий pipeline. Оба изолируют утверждения и исключают платные API-вызовы. Браузерный `scripts/ui_browser_smoke.py --ml` повторно пройден после интеграции `86e1d81`, пять вкладок и карточка LOOP без ошибок JavaScript. Сценарий — docs/demo.md.

## ML — 2026-09-23

- Финальный объединенный прогон после `86e1d81`: `.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest_cache/ml-team-integrated --tb=short` → **104 passed, 189.21 с, без skip/xfail**. До получения командного обновления — 102 passed. Browser smoke `--ml` после объединения также пройден. Исходные Excel и реальные утверждения не изменялись, платные LLM-запросы не выполнялись.

- Обучение: `.venv/Scripts/python.exe -m app.ml.train` после установки requirements и сборки Excel. Локальные артефакты `data/models/demand.joblib` (~78 KB) и `demand.json` исключены из Git; в Git передаются код, тесты и отчет `docs/ml-evaluation.json`. На другой машине нужно выполнить обучение, отсутствие модели явно показывается в UI.
- Общая модель HistGradientBoostingRegressor, 150 деревьев/итераций, до 15 листьев, learning rate 0.05, min_samples_leaf 30, L2 10, seed 42. Сравнены Poisson и absolute_error на ранних временных срезах; выбран absolute_error. Это прогноз типичного/медианного объема, не доказанная оценка математического ожидания.
- Лаги, скользящие средние, регулярность/разброс, календарь, поставщик, категория, единица и статистический прогноз. Примеры нормируются на предыдущий средний объем товара. Модель одна для SKU обоих поставщиков; отдельные модели на коротких рядах не строятся.
- Очистка заново для каждого исторического cutoff, обучение не видит будущие накладные/остатки/месячный отчет. Недатированные коэффициенты компании исключены из ML и эталонной временной проверки. Цель — очищенные наблюдавшиеся продажи в месяцах с положительным начальным остатком; stockout uplift не является известной целью.
- Обучение по август 2026: 86 094 примера и 2 523 SKU. На 20 507 проверочных примерах normalized MAE 0.9389 → 0.7849 (−16.41%); август отдельно 0.9783 → 0.8203 (−16.15%). Валидационные горизонты пересекаются; август был виден в первоначальном пробном Poisson-прогоне, поэтому не заявлять совершенно нетронутый внешний тест. Для IEK/шт WAPE ухудшился 33.72% → 35.93%; общий выигрыш не означает выигрыш каждого SKU. Эти ограничения есть в UI и методике.
- `Params.forecast_method="ml"` подключает модель через `pipeline.run`, заменяет forecast_H. `PipelineResult.forecast_details` содержит метод, версию, метрики и месячную кривую; прежние контрактные колонки не переименованы. Рост применяется один раз после прогноза, остатки/поставки/кратность — прежним движком. Месяцы дальше 3-го явно используют статистический fallback. Штатный метод по умолчанию остается statistical.
- Сохранены новые проверки и обоснования человека 2. `explain.add_rationale(..., forecast_description=...)` необязателен и в ML-режиме убирает ложное объяснение через произведение статистических коэффициентов, сохраняя кратность/разовые строки/оценочный остаток. Model ID включен в обоснование и подпись утверждения. Историческое применение артефакта раньше обучения и несовпадение данных/версии sklearn отклоняются.
- `tests/test_ml.py`: защита от будущих значений, реальный fitted estimator и отчет, отсутствие артефакта, конечный положительный прогноз, сумма месячных прогнозов, влияние роста/поставки, кратность, исторический cutoff, настоящий ML в AppTest. UI запуск проверен также в Microsoft Edge через `scripts/ui_browser_smoke.py --ml`, сервер отвечает на `http://localhost:8501`.
- Не заявлять доказанное снижение дефицита или стоимости запасов: нужен новый временной тест, квантили под сервис и реальные поступления/дневная доступность. Исторический страховой запас остается общим для обоих методов и не является доверительным интервалом ML.
