# AI-Dostar: team memory

This file is committed with the project and read by coding agents at the start of a task. Add verified, durable facts here before each relevant commit or push. Replace outdated entries when a decision changes; do not accumulate contradictory notes.

## Project

- Repository: `https://github.com/BAITC-Hacks/hack-1404e13c-ai-dostar`.
- Purpose: HackAlem AI case «Электрокомплект» — сервис рекомендованных заказов поставщикам (IEK, Systeme Electric).
- Architecture for the 4h MVP: `docs/architecture.md` (Python modular monolith + Streamlit, no DB/microservices). The long `SupplyAI_ARCHITECTURE.md` is the post-hackathon target; its domain rules are folded into `docs/architecture.md`.

## Progress (обновлять при каждом push)

**Актуализация 2026-09-23, завершение человека 3:** рабочий UI использует только реальные Excel, исправления ниже в разделе «Продукт». После сборки `python -m app.adapters.build --raw datasets` полный прогон дал **62 passed, без skip/xfail** (84.60 с). Проверены настоящие данные → pipeline → пять вкладок → редактирование → утверждение → CSV/XLSX → новая сессия; отдельный браузерный прогон Microsoft Edge прошёл без ошибок JavaScript. Задачи 3.1–3.10 закрыты. Оставшиеся задачи человека 2, расхождение критерия приемки №4 и вопросы партнеру отражены в `docs/completion-plan.md`; зеленые тесты не означают закрытие этих пунктов. Ниже сохранена история предыдущих проверок.

Статус на 2026-09-23 после `37580dd`: интегрированы спрос 1.1–1.5, прогноз, copilot и интерфейс заказа с утверждением/экспортом. Сезонность передана в `build_monthly`, устаревший `xfail` снят. **Реальный режим работает и из `datasets/`**: имена книг в `datasets/IEK` исправлены, `python -m app.adapters.build --raw datasets` дает те же 8 таблиц, что и архивы партнера. 52 теста проходят; AppTest нашел ошибки интеграции, не покрытые тестами — полную готовность приемки пока не заявлять: замечания и воспроизведения — в разделе «Спрос», анализ обновлений ниже. Владельцы файлов — `docs/tasks.md`.

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

**Тесты сейчас:** на `37580dd` полный запуск дал 49 passed и 3 ошибки доступа к системной временной папке Windows; повторный запуск `tests/test_product.py` с отдельным `--basetemp` дал 3 passed. Итого все 52 теста проверены, без пропусков и xfail. Есть расхождение метрики must-have №4 и ошибки UI, описанные ниже; зеленые тесты их не исключают.

**Состояние модулей:**

| Модуль | Что работает | Что осталось → кто |
|---|---|---|
| `engine/oneoffs.py` | **готово (1.1, 1.4)**: median/MAD, доля месяца, повторение по месяцам, fallback по категории, отчёт с типичным объёмом | — |
| `engine/demand.py` | **готово (1.2)**: сетка месяцев, вычет разовых, stockout (остаток 0 и продажи ниже ожидаемых, ≥2 месяцев с остатком), uplift с сезонностью компании | — |
| `engine/forecast.py` | **готово (2.1)**: сезонность с усадкой, тренд, рост, робастная σ | — |
| `engine/replenish.py` | вся формула: в пути в горизонте, z·σ·√LT, кратность, срочность, `needs_review` | мелкие доработки → Человек 2, задача 2.2 |
| `engine/explain.py` | шаблонное обоснование из чисел | добавить причину разового заказа → Человек 2, задача 2.3 |
| `app/copilot.py` | `explain_line`, `supplier_summary`, fallback на шаблон | защита чисел, выбор модели, `final_qty` в сводке, NaN → Человек 2; исправить вызов из UI → Человек 3 |
| `app/ui/app.py`, `app/ui/state.py` | пять вкладок, параметры, редактирование, утверждение и восстановление по подписи расчета; проверено на реальных данных | исправить объяснение (KeyError `supplier`), пустую причину, сохранение исключенных строк, спиннер на «Сравнить факторы» (~20 с), кнопка `supplier_summary` → Человек 3 |
| `app/export.py` | XLSX/CSV утвержденных положительных строк, защита от формул, кнопки в UI | проверено тестами продукта |

