# Generated by Django 2.1.5 on 2019-01-28 14:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0009_auto_20190126_2142'),
    ]

    operations = [
        migrations.AddField(
            model_name='deviceinfo',
            name='fqdn',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
