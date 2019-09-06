from django.contrib import admin
from django_json_widget.widgets import JSONEditorWidget
from django.contrib.postgres.fields import JSONField

from device_registry.models import Device, Credential


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = [
        'device_id',
        'created',
        'last_ping',
        'owner',
        'claimed',
    ]

    list_filter = (
        'last_ping',
    )

    ordering = ('last_ping',)
    readonly_fields = ('claim_token', 'fallback_token')
    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget},
    }


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ['owner', 'name', 'data', 'linux_user']
    list_filter = ['owner']

    formfield_overrides = {
        JSONField: {'widget': JSONEditorWidget},
    }