**Для демо (проверено на реальных данных):**

- Разовый заказ: IEK `130200305_` «Петля металлическая LOOP», 210 000 шт одной накладной 09.06.2025 — исключена. Регулярный крупный опт SE `030200192_` «Установочная коробка» 36–90 тыс. — не исключен.
- Сезонность: IEK `130300792_` «Труба гибкая Ø50» — индекс 0.41 (февраль), 1.05 (июнь), 2.04 (горизонт сен–окт), тренд ×1.17, +3 373 м восстановлено за месяц дефицита → заказ 16 400 м.
- Итог по поставщикам: IEK — к заказу 668 из 1948 позиций; SE — 169 из 534. У IEK много «критичных» из-за оценки остатка (см. Known issue в «Расчет»).
- Сравнение с менеджером: `manager_baseline` (SE, 497 позиций) — вкладка 3.6.
- «Проверки» на трубе Ø50 (реальные данные): все факторы 16 400; без разовых 16 450; без компенсации дефицита 14 750; без сезонности 9 550; без тренда 14 400; в пути +100 → 16 300.
- Все must-have можно показать переключателями `Params(use_oneoff_filter / use_stockout_fix / use_seasonality / use_trend / use_in_transit)` — вкладка 3.5.

**Следующие шаги:**

- Человек 1 — задачи 1.1–1.5 готовы; при интеграционных вопросах — описание и тесты в разделе «Спрос». Свободен помогать с UI (вкладки «Товар», «Разовые заказы») по договоренности с Человеком 3.
- Человек 2 — решить Known issue с остатком IEK (2.2), 2.3 обоснование (причина разового заказа), помочь UI с вкладкой 3.5 «Проверки» по договоренности.
- Человек 3 — интерфейс и экспорт уже реализованы в `37580dd`; устранить замечания AppTest ниже. Кнопка `explain_line` подключена, но падает из-за отсутствующего поля `supplier`; `supplier_summary` пока не подключена. Для реального демо собрать данные из `datasets/` (имена IEK исправлены) или из `data/raw`.

## Decisions

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
- UI: `.venv/bin/streamlit run app/ui/app.py` (sidebar toggle «Мок-данные» switches mock ↔ real pipeline).
- UI on Windows: `.venv\Scripts\python.exe -m streamlit run app/ui/app.py --server.port=8501`; 2026-09-23 сервер отвечал HTTP 200 на `http://localhost:8501`. Для просмотра без `data/clean` включить «Мок-данные» и нажать «Рассчитать».

## Open questions

- How the manager's «Кэф. Роста», «Кэф. Сез-ти» and «Запас» are computed in the SE file (not reverse-engineered yet).
- What the monthly sales report includes/excludes compared to invoices (ask partner).
- 2026-09-23: Commit `03b9ce7` (ValiCoder) added the raw partner xlsx and CSV copies under `datasets/` (~15 MB). This contradicts the decision to keep partner data out of Git (`data/raw/` is gitignored). The repo is private. Team to decide: keep or `git rm -r --cached datasets/` + add to `.gitignore` (history still keeps the files).
- Real lead times per supplier (IEK transit headers suggest 12–40 days).

## Спрос

### Анализ интеграции UI 37580dd от 2026-09-23

