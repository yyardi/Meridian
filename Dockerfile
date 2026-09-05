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
# engine_v2.record_cycle imports analysis.congestion_detector. Without this the
# import throws every cycle, the error is CAUGHT and logged as
# quote_v2_record_failed, and the engine quotes on perfectly while recording
# ZERO observations. Third occurrence of this exact omission in this project.
COPY analysis ./analysis
COPY alembic ./alembic
COPY alembic.ini ./
# The dashboard's static pages — core/api.py serves them from ../static.
COPY static ./static

# Extras are opt-in per image: services build with none, the trainer builds
# with `model` (xgboost + scikit-learn). Keeps the recorder/API images small
# and means adding a modelling dependency never rebuilds a running service.
ARG INSTALL_EXTRAS=""
RUN if [ -n "$INSTALL_EXTRAS" ]; then \
      pip install --no-cache-dir -e ".[$INSTALL_EXTRAS]"; \
    else \
      pip install --no-cache-dir -e .; \
    fi

# Migrations run before the recorder starts — never hand-run against prod.
CMD ["sh", "-c", "alembic upgrade head && python -m core --json-logs"]
