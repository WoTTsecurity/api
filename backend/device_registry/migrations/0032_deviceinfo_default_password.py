# Generated by Django 2.1.7 on 2019-05-16 14:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0031_merge_20190514_1031'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceinfo',
            name='default_password',
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
