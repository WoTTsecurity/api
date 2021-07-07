from django.urls import path

from django_prometheus import exports
from django.contrib.admin.views.decorators import staff_member_required

from .views import CeleryPulseTimestampView, ErrorView

urlpatterns = [
    path('celery/', CeleryPulseTimestampView.as_view(), name='celery_pulse'),
    path('error/', ErrorView.as_view(), name='error'),
    path('prometheus/', staff_member_required(exports.ExportToDjangoView), name='prometheus-django-metrics')
]
