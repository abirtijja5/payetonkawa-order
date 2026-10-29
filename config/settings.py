"""
Configuration du micro-service Commandes - PayeTonKawa.

Toutes les valeurs sensibles ou qui changent selon l'environnement
(clés, hôtes, mode debug) sont lues dans les variables d'environnement.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "order"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-order")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# Préfixe d'URL quand le service est derrière la passerelle (ex. "/product")
FORCE_SCRIPT_NAME = os.environ.get("URL_PREFIX") or None
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # Swagger servi localement (fonctionne hors ligne)
    "django_prometheus",
    "orders",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Nécessaire pour afficher la page Swagger (/api/docs/)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

# Une base de données par micro-service (principe d'autonomie).
# - en production (Docker) : PostgreSQL, choisi avec DB_ENGINE=postgres
# - en développement et pour les tests : SQLite (aucune installation nécessaire)
if os.environ.get("DB_ENGINE") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "NAME": os.environ.get("DB_NAME", SERVICE_NAME),
            "USER": os.environ.get("DB_USER", SERVICE_NAME),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DB_PATH", BASE_DIR / "data" / "db.sqlite3"),
        }
    }

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STATIC_URL = f"{FORCE_SCRIPT_NAME or ''}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- API REST -----------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTStatelessUserAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Limitation du nombre d'appels (protection contre les abus - OWASP API4)
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "100/min"),
        "user": os.environ.get("THROTTLE_USER", "1000/min"),
    },
}

# Jetons JWT : la même clé de signature est partagée par les 3 services,
# le service Client émet les jetons, Produits et Commandes les vérifient.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", "dev-only-shared-jwt-key"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PayeTonKawa - API Commandes",
    "DESCRIPTION": "Prise et suivi des commandes.",
    "VERSION": "1.0.0",
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
}

# --- RabbitMQ (communication asynchrone entre services) -----------------
RABBITMQ = {
    "ENABLED": os.environ.get("RABBITMQ_ENABLED", "0") == "1",
    "HOST": os.environ.get("RABBITMQ_HOST", "localhost"),
    "PORT": int(os.environ.get("RABBITMQ_PORT", "5672")),
    "USER": os.environ.get("RABBITMQ_USER", "guest"),
    "PASSWORD": os.environ.get("RABBITMQ_PASSWORD", "guest"),
    "EXCHANGE": "payetonkawa.events",
}

# Adresses des autres services (appels REST synchrones)
CLIENT_SERVICE_URL = os.environ.get("CLIENT_SERVICE_URL", "http://localhost:8001")
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:8002")
SERVICE_TIMEOUT = float(os.environ.get("SERVICE_TIMEOUT", "3"))

# --- Journaux (logs) ----------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s [order] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    "loggers": {"pika": {"level": "WARNING"}},
}

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
