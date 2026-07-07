"""
Django settings for peopleskilltrainingapp project.
"""
import os
from pathlib import Path
from decouple import config
import dj_database_url
from datetime import timedelta


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=True, cast=bool)


ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,103.194.228.141,peopleskilltraining.com,api.compliancetrainned.com,api.compliancetrained.com,www.peopleskilltraining.com', cast=lambda v: [s.strip() for s in v.split(',')])


# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]


THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'django_celery_beat',  # ← ADDED
    'django_celery_results',  # ← ADDED (optional)
    'django_redis',  # ← ADDED
]


LOCAL_APPS = [
    'apps.authentication',
    'apps.users',
    'apps.webinars',
    'apps.enrollments',
    'apps.payments',
    'apps.analytics',
    'apps.notifications',
    'apps.integrations',
    'apps.oauth',
    'apps.attendees',
    'apps.speakers',
    'apps.cart',
    'apps.platforms',
]


INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.platforms.middleware.PlatformAPIKeyMiddleware',
]


ROOT_URLCONF = 'peopleskilltrainingapp.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], 
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


WSGI_APPLICATION = 'peopleskilltrainingapp.wsgi.application'


# ============================================
# DATABASE CONFIGURATION
# ============================================
# ============================================
# DATABASE CONFIGURATION
# ============================================

# DATABASE_URL = config('DATABASE_URL', default=None)

# if DATABASE_URL:
#     DATABASES = {
#         'default': dj_database_url.parse(
#             DATABASE_URL,
#             conn_max_age=300, 
#             ssl_require=True,
#             conn_health_checks=True,
#         )
#     }
    
#     DATABASES['default']['NAME'] = 'production'
    
#     DATABASES['default']['OPTIONS'] = {
#         'sslmode': 'require',
#     }
# else:
   
#     DATABASES = {
#         'default': {
#             'ENGINE': 'django.db.backends.sqlite3',
#             'NAME': BASE_DIR / 'db.sqlite3',
#         }
#     }

DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE"),
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT"),
    }
}


# Custom User Model
AUTH_USER_MODEL = 'users.User'


AUTHENTICATION_BACKENDS = [
    'apps.users.backends.EmailAuthBackend',
    'django.contrib.auth.backends.ModelBackend',
]


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --------------------------
# STATIC FILES (Local Only)
# --------------------------
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'  # local storage

# --------------------------
# MEDIA FILES (S3 / DO Spaces)
# --------------------------
SPACES_KEY = config('SPACES_KEY')
SPACES_SECRET = config('SPACES_SECRET')
SPACES_ENDPOINT = config('SPACES_ENDPOINT', default='sfo3.digitaloceanspaces.com')
SPACES_BUCKET = config('SPACES_BUCKET', default='peopleskilltraining-media')
SPACES_REGION = config('SPACES_REGION', default='sfo3')

AWS_ACCESS_KEY_ID = SPACES_KEY
AWS_SECRET_ACCESS_KEY = SPACES_SECRET
AWS_STORAGE_BUCKET_NAME = SPACES_BUCKET
AWS_S3_ENDPOINT_URL = f'https://{SPACES_ENDPOINT}'
AWS_S3_REGION_NAME = SPACES_REGION
AWS_S3_CUSTOM_DOMAIN = f'{SPACES_BUCKET}.{SPACES_REGION}.cdn.digitaloceanspaces.com'
AWS_DEFAULT_ACL = 'public-read'
AWS_QUERYSTRING_AUTH = False
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_LOCATION = 'media'

# Media files storage
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'

# Media files
# MEDIA_URL = '/media/'
# MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ============================================
# REST FRAMEWORK CONFIGURATION
# ============================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'EXCEPTION_HANDLER': 'rest_framework.views.exception_handler',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}


# ============================================
# JWT CONFIGURATION
# ============================================

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}


# ============================================
# CORS CONFIGURATION
# ============================================

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-platform-api-key',
]


# ============================================
# CELERY CONFIGURATION
# ============================================

CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=config('REDIS_URL', default='redis://localhost:6379/0'))
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=config('REDIS_URL', default='redis://localhost:6379/0'))

# Celery task settings
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = config('CELERY_TIMEZONE', default='UTC')
CELERY_ENABLE_UTC = True

# Celery task execution
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(config('CELERY_TASK_TIME_LIMIT', default=1800))  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = int(config('CELERY_TASK_SOFT_TIME_LIMIT', default=1500))  # 25 minutes

# Celery task retry
CELERY_TASK_AUTORETRY_FOR = (Exception,)
CELERY_TASK_RETRY_KWARGS = {'max_retries': 3, 'countdown': 60}
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Celery broker settings
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Celery events and monitoring
CELERY_SEND_TASK_SENT_EVENT = True
CELERY_RESULT_EXTENDED = True
CELERY_RESULT_EXPIRES = 3600  # 1 hour

# Celery worker settings
CELERY_WORKER_PREFETCH_MULTIPLIER = 4
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Celery Beat scheduler (periodic tasks)
CELERY_BEAT_SCHEDULER = config('CELERY_BEAT_SCHEDULER', default='django_celery_beat.schedulers:DatabaseScheduler')

# Task routing
CELERY_TASK_ROUTES = {
    'webinars.*': {'queue': 'webinars'},
    'integrations.*': {'queue': 'integrations'},
    'notifications.*': {'queue': 'notifications'},
}

# Celery autodiscover tasks
CELERY_IMPORTS = [
    'apps.webinars.tasks',
]


# ============================================
# REDIS & CACHE CONFIGURATION
# ============================================

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/1')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'KEY_PREFIX': 'peopleskill',
        'TIMEOUT': 300,  # 5 minutes default
    }
}


# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'


# ============================================
# EMAIL CONFIGURATION
# ============================================

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='businessemail.webeyesoft.com')
EMAIL_PORT = config('EMAIL_PORT', default=465, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=False, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='support@compliancetrained.com')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='support@compliancetrained.com')

FRONTEND_URL = config('WEBSITE_URL', default='https://www.peopleskilltraining.com/')

EMAIL_TEMPLATES_DIR = BASE_DIR / 'templates' / 'emails'
EMAIL_VERIFICATION_TOKEN_LIFETIME = timedelta(hours=24)
EMAIL_VERIFICATION_URL = config('EMAIL_VERIFICATION_URL', default=f"{FRONTEND_URL}/verify-email")

EMAIL_TEMPLATE_SETTINGS = {
    'COMPANY_NAME': config('COMPANY_NAME', default='People Skill Training'),
    'COMPANY_LOGO': config('COMPANY_LOGO_URL', default='https://www.peopleskilltraining.com/assets/logo.png'),
    'SUPPORT_EMAIL': config('SUPPORT_EMAIL', default='support@compliancetrained.com'),
    'COMPANY_ADDRESS': config('COMPANY_ADDRESS', default='2313 East Venango St Ste 4B PMB 1026,Philadelphia, PA 19134,United States'),
    'COMPANY_PHONE': config('COMPANY_PHONE', default='+1 (555) 123-4567'),
    'WEBSITE_URL': config('WEBSITE_URL', default='https://www.peopleskilltraining.com/'),
}

EMAIL_QUEUE_SETTINGS = {
    'BATCH_SIZE': 50,
    'DELAY_BETWEEN_BATCHES': 2,
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 300,
}

FIELD_ENCRYPTION_KEY = config(
    'FIELD_ENCRYPTION_KEY',
    default='qJ8vQ7KPmN2hR4tW9yB3xD6gH8kM5nP0sU1vZ4aE7fI='  # ⚠️ CHANGE THIS IN PRODUCTION!
)
# ============================================
# PAYMENT GATEWAY CONFIGURATION
# ============================================

# Stripe Configuration
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')

# Razorpay Configuration
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID', default='')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET', default='')


# ============================================
# THIRD-PARTY INTEGRATIONS
# ============================================

