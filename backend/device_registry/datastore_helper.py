import logging
import os
from google.cloud import datastore

logger = logging.getLogger(__name__)


if 'DATASTORE_KEY_JSON' in os.environ:
    with open('/tmp/datastore.json', 'w') as keyfile:
        keyfile.write(os.environ['DATASTORE_KEY_JSON'])
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/datastore.json'
    datastore_client = datastore.Client()
else:
    datastore = None
    datastore_client = None
