# Generated by Django 2.1.9 on 2019-06-26 13:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0047_merge_20190622_0343'),
    ]

    operations = [
        migrations.AddField(
            model_name='credential',
            name='hardware',
            field=models.PositiveSmallIntegerField(choices=[(1, 'All devices'), (2, 'Raspberry Pi')], default=1),
        ),
    ]
