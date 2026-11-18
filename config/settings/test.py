"""Settings for `manage.py test`. Django makes its own test_* PostgreSQL database."""
from .development import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast, tests only
