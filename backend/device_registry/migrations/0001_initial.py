# Generated by Django 2.1.5 on 2019-01-18 19:39

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Device',
            fields=[
                ('device_id', models.CharField(max_length=128, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_ping', models.DateTimeField(blank=True, null=True)),
                ('certificate', models.TextField(blank=True, null=True)),
                ('certificate_expires', models.DateTimeField(blank=True, null=True)),
                ('ipv4_address', models.GenericIPAddressField(blank=True, null=True, protocol='IPv4')),
                ('claim_token', models.CharField(editable=False, max_length=128)),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='device', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('created',),
            },
        ),
    ]
