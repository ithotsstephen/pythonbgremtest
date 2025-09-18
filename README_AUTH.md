# Authentication Setup

This app now supports:

- Email/password registration and login (Flask-Login)
- Google OAuth login (Authlib)

## Environment variables

Set these before running in production:

- `SECRET_KEY` — Flask session secret
- `DATABASE_URL` — SQLAlchemy database URI (defaults to `sqlite:///app.db`)
- `GOOGLE_CLIENT_ID` — Google OAuth client id (optional)
- `GOOGLE_CLIENT_SECRET` — Google OAuth secret (optional)
- `MAIL_SERVER` — SMTP host (optional; if not set, emails are printed to console)
- `MAIL_PORT` — SMTP port (default 587)
- `MAIL_USE_TLS` — `1` to enable TLS (default 1)
- `MAIL_USERNAME` — SMTP username
- `MAIL_PASSWORD` — SMTP password
- `MAIL_DEFAULT_SENDER` — From address for emails

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run (development)

```bash
export FLASK_ENV=development
python3 app.py
```

Open http://localhost:5000/ — you will be redirected to the login page if not authenticated.

## Notes

- Google login button shows only if `GOOGLE_CLIENT_ID` is configured.
- Existing image editing routes are now protected with `@login_required`.
- The default database is SQLite at `app.db` in the project root.
- Password reset available at `/forgot`, reset link `/reset/<token>` (valid 1 hour).
- Email verification required to use the app; after register you’ll land on `/verify` to resend the link.

## OAuth Setup

### Google

Set environment variables:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

Authorized redirect URL:

- `http://localhost:5000/auth/google/callback` (dev)
- `https://your-domain/auth/google/callback` (prod)

### Facebook

Create an app at https://developers.facebook.com/

Add OAuth redirect URL:

- `http://localhost:5000/auth/facebook/callback` (dev)
- `https://your-domain/auth/facebook/callback` (prod)

Set environment variables:

- `FACEBOOK_CLIENT_ID`
- `FACEBOOK_CLIENT_SECRET`

Requested permissions: `email`

### LinkedIn

Create an app at https://www.linkedin.com/developers/

Authorized redirect URL:

- `http://localhost:5000/auth/linkedin/callback` (dev)
- `https://your-domain/auth/linkedin/callback` (prod)

Set environment variables:

- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`

Requested permissions: `r_liteprofile`, `r_emailaddress`
