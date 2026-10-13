"""Settings for pytest: the throwaway PostgreSQL from `compose.test.yaml`."""

import os

from .settings import *  # noqa: F403
from .settings import DATABASES

DATABASES["default"].update(
    HOST=os.environ.get("POSTGRES_HOST", "localhost"),
    PORT=os.environ.get("POSTGRES_PORT", "5433"),
    PASSWORD=os.environ.get("POSTGRES_PASSWORD", "pursegraph"),
)

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
