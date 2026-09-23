# AI-Dostar в Docker

Образ `ai-dostar:ml-demand` содержит приложение, реальные подготовленные данные IEK/SE и обученную ML-модель. Подготовка Excel и обучение выполняются при сборке внутри Linux. При запуске контейнер сразу готов к расчёту обоими методами.

## Сборка и запуск

Нужен работающий Docker Engine / Docker Desktop в режиме Linux containers. Из корня репозитория:

```powershell
docker compose build
docker compose up -d --wait
```

Сайт: **http://127.0.0.1:8502**. Порт 8502 выбран, чтобы не мешать локальному Python-серверу на 8501. Другой порт в PowerShell:

```powershell
$env:AIDOSTAR_PORT = "8503"
docker compose up -d --wait
```

Проверка и логи:

```powershell
docker compose ps
docker compose logs --tail 100 web
docker compose exec web python -m pip check
```

Остановка: `docker compose down`. Именованный volume `ai-dostar_approvals` сохраняет утверждённые заказы между пересозданиями контейнера. Команда `down -v` удалит этот volume вместе с сохранёнными решениями; для обычной остановки `-v` не нужен.

## Что находится в образе

| Компонент | Реализация |
|---|---|
| Python и зависимости | Python 3.14 slim, версии библиотек зафиксированы в `requirements-docker.lock` |
| Данные | `app.adapters.build --raw datasets` читает оригинальные книги двух поставщиков |
| ML | `app.ml.train` обучает и сохраняет модель на тех же Linux-библиотеках, которые загружают её в контейнере |
| Готовое приложение | Финальный этап содержит код, `data/clean` и `data/models`; Excel остаются на этапе подготовки |
| Пользователь | Приложение работает под `appuser`, UID 10001 |
| Сохранение заказов | Volume подключён к `/app/data/state` |
| Healthcheck | Проверяет HTTP `/_stcore/health` на внутреннем порту 8501 |
| Контекст сборки | Только код, файлы зависимостей и оригинальные Excel; `.env`, `.git`, `.venv`, локальные модели и утверждения исключены |

[Dockerfile](../Dockerfile) использует [несколько этапов сборки](https://docs.docker.com/build/building/multi-stage/); [healthcheck](https://docs.docker.com/reference/dockerfile/#healthcheck) проверяет доступность сервера. Проверка healthcheck сама по себе не заменяет тесты расчёта и браузера.

Расчёт и ML работают без внешнего API. Для текстового копилота можно задать `OPENAI_API_KEY`, `OPENAI_MODEL` и `COPILOT_ENABLED` через локальный `.env` или окружение терминала: Compose передаёт их при запуске. Ключ в образ не встраивается. Образ содержит производные от реальных данных проекта; Docker registry этой задачей не публикуется.

## Изменение данных и перенос

После изменения Excel или кода пересоберите образ и пересоздайте контейнер: `docker compose up -d --build --wait`. Локальный Windows-файл `demand.joblib` не переносится в Linux; модель строится внутри образа. Не подключайте весь локальный `data/` поверх `/app/data`, иначе он скроет подготовленные в образе данные и модель.

Сохранить образ для передачи файлом:

```powershell
docker save -o ai-dostar-ml-demand.tar ai-dostar:ml-demand
# На другой машине:
docker load -i ai-dostar-ml-demand.tar
docker compose up -d --no-build --wait
```

Нужен также `compose.yaml` для параметров запуска. Для Linux AMD64 используйте образ, собранный на этой архитектуре; на другой архитектуре пересоберите его из исходников. Сохранённые утверждения в tar образа не входят: они находятся в отдельном volume.
