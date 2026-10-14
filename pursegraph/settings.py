"""Django settings. Everything installation-specific comes from the environment (see `.env.example`)."""

import os
from datetime import timedelta
from pathlib import Path

from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "") == "1"
ALLOWED_HOSTS = [
    h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "axes",
    "members",
    "dashboard",
    "ledger",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # last, so it sees the outcome of the login view
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "pursegraph.urls"

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
                "ledger.context_processors.review_queue",
            ],
        },
    },
]

WSGI_APPLICATION = "pursegraph.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "NAME": os.environ.get("POSTGRES_DB", "pursegraph"),
        "USER": os.environ.get("POSTGRES_USER", "pursegraph"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Members

AUTH_USER_MODEL = "members.Member"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Invite and password-reset links (see members/links.py) are valid for 7 days.
PASSWORD_RESET_TIMEOUT = int(timedelta(days=7).total_seconds())

SESSION_COOKIE_AGE = int(timedelta(days=30).total_seconds())

# Failed-login lockout: a username is locked from an IP after 5 failures, for an hour.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/locked_out.html"

# Internationalization: English only in v1, but every UI string is marked for translation.

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "Europe/Ljubljana"
USE_TZ = True

# The original Statement files, kept so they can be re-parsed after a parser fix. Never served.

MEDIA_ROOT = Path(os.environ.get("PURSEGRAPH_STATEMENT_FILES", BASE_DIR / "statement-files"))

# The local Ollama server that suggests Subcategories (see ledger/ollama.py), e.g. http://192.168.50.188:11434.
# Unset, the Review queue fills without suggestions.

OLLAMA_URL = os.environ.get("OLLAMA_URL", "")

# Static files: HTMX and ECharts are vendored under static/vendor and served by WhiteNoise.

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