- Во время анализа `dbd72f1` человек 3 добавил `37580dd`; обновление подтянуто через rebase и включено в проверку. Общий diff от `7fbd121`: 14 файлов, 1 094 добавления / 58 удалений. Код приложения в ходе ревью не исправлялся; обновлена только память команды.
- Добавлены пять вкладок Streamlit, параметры расчета, правки количества/причины, локальные утверждения с подписью исходной строки, раздельное состояние моков, XLSX/CSV, сравнение факторов и с менеджером, README и трехминутный сценарий. `tests/test_product.py` проверяет восстановление/отзыв утверждений, обязательную причину и экспорт с экранированием формул.
- На этом компьютере есть корректные `data/raw` из партнерских архивов и построенные `data/clean`. AppTest реального интерфейса выполняет расчет без исключений, получает 2 482 строки; кнопка сравнения факторов успешно возвращает все семь сценариев. Это не блокируется проблемой `datasets` у другого участника. Повторный `build(Path('datasets'))` подтвердил `KeyError: 'Документ'`; подсказка UI `--raw datasets` ведет к известному нерабочему источнику.
- **P1, кнопка объяснения падает:** `product_tab` получает строку через `set_index(['supplier', 'sku'])` с `drop=True`, затем передает ее в `explain_line`, где `line_facts` требует `row['supplier']`. Нажатие «Объяснить подробнее» на реальном расчете воспроизводимо дает `KeyError: 'supplier'`, даже при `COPILOT_ENABLED=0`; fallback не достигается. Сохранить поля при индексации (`drop=False`) или передавать полную строку.
- **P1, обход обязательной причины:** UI делает `str(row['override_reason'])` до валидации. AppTest с изменением 120 → 121 и очисткой причины получает строку `'<NA>'`, `validate_line` возвращает `None`, кнопка утверждения активна; заказ сохраняется как approved и появляются оба экспорта. Причину нужно нормализовать как отсутствующее значение до преобразования в текст; добавить интеграционную проверку очистки ячейки.
- **P2, нулевые правки теряются:** `approve_supplier` сохраняет только `final_qty > 0`. Воспроизведение: рекомендация 10, менеджер ставит 0 с причиной, утверждает остальные строки; после `apply_saved` исходного расчета исключенная строка снова имеет 10, пустую причину и draft. Она не экспортируется автоматически, но следующий общий approve может вернуть ее в заказ. Нужна сохраненная запись об исключении/нулевой правке.
- Тестовый прогон `37580dd`: 49 passed / 3 ошибки `PermissionError` в `Temp/pytest-of-bekes`, затем `.\.venv\Scripts\python.exe -m pytest tests/test_product.py -q --basetemp=.pytest_cache/review-product-20260923-a --tb=short` → 3 passed. Все 52 теста фактически проверены. AppTest использовал изолированные файлы в `.pytest_cache`, реальные утверждения не менялись, внешние LLM-запросы не выполнялись.
- Дополнительные замечания по чтению кода: график делит общий `forecast_H` по числу будущих дней, не показывает отдельный сезонный прогноз каждого месяца; сравнение `ours_month_12` выводит десезонированную дневную базу ×30.4, а не фактический средний объем за 12 месяцев. Подписи/методику этих сравнений стоит уточнить. `docs/tasks.md` все еще содержит незакрытые чекбоксы уже реализованных задач 1.x/3.x.

### Анализ обновления dbd72f1 от 2026-09-23

