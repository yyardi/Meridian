# Recorder image. Same image runs locally and in production — only env differs,
# so migrating off a laptop later is a config change, not a rebuild.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
COPY core ./core
COPY strategies ./strategies
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir -e .

# Migrations run before the recorder starts — never hand-run against prod.
CMD ["sh", "-c", "alembic upgrade head && python -m core --json-logs"]
