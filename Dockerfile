# AI-Dostar: supplier order recommendations (Streamlit).
# Build: docker compose build     Run: docker compose up     Open: http://localhost:8501
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY datasets ./datasets

# Partner Excel -> data/clean/*.parquet at build time, so the container starts ready.
RUN python -m app.adapters.build --raw datasets

# Optional ML model (gradient boosting, ~1 min on CPU). Disable: --build-arg TRAIN_ML=0
ARG TRAIN_ML=1
RUN if [ "$TRAIN_ML" = "1" ]; then python -m app.ml.train; else echo "ML training skipped"; fi

# Unprivileged user; approvals are written to data/state (mounted as a volume by compose).
RUN useradd --create-home --uid 1000 dostar \
    && mkdir -p data/state \
    && chown -R dostar:dostar /app/data
USER dostar

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "app/ui/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
