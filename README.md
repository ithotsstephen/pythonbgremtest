# Flask Image & Document Toolkit

Tools included:
- Background removal and compositing with text/filters
- Image multi-size social export (zip)
- PDF split / merge / rotate / reorder via visual editor
- Word (doc/docx/rtf/odt) to PDF conversion (LibreOffice headless)
- OAuth (Google / Facebook / LinkedIn) and email/password auth with verification

## Quick Start (Local)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py  # dev server on :5000
```
Visit: http://127.0.0.1:5000

## Environment Variables (Common)
| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session & token signing secret. Set in prod. |
| `DATABASE_URL` | SQLAlchemy URL (defaults to sqlite:///app.db). |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | For verification emails. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Enable Google OAuth. |
| `FACEBOOK_CLIENT_ID` / `FACEBOOK_CLIENT_SECRET` | Enable Facebook OAuth. |
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | Enable LinkedIn OAuth. |
| `WORD_TO_PDF_TIMEOUT` | Conversion timeout seconds (default 60). |
| `WORD_TO_PDF_MAX_SIZE` | Max upload bytes (default 15728640). |
| `WORD_TO_PDF_PARALLEL` | Concurrent conversions (default 3). |
| `LIBREOFFICE_PATH` | Explicit soffice path if not on PATH. |

## Word to PDF Docs
See `README_WORD_TO_PDF.md` for detailed production notes.

## Docker
```bash
docker build -t doc-toolkit .
docker run --rm -p 8000:8000 \
  -e SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))') \
  doc-toolkit
```
App: http://127.0.0.1:8000

## Health Check
`GET /health` returns JSON including LibreOffice availability.

## Production Notes
- Run via Gunicorn behind Nginx/ALB.
- Provide persistent storage (S3) if long-term file retention required.
- Set `SECRET_KEY` and mail credentials.
- Add HTTPS termination at reverse proxy.

## Future Enhancements
- Rate limiting & metrics (Prometheus)
- MIME sniffing (python-magic) for uploads
- Queue (Celery/RQ) for heavy conversions
- Structured JSON access logs

## Legacy Notes (Original Static Front-End Deployment)
Below is the previous deployment guidance for a static Netlify front-end communicating with the Flask backend. Retained for reference.

<details><summary>Legacy Deployment Instructions</summary>

This project originally used a static Netlify front-end (in `static/`) and a Flask API backend you deploy separately. The front-end JavaScript called `/remove` for background removal.

### Render Backend Example
```
Start Command: gunicorn app:app --timeout 120 --workers 1
```
Health test:
```bash
curl https://your-service.onrender.com/health
```
Update `static/index.html` `API_URL` constant accordingly.

### CORS Hardening
```python
CORS(app, resources={r"/remove": {"origins": ["https://YOUR_NETLIFY_DOMAIN.netlify.app"]}})
```

</details>

## License
MIT (adjust as needed)

