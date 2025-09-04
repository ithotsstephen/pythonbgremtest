# Deployment & Usage Guide

This project uses a static Netlify front-end (in `static/`) and a Flask API backend you must deploy separately (Render/Railway/Fly.io/etc.). The front-end JavaScript calls `/remove` on the backend to process images with rembg.

## 1. Backend Deployment (Render example)

1. Push repo to GitHub (already done).
2. Create new Web Service in Render, pick the repo.
3. Environment:
   - Build Command: (leave empty – Python autodetect) 
   - Start Command: `gunicorn app:app --timeout 120 --workers 1`
4. After deployment you get a URL like `https://your-service.onrender.com`.
5. Test health:
   ```bash
   curl https://your-service.onrender.com/health
   ```

## 2. Update Front-end API URL
Edit `static/index.html` and change:
```js
const API_URL='https://YOUR_BACKEND_DOMAIN/remove';
```
To:
```js
const API_URL='https://your-service.onrender.com/remove';
```

## 3. Netlify Setup
- In Netlify: New site from Git.
- Publish directory: `static`
- No build command.
- Deploy.

## 4. CORS Hardening (after confirming URL)
In `app.py` change CORS line to:
```python
CORS(app, resources={r"/remove": {"origins": ["https://YOUR_NETLIFY_DOMAIN.netlify.app"]}})
```

## 5. Local Development
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open: http://127.0.0.1:5000

## 6. API Contract
POST /remove
Form-data: `image` (binary)
Returns: PNG (image/png)
Errors: JSON `{ "error": "message" }`

## 7. Notes
- Netlify cannot run rembg server-side; it only serves static assets.
- Persistent files in `uploads/` and `results/` are ephemeral on most PaaS—consider S3 if you need long-term storage.
- Max upload size enforced: 12 MB.

## 8. Next Ideas
- Add rate limiting.
- Add queue for large images.
- Add background selection model variants (rembg session configs).