- Проверен весь diff `7fbd121..dbd72f1` (8 файлов): copilot, его тесты/конфигурация, приемочные тесты, pipeline и документация. Полный локальный прогон: **49 passed за 90.05 с**, без xfail. Зависимость `openai` установлена в `.venv`; версия 3.19.0 поддерживает используемые параметры вызова. Реальные платные API-запросы в этом анализе не выполнялись; поведение copilot проверялось подменой клиента/ответа.
- Интеграция 1.2 завершена человеком 2: pipeline передаёт `seasonality=data["seasonality"]`, метка xfail с теста дефицита снята. На реальных данных: 2 482 строки результата; IEK — 1 948 проанализированных / 668 к заказу / 401 критичная; SE — 534 / 169 / 84; 1 399 товарных месяцев с оценкой дефицита.
- **Расхождение приемки:** новый `test_4_injected_one_off_does_not_inflate_order` ограничивает рост `forecast_H + safety_stock`, хотя `docs/tasks.md` требует изменения рекомендации менее 10%. Воспроизведено на выбранном самим тестом IEK `200400166_`: строка ×50 помечается как разовая; потребность 4 333.31 → 4 586.78 (+5.85%), заказ **530 → 783 (+47.74%)**. Тест проходит, но критерий по итоговому заказу не подтверждает. Команде нужно явно согласовать метрику или доработать поведение/проверку, а не считать этот пункт полностью доказанным.
- **Copilot, проверка чисел:** `unsupported_numbers` безусловно разрешает целые 0–12 и сверяет остальные с общим набором чисел без привязки к полям. Подменённый ответ `Order 7 units.` для строки с `recommended_qty=120` принят как `llm:test-mini`, без fallback. Это воспроизводимый пробел в защите текста; сам детерминированный заказ не меняется.
- **Copilot, выбор модели:** `model_name()` сортирует имена лексикографически и не исключает модели изображений. На имитированном списке `gpt-4o-mini`, `gpt-5-mini`, `gpt-image-1-mini` выбирается последняя, не подходящая для текстового ответа. До исправления задавать явно совместимую текстовую модель через `OPENAI_MODEL`; реальная доступность моделей на командном ключе не проверялась.
- **Copilot, сводка перед утверждением:** `supplier_facts` использует только `recommended_qty`, игнорируя `final_qty`. На моках после обнуления менеджером всех итоговых количеств сводка по выбранному поставщику продолжает показывать 6 позиций к заказу вместо 0. Для описания утверждаемого заказа нужны итоговые количества или явное разделение рекомендации и правок.
- **Copilot, неполные данные:** `line_facts()` выполняется до защищённого вызова. При `free_qty=NaN` `explain_line()` выбрасывает `ValueError` даже при отключённом LLM, вместо возврата шаблона. Это проверка искусственного неполного входа, не обнаруженный сбой текущего нормального pipeline.
- Документация обновлена не полностью: `docs/methodology-demand.md` ещё описывает отсутствие сезонности в pipeline, `docs/tasks.md` у выполненной 2.4 пишет, что тест ждёт 1.2. Информация об интеграции в этом разделе исправлена. UI, отсутствовавший в `dbd72f1`, добавлен последующим `37580dd`; его отдельный анализ приведен выше.
- Замечание человека 2 о включении месяца кандидата в `oneoff_min_months`: это текущее правило задачи 1.1 и тестов (три различных месяца всего, включая текущий). Исключать текущий месяц означало бы изменить правило повторяемости; автоматического изменения в ходе анализа не делалось.

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
3. После интеграции полный pytest подтверждён: 49 passed. Осталось актуализировать раздел подключения в `docs/methodology-demand.md` и формулировку задачи 2.4; замечания к новым тестам и copilot перечислены в анализе выше.

## Расчет