# Zoom Configuration
ZOOM_CLIENT_ID = config('ZOOM_CLIENT_ID', default='')
ZOOM_CLIENT_SECRET = config('ZOOM_CLIENT_SECRET', default='')
ZOOM_REDIRECT_URI = config('ZOOM_REDIRECT_URI', default='')
ZOOM_ACCOUNT_ID = config('ZOOM_ACCOUNT_ID', default='')

# Google OAuth
GOOGLE_OAUTH2_CLIENT_ID = config('GOOGLE_OAUTH2_CLIENT_ID', default='')
GOOGLE_OAUTH2_CLIENT_SECRET = config('GOOGLE_OAUTH2_CLIENT_SECRET', default='')

# Twilio SMS
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')
TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER', default='')

# Brevo (Sendinblue)
BREVO_API_KEY = config('BREVO_API_KEY', default='')


# ============================================
# LOGGING CONFIGURATION
# ============================================

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'django_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'django.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'celery_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'celery.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'webinar_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'webinars.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'email_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'email.log',
            'maxBytes': 1024 * 1024 * 5,  # 5MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'zoom_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'zoom.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'django_file'] if DEBUG else ['django_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'celery_file'] if DEBUG else ['celery_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.webinars': {
            'handlers': ['console', 'webinar_file'] if DEBUG else ['webinar_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'apps.notifications': {
            'handlers': ['console', 'email_file'] if DEBUG else ['email_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'apps.integrations': {
            'handlers': ['console', 'zoom_file'] if DEBUG else ['zoom_file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}


# ============================================
# FILE UPLOAD CONFIGURATION
# ============================================

FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2MB
ALLOWED_AVATAR_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif']


# ============================================
# PLATFORM CONFIGURATION
# ============================================

PLATFORM_API_KEY_HEADER = 'X-Platform-API-Key'
PLATFORM_CACHE_TIMEOUT = 3600  # 1 hour


# ============================================
# SECURITY SETTINGS FOR PRODUCTION
# ============================================

if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_REDIRECT_EXEMPT = []
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'


# ============================================
# DEVELOPMENT SPECIFIC SETTINGS
# ============================================

if DEBUG:
    # Django Debug Toolbar (if installed)
    try:
        import debug_toolbar
        INSTALLED_APPS += ['debug_toolbar']
        MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
        INTERNAL_IPS = ['127.0.0.1', 'localhost']
    except ImportError:
        pass


# ============================================
# CONFIGURATION STATUS (Development Only)
# ============================================

if DEBUG:
    print("\n" + "="*80)
    print("🚀 DJANGO CONFIGURATION LOADED")
    print("="*80)
    print(f"📍 Environment: {'DEVELOPMENT' if DEBUG else 'PRODUCTION'}")
    print(f"🔐 Custom User Model: {AUTH_USER_MODEL}")
    print(f"🔑 Authentication Backends:")
    for idx, backend in enumerate(AUTHENTICATION_BACKENDS, 1):
        print(f"   {idx}. {backend}")
    print(f"📧 Email Backend: {EMAIL_BACKEND}")
    print(f"📧 Email Host: {EMAIL_HOST}:{EMAIL_PORT}")
    print(f"💾 Database: {DATABASES['default']['ENGINE'].split('.')[-1]}")
    print(f"🎯 Frontend URL: {FRONTEND_URL}")
    print(f"📦 Redis/Celery: {CELERY_BROKER_URL}")
    print(f"🎯 Celery Beat Scheduler: {CELERY_BEAT_SCHEDULER}")
    print(f"📝 Logs Directory: {LOGS_DIR}")
    print(f"⏱️  Celery Task Time Limit: {CELERY_TASK_TIME_LIMIT}s")
    print(f"✅ Authentication Backends: {len(AUTHENTICATION_BACKENDS)}")
    print(f"🔄 Celery Task Routing: {len(CELERY_TASK_ROUTES)} queues")
    print("="*80 + "\n")
