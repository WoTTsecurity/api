from backend.settings.base import *

DEBUG = True

SECRET_KEY = 'oj1k=g1q=ya-7yr0!=a%iq$f_)wvlwqwf$7f245$muev^)an!='

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'wott-backend'),
        'OPTIONS': {
            'connect_timeout': 3,
        },
    }
}
COMMON_NAME_PREFIX = 'd.wott-dev.local'
# STATIC_URL = 'http://localhost:8003/'
INSTALLED_APPS += ['django_extensions']
IS_DEV = True
IS_DASH = True
