# Production Dockerfile for the Flask app with LibreOffice
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
# System packages (libreoffice + fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    fonts-dejavu \
    fonts-liberation \
    fonts-noto-core \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Environment defaults (override at runtime)
ENV WORD_TO_PDF_TIMEOUT=60 \
    WORD_TO_PDF_MAX_SIZE=15728640 \
    WORD_TO_PDF_PARALLEL=3 \
    PYTHONUNBUFFERED=1
# Drop privileges
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
# Healthcheck could curl /health once running via docker compose (not added here)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app", "--timeout", "120"]
