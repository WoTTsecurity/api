# Generated by Django 2.2.10 on 2020-02-26 11:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('profile_page', '0011_merge_20191126_0607'),
        ('device_registry', '0083_auto_20200226_0527')
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='github_issues',
        ),
    ]