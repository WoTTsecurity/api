# Generated by Django 2.1.9 on 2019-06-28 12:37

from django.db import migrations
from django.core.management import call_command

import tagulous.models.fields


def run_initial_tags_management_command(apps, schema_editor):
    call_command('initial_tags')


def update_existing_devices_meta_tags(apps, schema_editor):
    Device = apps.get_model('device_registry', 'Device')
    Tag = apps.get_model('device_registry', 'Tag')
    all_devices_tag = Tag.objects.get(name='Hardware: All')
    raspberry_pi_tag = Tag.objects.get(name='Hardware: Raspberry Pi')
    for device in Device.objects.all():
        if all_devices_tag not in device.tags:
            device.tags.add(all_devices_tag)
        if (hasattr(device, 'deviceinfo') and device.deviceinfo.device_manufacturer == 'Raspberry Pi' and
                raspberry_pi_tag not in device.tags):
            device.tags.add(raspberry_pi_tag)


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0047_merge_20190622_0343'),
    ]

    operations = [
        migrations.AlterField(
            model_name='credential',
            name='tags',
            field=tagulous.models.fields.TagField(_set_tag_meta=True, autocomplete_view='ajax-tags-autocomplete', blank=True, force_lowercase=True, help_text='Enter a comma-separated tag string', initial='Hardware: All, Hardware: Raspberry Pi', to='device_registry.Tag'),
        ),
        migrations.AlterField(
            model_name='device',
            name='tags',
            field=tagulous.models.fields.TagField(_set_tag_meta=True, autocomplete_view='ajax-tags-autocomplete', blank=True, force_lowercase=True, help_text='Enter a comma-separated tag string', initial='Hardware: All, Hardware: Raspberry Pi', to='device_registry.Tag'),
        ),
        migrations.RunPython(run_initial_tags_management_command),
        migrations.RunPython(update_existing_devices_meta_tags)
    ]