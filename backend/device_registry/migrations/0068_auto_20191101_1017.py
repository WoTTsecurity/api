# Generated by Django 2.2.6 on 2019-11-01 10:17

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0067_device_mysql_root_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='cpu',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='device',
            name='kernel_deb_package',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='device_registry.DebPackage'),
        ),
    ]