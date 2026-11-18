"""Local development: debug on, reachable from phones on the same Wi-Fi."""
from .base import *  # noqa: F401,F403

DEBUG = True
SECRET_KEY = SECRET_KEY or "dev-only-not-secret"  # noqa: F405

# Phones on the same Wi-Fi reach the laptop by its LAN address, so any host is accepted locally.
ALLOWED_HOSTS = ["*"]

# Serve static files straight from static/ (no collectstatic needed locally or in tests).
WHITENOISE_AUTOREFRESH = True
