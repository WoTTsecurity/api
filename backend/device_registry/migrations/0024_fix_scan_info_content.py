# Generated by Django 2.1.7 on 2019-05-09 09:42

from django.db import migrations


def fix_scan_info_content(apps, schema_editor):
    PortScan = apps.get_model('device_registry', 'PortScan')
    for ps in PortScan.objects.all():
        if isinstance(ps.scan_info, str):
            ps.scan_info = []
            ps.save(update_fields=['scan_info'])


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0023_firewallstate_rules'),
    ]

    operations = [
        # migrations.RunPython(fix_scan_info_content),
    ]