- 2026-09-23: Task 2.0 skeleton pushed. Engine files exist with working stubs: `flag_oneoffs` flags nothing, `build_monthly` builds the month grid 2025-01..as_of with stockout flag but uplift = 0, `forecast` = 12-month average with seasonal_index = trend = 1, `replenish.calc` implements the full formula (horizon transit, z·σ·√LT safety, pack rounding, urgency, needs_review when stock is missing), `explain` builds a template rationale.
- `as_of` defaults to the last sale date (2026-09-22). Every engine function takes `(…, params, as_of)`.
- 2026-09-23: Task 2.1 done. Forecast history = rescaled 2024 monthly report + invoice `qty_regular` from 2025 (full months only). Seasonal index per calendar month: ratio to centred 12-month MA, shrunk SKU → product group (n/(n+24)) → company (n/(n+12)), clipped 0.4–2.5. Trend only if sustained (OLS slope sign = last-6 vs prev-6 sign, ≥8 of 12 nonzero months), damped ×0.5, capped 0.8–1.25. σ = 1.4826·MAD of residuals. Details: `docs/methodology-forecast.md`.
- Seasonal demo SKU: IEK `130300792_` «Труба гибкая Ø50» — seasonal index 0.41 (Feb), 1.05 (Jun), 2.03 (Sep–Oct horizon). Also `130300791_` Ø40.
- Safety-stock issue resolved by robust σ: pipes safety 2 764 vs forecast 11 976 (was larger than forecast). Result now: 842 SKUs with recommended_qty > 0; ~38% SKUs have trend ≠ 1.
- `avg_daily_regular` is the deseasonalised base; the rationale shows seasonality/trend as separate factors.
- 2026-09-23: Task 2.4 done. Pitfall: `df.flags` is a built-in pandas attribute — always use `df["flags"]` for the ORDER_LINES column.
- One-off acceptance compares regular need (`forecast_H + safety_stock`), not `recommended_qty`: the order is need minus stock, so small need changes look large in % of the order. Injected 50× line on IEK `200400166_`: need +6% with filter, +46% without.
- 2026-09-23: `pipeline.run` now passes `seasonality=` to `demand.build_monthly`, so stockout uplift is seasonal. Stock-history acceptance zeroes stock only in weak months (demand.py needs ≥2 stocked months as evidence).
- 2026-09-23: AI resources: OpenAI API ($50) → `app/copilot.py` (row explanation + supplier summary, chat.completions, store=False, timeout 20 s, cached). Model gets only the rounded fact pack; any number in the answer that is not in the facts (except small counts ≤12), an API error or a missing key → template text. Key in `.env` (`OPENAI_API_KEY`, optional `OPENAI_MODEL`), see `.env.example`. NVIDIA Brev ($50) = GPU VMs, not an LLM API: use only to host the demo if a public URL is needed; not needed for the calculation.
- **Known issue for 2.2 (important for demo):** IEK current stock is estimated as Sep-1 stock − Sep sales (receipts unknown), so many IEK SKUs show free_qty 0 → 401 of 668 IEK order lines are «critical». Options: mark IEK stock as estimate in the UI/rationale, or use max(estimate, Sep-1 stock × share of month left). Decide before the demo.
- Note for Person 1: `oneoffs.flag_oneoffs` counts the candidate's own month among «comparable months», so effectively only 2 other months with ≥50% volume make a line regular. Example: IEK `010300004_` (median 2, lines 60/73/48) — a new 100-unit line is kept as regular. Decide whether that is intended.

## Продукт

### Завершение человека 3 — 2026-09-23

