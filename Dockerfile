# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
WORKDIR /app
COPY requirements.txt requirements-docker.lock ./
RUN python -m pip install --no-cache-dir -r requirements.txt -c requirements-docker.lock \
    && python -m pip check

# Train using the same Linux libraries that will load the artifact at runtime.
FROM base AS prepared
COPY app ./app
COPY datasets/IEK/ ./datasets/IEK/
COPY ["datasets/Systeme electric/", "./datasets/Systeme electric/"]
RUN python -m app.adapters.build --raw datasets \
    && python -m app.ml.train

FROM base AS runtime
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/state \
    && chown -R appuser:appuser /app
COPY --chown=appuser:appuser app ./app
COPY --from=prepared --chown=appuser:appuser /app/data/clean ./data/clean
COPY --from=prepared --chown=appuser:appuser /app/data/models ./data/models
USER appuser
EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3); assert r.status == 200"]
CMD ["python", "-m", "streamlit", "run", "app/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--server.fileWatcherType=none"]
