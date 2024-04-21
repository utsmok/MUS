
from pathlib import Path
from dotenv import load_dotenv
import os
from loguru import logger
#from pyzotero import zotero
#ZOTERO = zotero.Zotero(ZOTERO_PUBLIC, 'user', ZOTERO_PRIVATE)

dotenv_path = 'secrets.env'
load_dotenv(dotenv_path)

MONGOURL = str(os.getenv('MONGOURL'))
APIEMAIL = str(os.getenv('APIEMAIL'))
OPENAIRETOKEN = str(os.getenv('OPENAIRETOKEN'))
ZOTERO_PUBLIC = str(os.getenv('ZOTERO_PUBLIC'))
ZOTERO_PRIVATE = str(os.getenv('ZOTERO_PRIVATE'))

SCRAPEOPSKEY = str(os.getenv('SCRAPEOPSKEY'))
ORCID_CLIENT_ID = str(os.getenv('ORCID_CLIENT_ID'))
ORCID_CLIENT_SECRET = str(os.getenv('ORCID_CLIENT_SECRET'))

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = str(os.getenv('DJANGOSECRETKEY'))
ACCOUNT_ADAPTER = "accounts.adapter.NoNewUsersAccountAdapter"

DEBUG = True
LOGLEVEL = "DEBUG"
LOGFMT = "{time:[%m %d] %H:%M:%S} | {name}>{function}() [{level}] |> {message}"
logger.remove()
logger.add('log_mus.log', format=LOGFMT, level=LOGLEVEL)

ALLOWED_HOSTS = [
    "openalex.samuelmok.cc",
    "127.0.0.1",
    ".localhost",
    "*.samuelmok.cc",
    "[::1]" "*",
    'mus.samuelmok.cc',
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    "https://openalex.samuelmok.cc",
    "https://*.samuelmok.cc",
    "https://127.0.0.1",
    "https://openalex.samuelmok.cc/api",
    'https://openalex.samuelmok.cc/api/docs',
    'https://mus.samuelmok.cc',

]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "PureOpenAlex.apps.PureopenalexConfig",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    "accounts",
    'mus_backend.apps.MusBackendConfig',
    'corsheaders',
    "data_browser",
    "django_extensions",
    "ajax_datatable",
    "slippers",
    'explorer',
    'django_celery_results',
    'xclass_refactor.apps.XClassRefactorConfig',
    'django_sonar',
    # 'debug_toolbar',

]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    "django.middleware.security.SecurityMiddleware",
    #"debug_toolbar.middleware.DebugToolbarMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    'django_sonar.middlewares.requests.RequestsMiddleware',

]

CORS_ALLOWED_ORIGINS = [
    "https://openalex.samuelmok.cc",
    "https://samuelmok.cc",
    "https://127.0.0.1:9000",
    "https://127.0.0.1:3000",
    'https://mus.samuelmok.cc',
]

ROOT_URLCONF = "mus.urls"
CORS_ALLOW_CREDENTIALS = True

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": ["slippers.templatetags.slippers"],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "mus.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": str(os.getenv('POSTGRESDB')),
        "USER": str(os.getenv('POSTGRESUSER')),
        "HOST": str(os.getenv('POSTGRESHOST')),
        "PORT": str(os.getenv('POSTGRESPORT')),
        "PASSWORD": str(os.getenv('POSTGRESPWD')),
    },
    'readonly': {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": str(os.getenv('POSTGRESDB')),
        "USER": 'readonly',
        "HOST": str(os.getenv('POSTGRESHOST')),
        "PORT": str(os.getenv('POSTGRESPORT')),
        "PASSWORD": 'readonly',
    }
}
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(os.getenv('REDISHOST')),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
RQ_QUEUES = {
    "default": {
        "USE_REDIS_CACHE": "default",
    },
}

# Celery settings
CELERY_BROKER_URL = str(os.getenv('REDISHOST'))
CELERY_TIMEZONE = "Europe/Amsterdam"
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_BACKEND = 'django-db'

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

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

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = str(os.getenv('STATICROOT'))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

SITE_ID = 1

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_EMAIL_VERIFICATION = "none"
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

INTERNAL_IPS = [
    "127.0.0.1",
]

GRAPH_MODELS = {
    "all_applications": True,
    "group_models": True,
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

CACHE_TTL = 60 * 5

EXPLORER_CONNECTIONS = { 'Default': 'readonly' }
EXPLORER_DEFAULT_CONNECTION = 'readonly'

DJANGO_SONAR = {
    'excludes': [
        STATIC_URL,
        '/sonar/',
        '/admin/',
        '/__reload__/',
    ],
}