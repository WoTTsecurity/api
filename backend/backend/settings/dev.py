from backend.settings.base import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'wott-backend'),
        'USER': os.getenv('DB_USER', 'wott-backend'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'psql'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 3,
        }
    }
}
COMMON_NAME_PREFIX = 'd.wott-dev.local'
STATIC_URL = 'http://localhost:8003/'

INSTALLED_APPS += [
    'django_extensions'
]

IS_DEV = True
# IS_API = IS_DEV = IS_DASH = IS_MTLS_API = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DASH_URL = 'http://localhost:8000'
ALLOWED_HOSTS = ['*']

# Stripe settings.
STRIPE_LIVE_PUBLIC_KEY = None
STRIPE_LIVE_SECRET_KEY = None
STRIPE_TEST_PUBLIC_KEY = 'pk_test_380KNHna4diAHvGVsucQ3pel00xbqUaSQf'
STRIPE_TEST_SECRET_KEY = 'sk_test_fICt6Rar7IYLVSvBYncQSGja00dXMw2Ufs'
STRIPE_LIVE_MODE = False  # Change to True in production.
DJSTRIPE_WEBHOOK_SECRET = 'whsec_KJPxeCf0oTnSw6ZGP9Kiqm7Mf5E6mnom'  # Not used, but still required.
WOTT_STANDARD_PLAN_ID = 'plan_GLUYYLh2OnuJwI'  # Monthly with 30d trial.
# WOTT_STANDARD_PLAN_ID = 'plan_GNgOchjZ4tXkQO'  # Monthly without trial.
# WOTT_STANDARD_PLAN_ID = 'plan_GQiy3tSBzYYuM9'  # Daily without trial.
# WOTT_STANDARD_PLAN_ID = 'plan_GQnlf795k5cWIY'  # Daily with 1d trial.
