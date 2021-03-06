import json
import logging
import os

from google.cloud import datastore
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


if 'GOOGLE_CLOUD_KEY_JSON' in os.environ:
    key_json = json.loads(os.environ['GOOGLE_CLOUD_KEY_JSON'])
    credentials = service_account.Credentials.from_service_account_info(key_json)
    project = key_json.get('project_id')
else:
    credentials = project = None


def dicts_to_ds_entities(element, task_key=None):
    """
    Recursively process passed elements by:
    1) replacing dicts with Entity instances
       (required for managing indices of nested dicts);
    2) disabling indexing of all elements;

    `task_key` is supposed to be passed only to the 1st recursion call because
     we need the `task_key` added only to the top level object.
    """
    if isinstance(element, dict):
        entity = datastore.Entity(key=task_key, exclude_from_indexes=tuple(element.keys()))
        entity.update({key: dicts_to_ds_entities(value) for key, value in element.items()})
        return entity
    elif isinstance(element, list):
        return [dicts_to_ds_entities(e) for e in element]
    return element
