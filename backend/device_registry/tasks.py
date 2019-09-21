import logging
import zlib
from itertools import groupby
from urllib.request import urlopen, Request

from django.db import transaction

from celery import shared_task

from .models import Device, Vulnerability, DebPackage

logger = logging.getLogger('django')


@shared_task
def update_trust_score():
    """
    Update trust score of devices marked as needing such update.
    """
    target_devices = Device.objects.filter(update_trust_score=True).only('pk')
    for device in target_devices:
        device.trust_score = device.get_trust_score()
        device.update_trust_score = False
        device.save(update_fields=['trust_score', 'update_trust_score'])


@shared_task
def fetch_vulnerabilities():
    """
    Download vulnerability index from Debian Security Tracker, parse it and store in db.
    """
    logger.info('fetching data..')

    suite = 'stretch'
    URL = "https://security-tracker.debian.org/tracker/debsecan/release/1/" + suite
    response = urlopen(Request(URL))
    compressed_data = response.read()
    data = zlib.decompress(compressed_data).decode()

    lines = data.split('\n')
    lines_split = groupby(lines, lambda e: e.strip() == '')
    lists = [list(group) for k, group in lines_split if not k]

    vuln_name_list, packages_list = lists[:2]
    if vuln_name_list.pop(0) != 'VERSION 1':
        logger.error('ERROR')
    vuln_names = [(name, desc) for (name, flags, desc) in map(lambda x: x.split(',', 2), vuln_name_list)]

    vulnerabilities = []
    logger.info('parsing data..')
    for package_desc in packages_list:
        (package, vnum, flags, unstable_version, other_versions) \
            = package_desc.split(',', 4)

        other_versions = other_versions.split(' ')
        if other_versions == ['']:
            other_versions = []
        v = Vulnerability(name=vuln_names[int(vnum)][0],
                          package=package,
                          unstable_version=unstable_version,
                          other_versions=other_versions,
                          is_binary=flags[0] == 'B',
                          urgency={' ': Vulnerability.Urgency.NONE,
                                   'L': Vulnerability.Urgency.LOW,
                                   'M': Vulnerability.Urgency.MEDIUM,
                                   'H': Vulnerability.Urgency.HIGH
                                   }[flags[1]],
                          remote={'?': None,
                                  'R': True,
                                  ' ': False
                                  }[flags[2]],
                          fix_available=flags[3] == 'F')
        vulnerabilities.append(v)
    logger.info('saving data...')
    # with transaction.atomic():
    Vulnerability.objects.all().delete()
    Vulnerability.objects.bulk_create(vulnerabilities)
    DebPackage.objects.update(processed=False)


@shared_task
def update_packages_vulnerabilities():
    packages = DebPackage.objects.filter(processed=False)
    for package in packages:
        actionable_valns = []
        vulns = Vulnerability.objects.filter(package=package.source_name)
        for vuln in vulns:
            if vuln.is_vulnerable(package.source_version) and vuln.fix_available:
                actionable_valns.append(vuln)
        # with transaction.atomic():
        package.vulnerabilities.set(actionable_valns)
        package.processed = True
        package.save(update_fields=['processed'])