- Перед работой получены три командных коммита до `363c7ab`, включая исправленные Excel IEK. Сборка `--raw datasets` успешна: 248875 строк накладных, 99561 месячных продаж, 117282 месячных остатков, 3577 текущих остатков, 313 поставок, 3667 товаров, 24 коэффициента сезонности и 497 строк менеджера. Исходники не изменялись.
- Рабочий UI больше не импортирует `app.mock` и не предлагает режим моков. Кэш данных зависит от времени/размера parquet; пересборка требует нового расчета, изменение параметров показывает предупреждение.
- Исправлены замечания AppTest: очищенная причина нормализуется до пустой строки; нулевые количества сохраняются как утвержденное исключение, включая полностью отмененный заказ; изменения отзывают утверждение. `needs_review` с положительным количеством требует пояснения проверки. JSON сохраняет время утверждения, атомарная запись и блокировка защищают сессии одного процесса. Для нескольких реплик нужен другой storage — в плане.
- По IEK и оценочным строкам SE показано предупреждение об оценке текущего остатка; утверждение требует отметки о сверке со складом. Это не превращает оценку в фактический остаток; неизвестные поступления нельзя восстановить достоверно из имеющихся файлов.
- Карточка товара выбирает весь каталог, поэтому LOOP `130200305_` доступна даже без текущей рекомендации. На графике маркеры разовых продаж/дефицита, под ним исходные строки и причины, кратность и источник остатка. `forecast_H` распределяется по дням оставшегося горизонта, подпись явно отличает его от полного месячного прогноза.
- Вызов `explain_line` теперь получает `supplier` вместе с остальными полями. Добавлена сводка поставщика; она считает `final_qty`, а не старую рекомендацию. Исправлены NaN, допуск выдуманных малых чисел и выбор image-модели. Лексическая проверка чисел не является доказательством смысловой корректности LLM; детерминированные количества остаются источником решения. Платные API-вызовы в тестах не выполнялись, проверен шаблонный fallback.
- Семь сценариев факторов выполняют настоящий `pipeline.run`, показывают индикатор выполнения; изменение дополнительного прихода скрывает устаревшую таблицу. Сравнение SE использует арифметическое среднее за 12 полных месяцев (факт и регулярный спрос отдельно), сортирует разницу спроса либо заказа; пустой заказ менеджера не заменяется нулем.
- Экспорт только утвержденных положительных строк; причина решения менеджера добавлена в обоснование. Сохранилась защита CSV/XLSX от формул. Тестовый файл утверждений изолирован, реальные пользовательские утверждения не создавались.
- Воспроизводимая проверка: `.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest_cache/all-real-final` → 62 passed; `tests/test_ui_real.py` использует настоящие parquet и реальный движок. `scripts/ui_browser_smoke.py` проверяет пять вкладок, карточку LOOP и узкий экран через установленный Microsoft Edge; снимки в `.pytest_cache/ui-screenshots` (не коммитятся). Для скрипта отдельно установить `playwright`.
- После обновления Python-модулей перезапустить Streamlit: старый сервер мог сохранять импортированный модуль. Сервер: `.venv/Scripts/python.exe -m streamlit run app/ui/app.py --server.headless=true --server.port=8501 --browser.gatherUsageStats=false`; адрес `http://localhost:8501`. Нажать «Рассчитать»; подтвержденные исходные данные по 2026-09-22, не живой склад.

Ниже — история предыдущего состояния; замечания к UI из нее устранены этой работой.

- 2026-09-23: Implemented Streamlit tabs for order editing/approval/export, product history, factor checks, SE manager comparison, and one-off report. Approvals are saved in `data/state/approvals.json` and restored only when the calculated line signature matches; editing revokes prior approval. Mock approvals use a separate local state file. Exports include only approved positive rows, with CSV/XLSX formula escaping.
- 2026-09-23: On Windows, `.venv/Scripts/python.exe -m pytest -q tests/test_product.py` passed (3 tests); Streamlit AppTest completed the mock flow without exceptions. After the concurrent demand/calc updates, full suite without `data/clean` reports 28 passed, 24 skipped.
- 2026-09-23: Product tab now wires the existing `app/copilot.explain_line` to an explicit per-SKU button; without an API key it displays the template fallback. Review fixes: export re-reads persisted approvals, signatures cover all immutable row fields, and clearing edited quantity gives validation instead of an exception.
- 2026-09-23: Real UI remains blocked by source layout: `python -m app.adapters.build --raw datasets` raises `KeyError: 'Документ'` because IEK `Динамика продаж_2025-2026.xlsx` has MOQ headers. IEK `Ежемесячные остатки...xlsx` has invoice headers, `Путь ИЭК...xlsx` has monthly stock headers, and `Сезонность ИЭК.xlsx` has transit headers; an IEK seasonality workbook matching the adapter is absent. Keep adapter ownership with the data team; see README and `docs/demo.md`.
- 2026-09-23 (Person 2): the «Real UI remains blocked» note above is resolved — `datasets/IEK` workbooks were misnamed; files fixed, real-data build and UI verified (AppTest, checks tab on IEK `130300792_`).
