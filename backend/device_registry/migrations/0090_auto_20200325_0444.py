# Generated by Django 2.2.11 on 2020-03-25 04:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('device_registry', '0089_auto_20200323_1008'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicehistoryrecord',
            name='cve_high_count',
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name='devicehistoryrecord',
            name='cve_low_count',
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name='devicehistoryrecord',
            name='cve_medium_count',
            field=models.IntegerField(null=True),
        ),
    ]
