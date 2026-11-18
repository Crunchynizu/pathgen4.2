"""Settings shared by every environment.

Databases (docs/database.md, docs/tech_stack.md): SQLite in development, PostgreSQL in production.
Development uses SQLite unless DATABASE_URL points somewhere else; production requires PostgreSQL.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Values already in the environment win over .env (Railway sets the real ones).
load_dotenv(BASE_DIR / ".env", override=False)


def env(name, default=None):
    return os.environ.get(name, default)


def env_list(name, default=""):
    return [item.strip() for item in (env(name) or default).split(",") if item.strip()]


POSTGRES = "django.db.backends.postgresql"
SQLITE = "django.db.backends.sqlite3"


def database_from_env(*, postgres_only=False):
    """DATABASE_URL, or the development SQLite file when it is unset (never in production)."""
    url = env("DATABASE_URL")
    if not url:
        if postgres_only:
            raise ImproperlyConfigured("DATABASE_URL must point at PostgreSQL in production.")
        url = f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"
    if url.startswith("sqlite"):
        config = dj_database_url.parse(url)
    else:
        config = dj_database_url.parse(url, conn_max_age=60, conn_health_checks=True)
    if config["ENGINE"] == SQLITE:
        if postgres_only:
            raise ImproperlyConfigured("Production runs on PostgreSQL: DATABASE_URL must start with postgres://")
        # Writes wait for each other instead of failing (docs/database.md, "Write boundaries").
        config["OPTIONS"] = {"transaction_mode": "IMMEDIATE", "timeout": 20}
    elif config["ENGINE"] != POSTGRES:
        raise ImproperlyConfigured("DATABASE_URL must be sqlite:/// (development) or postgres:// .")
    return config


SECRET_KEY = env("SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.classrooms",
    "apps.curriculum",
    "apps.practice",
    "apps.assessments",
    "apps.dashboards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": database_from_env()}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboards:home"
LOGOUT_REDIRECT_URL = "accounts:login"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT") or BASE_DIR / "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The fitted BKT and struggle-model files (docs/bkt.md, docs/agent.md). Phase 5.
MODEL_ARTIFACTS_DIR = BASE_DIR / "model_artifacts"

# Local Qwen feedback (docs/rag.md). Empty LLM_BASE_URL = off: the saved approved text is shown.
LLM_BASE_URL = env("LLM_BASE_URL", "")
LLM_MODEL = env("LLM_MODEL", "qwen2.5-0.5b-instruct-q4_k_m")
LLM_MODEL_VERSION = "qwen2.5-0.5b-instruct-q4_k_m@9217f5d, llama.cpp b12464"
LLM_TIMEOUT_SECONDS = float(env("LLM_TIMEOUT_SECONDS", "15"))
LLM_MAX_TOKENS = int(env("LLM_MAX_TOKENS", "120"))
