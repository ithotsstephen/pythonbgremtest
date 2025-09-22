# Word to PDF Conversion (Production Guide)

This document explains how the `/pdf-converter/word-to-pdf` endpoint is hardened for production and how to deploy it safely.

## Features Implemented
- LibreOffice headless conversion with controlled timeout.
- Concurrency limiting via semaphore (`WORD_TO_PDF_PARALLEL`).
- Size limits (`WORD_TO_PDF_MAX_SIZE`, default 15MB).
- Allowed extension whitelist: `.docx, .doc, .odt, .rtf`.
- Clear error classification with HTTP status codes.
- Optional JSON responses (`Accept: application/json` or `?json=1`).
- Unique `X-Request-ID` header per conversion for trace correlation.
- Clean temporary directory handling (auto-deleted) per request.

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `WORD_TO_PDF_TIMEOUT` | 60 | Seconds before conversion is aborted. |
| `WORD_TO_PDF_MAX_SIZE` | 15728640 (15MB) | Max upload size in bytes. Rejects larger files. |
| `WORD_TO_PDF_ALLOWED_EXTS` | (code constant) | Modify in code or patch to add formats. |
| `LIBREOFFICE_PATH` | auto-detect | Explicit path to `soffice` if not on PATH. |
| `WORD_TO_PDF_PARALLEL` | 3 | Max concurrent conversions. |

## Docker Example
```dockerfile
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice fonts-dejavu fonts-liberation && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV WORD_TO_PDF_TIMEOUT=60 WORD_TO_PDF_MAX_SIZE=15728640 WORD_TO_PDF_PARALLEL=3
EXPOSE 8000
USER nobody
CMD gunicorn -w 4 -b 0.0.0.0:8000 app:app --timeout 120
```

## Nginx / Ingress Size Limit
```
client_max_body_size 15M;
```

## Example JSON Error
```json
{
  "status": "error",
  "code": "conversion_failed",
  "message": "LibreOffice produced no PDF. Details: ...",
  "request_id": "abc123def456"
}
```

## Logging Pattern
```
[WORD2PDF] req=<id> success file=<original> size=<bytes>B time=<ms>ms
[WORD2PDF] req=<id> error code=<code> msg=<message>
```
Ingest into your log system (e.g., Loki, ELK, CloudWatch) and create alerts for spikes in `conversion_failed` or `timeout`.

## Fonts
Install fonts for consistent layout:
```bash
apt-get install -y fonts-dejavu fonts-liberation fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji
```
Optional (licensing applies): `ttf-mscorefonts-installer`.

## Security Notes
- Runs LibreOffice as non-root (see Dockerfile `USER nobody`).
- Temp files deleted automatically.
- Consider virus scanning (ClamAV) if accepting untrusted public uploads.
- Keep LibreOffice updated for security fixes.

## Scaling Strategies
| Scenario | Strategy |
|----------|----------|
| Bursty traffic | Increase `WORD_TO_PDF_PARALLEL` modestly (watch memory). |
| High sustained throughput | Dedicated microservice + queue (Celery/RQ). |
| Very low latency | Persistent LibreOffice listener (unoconv/pyuno). |

## Health Check Endpoint (optional)
Add a simple route:
```python
@app.route('/health')
def health():
    return {'status':'ok','libreoffice': bool(_detect_libreoffice())}
```

## Troubleshooting
| Symptom | Likely Cause | Action |
|---------|--------------|--------|
| `no_libreoffice` | Package missing | Install LibreOffice or set `LIBREOFFICE_PATH`. |
| `conversion_failed` | Unsupported content / macro / corrupted doc | Re-save file in Word/LibreOffice; check stderr logs. |
| `timeout` | Large or complex document | Increase timeout or optimize document; check memory. |
| `busy` | Parallel limit reached | Raise `WORD_TO_PDF_PARALLEL` or scale horizontally. |

## Extending
- Add caching (hash of file → PDF) to avoid repeat conversion cost.
- Post-process PDF with `pikepdf` to linearize or optimize size.
- Track metrics (Prometheus counters) for successes/failures.

---
This guide reflects the hardened implementation currently in `app.py`. Adjust limits as traffic patterns evolve.
