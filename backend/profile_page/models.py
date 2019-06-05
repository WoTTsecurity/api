from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User, dispatch_uid="user_save_lower")
def user_save_lower(sender, instance, *args, **kwargs):
    instance.username = instance.username.lower()


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(blank=True, null=True, max_length=128)
