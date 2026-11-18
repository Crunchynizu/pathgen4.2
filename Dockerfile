# The one Django image, for local development (compose.yaml) and Railway (railway.toml).
# docs/tech_stack.md. Python 3.13: the version every test ran on (PLAN.md, "Settled").
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    MEDIA_ROOT=/data/media

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are collected into the image (WhiteNoise serves them). The values here exist only
# for this build step: nothing connects to a database, and Railway supplies the real ones.
RUN SECRET_KEY=build-only DATABASE_URL=postgres://build@localhost:5432/build \
    ALLOWED_HOSTS=localhost CSRF_TRUSTED_ORIGINS=https://localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000
CMD gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --worker-class gthread --workers 3 --threads 4 --timeout 90
