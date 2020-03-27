from backend.settings.base import *

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'wott-backend',
        'USER': 'postgres',
        'PASSWORD': 'SuperSecurePassword',
        'HOST': 'psql',
        'OPTIONS': {
            'connect_timeout': 3,
        }
    }
}

COMMON_NAME_PREFIX = 'd.wott-dev.local'

# 3 parameters below are needed for views tests (they activate all url patterns).
IS_DASH = True
IS_API = True
IS_MTLS_API = True
DASH_URL = 'https://example.com'

# Stripe settings.
STRIPE_LIVE_PUBLIC_KEY = None
STRIPE_LIVE_SECRET_KEY = None
STRIPE_TEST_PUBLIC_KEY = None
STRIPE_TEST_SECRET_KEY = None
STRIPE_LIVE_MODE = False
WOTT_STANDARD_PLAN_ID = None
