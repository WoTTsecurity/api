# Generated by Django 2.1.9 on 2019-06-21 02:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0044_auto_20190620_0915'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='firewallstate',
            name='enabled',
        ),
        migrations.AddField(
            model_name='firewallstate',
            name='policy',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Enabled: Allow by default'), (2, 'Enabled: Block by default')], default=1),
        ),
    ]
