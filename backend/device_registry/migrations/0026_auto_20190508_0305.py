# Generated by Django 2.1.7 on 2019-05-06 09:05

from django.db import migrations
from django.contrib.postgres.fields import JSONField


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0025_auto_20190508_0253'),
    ]

    operations = [
        migrations.AddField(
            model_name='portscan',
            name='block_networks',
            field=JSONField(default=list),
        ),
        migrations.AddField(
            model_name='portscan',
            name='block_ports',
            field=JSONField(default=list),
        ),
    ]
