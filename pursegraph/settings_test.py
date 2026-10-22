"""Settings for pytest: the throwaway PostgreSQL from `compose.test.yaml`."""

import os
import re

from .settings import *  # noqa: F403
from .settings import BASE_DIR, DATABASES, STORAGES

DATABASES["default"].update(
    HOST=os.environ.get("POSTGRES_HOST", "localhost"),
    PORT=os.environ.get("POSTGRES_PORT", "5433"),
    PASSWORD=os.environ.get("POSTGRES_PASSWORD", "pursegraph"),
)
# Every worktree's tests share the one server, so each gets a test database of its own
# (test_pursegraph_109 in pursegraph-109) and two runs at once leave each other alone.
DATABASES["default"]["TEST"] = {"NAME": "test_" + re.sub(r"\W", "_", BASE_DIR.name)}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
