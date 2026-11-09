FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# rasterio's bundled GDAL needs the system expat library.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install -r requirements-dev.txt; else pip install -r requirements.txt; fi

COPY . .

# /data/media is owned by the app user so the named "media" volume inherits writable permissions.
RUN useradd --create-home --uid 1000 namaa && chown -R namaa /app \
    && mkdir -p /data/media && chown namaa /data/media
USER namaa

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli load-districts && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
