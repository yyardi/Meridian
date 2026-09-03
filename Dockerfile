# Recorder image. Same image runs locally and in production — only env differs,
# so migrating off a laptop later is a config change, not a rebuild.
FROM python:3.12-slim

# ENGINE IDENTITY (amendment 12): the commit this IMAGE was built from,
# baked in at build time so a container started from it always carries the
# right value. Deliberately NOT a runtime env: a plain `up -d` without
# --build would then stamp the checkout's current commit onto a container
# running older code — a lie in the exact column whose purpose is preventing
# lies. Engines that write cohort rows FAIL CLOSED when this is empty.
ARG GIT_COMMIT=""
ENV MERIDIAN_ENGINE_COMMIT=$GIT_COMMIT

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml ./
COPY core ./core
COPY strategies ./strategies
COPY alembic ./alembic
COPY alembic.ini ./
# The dashboard's static pages — core/api.py serves them from ../static.
COPY static ./static

RUN pip install --no-cache-dir -e .

# Migrations run before the recorder starts — never hand-run against prod.
CMD ["sh", "-c", "alembic upgrade head && python -m core --json-logs"]
