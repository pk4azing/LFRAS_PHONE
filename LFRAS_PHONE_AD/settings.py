from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import timedelta


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-^7ajq9%b!&6*bbi@@9wp&g^p5=_l_7n06r^ob2dti9=p36_+5c",
)
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1", "0.0.0.0"]

INSTALLED_APPS = [
    # Django Defined
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_cron",
    # LocalApps
    "accounts",
    "router",
    "marketing",
    "tenants",
    "auditlog",
    "notifications",
    "storages",
    "documents",
    "tickets",
    "activities",
    "validation",
    "preferences",
    "payments",
    "django_browser_reload",
    "widget_tweaks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
    "accounts.middleware.MustChangePasswordMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "LFRAS_PHONE_AD.urls"

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
                "notifications.context_processors.notifications_context",
                "core.context_processors.role_theme",
            ],
        },
    },
]

WSGI_APPLICATION = "LFRAS_PHONE_AD.wsgi.application"
ASGI_APPLICATION = "LFRAS_PHONE_AD.asgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',  # database name
        'USER': 'postgres.xougfnhgpvwbubzizznx',
        'PASSWORD': 'Luc!d~2025_09',
        'HOST': 'aws-1-us-west-1.pooler.supabase.com',
        'PORT': '5432'
    }
}


AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # where static/mofi/... lives
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Session-auth redirects (template views wired below)
LOGIN_URL = "accounts:login"
LOGOUT_REDIRECT_URL = "accounts:login"
LOGIN_REDIRECT_URL = "router:role_redirect"

# Base key prefix for all tenant data in S3 (or local media fallback)
LUCID_S3_BASE_PREFIX = os.getenv(
    "LUCID_S3_BASE_PREFIX", "lucid/"
)  # e.g. "lucid/" or "" for root

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Email / SMTP configuration (values loaded from .env)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", os.getenv("EMAIL_HOST_USER", "notifications-noreply@lucidcompliances.com"))
SALES_EMAIL = os.getenv("SALES_EMAIL", "sales@lucidcompliances.com")

LUCID_EXPIRY_REMINDER_OFFSETS = [30, 14, 7, 1]  # days before expires_at
LUCID_EXPIRY_POST_INTERVAL_DAYS = 7


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "lfras-data")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "us-east-1")  # e.g. us-east-1
AWS_QUERYSTRING_AUTH = True

DJANGO_CRON_LOCK_BACKEND = "django_cron.backends.lock.cache.CacheLock"
DJANGO_CRON_MAX_LOG_ENTRIES = 1000
DJANGO_CRON_TIME_ZONE = "America/Chicago"  # ensure cron uses Central time

# Register cron classes (added in step 2)
CRON_CLASSES = [
    "documents.cron.SendExpiryNotificationsCron",
    "payments.cron.ExpireSubscriptionsCron",
]

ROLE_THEME_CLASS = {
    "LAD": "theme-lad",
    "LUS": "theme-lus",
    "EAD": "theme-ead",
    "EVS": "theme-ead",  # share theme with EAD
    "SUS": "theme-sus",
}

# S3 on
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

CSRF_TRUSTED_ORIGINS = [
    "https://lucidcompliances.com",
    "https://www.lucidcompliances.com",
]

AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None                  # keep objects private

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in ("1","true","yes")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() in ("1","true","yes")
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")  # e.g., Gmail App Password

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

FORCE_SMTP_IN_DEBUG = os.getenv("FORCE_SMTP_IN_DEBUG", "true").lower() in ("1", "true", "yes")
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "http://173.212.203.137:5372")