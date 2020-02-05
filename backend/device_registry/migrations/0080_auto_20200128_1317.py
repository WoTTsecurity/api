# Generated by Django 2.2.9 on 2020-01-28 13:17

from django.db import migrations


def generate_recommended_actions(apps, schema_editor):
    from device_registry.models import RecommendedAction
    RecommendedAction.update_all_devices()


class Migration(migrations.Migration):
    dependencies = [
        ('device_registry', '0079_vulnerability'),
    ]

    operations = [
        migrations.RunPython(generate_recommended_actions)
    ]