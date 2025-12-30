FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

COPY requirements.txt /app/requirements.txt

# Upgrade tooling first, then install deps with retries/timeouts
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY app /app/app
COPY workers /app/workers
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
