import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models import Q, Avg
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from dateutil.relativedelta import relativedelta, MO
from mixpanel import Mixpanel, MixpanelException
from phonenumber_field.modelfields import PhoneNumberField

from device_registry.models import RecommendedAction, Device, HistoryRecord
from device_registry.celery_tasks import github

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=User, dispatch_uid="user_save_lower")
def user_save_lower(sender, instance, *args, **kwargs):
    instance.username = instance.username.lower()


class Profile(models.Model):
    PAYMENT_PLAN_FREE = 1
    PAYMENT_PLAN_STANDARD = 2
    PAYMENT_PLAN_PROFESSIONAL = 3
    PAYMENT_PLAN_ENTERPRISE = 4
    PAYMENT_PLAN_CHOICES = (
        (PAYMENT_PLAN_FREE, 'Free'),
        (PAYMENT_PLAN_STANDARD, 'Standard'),
        (PAYMENT_PLAN_PROFESSIONAL, 'Professional'),
        (PAYMENT_PLAN_ENTERPRISE, 'Enterprise')
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    last_active = models.DateField(null=True, blank=True)
    company_name = models.CharField(blank=True, max_length=128)
    payment_plan = models.PositiveSmallIntegerField(choices=PAYMENT_PLAN_CHOICES, default=PAYMENT_PLAN_FREE)
    wizard_shown = models.BooleanField(default=False)
    phone = PhoneNumberField(blank=True)
    github_auth_code = models.CharField(blank=True, max_length=32)
    github_repo_id = models.PositiveIntegerField(blank=True, null=True)
    github_repo_url = models.URLField(blank=True)
    github_random_state = models.CharField(blank=True, max_length=32)
    github_oauth_token = models.CharField(blank=True, max_length=64)
    github_issues = JSONField(blank=True, default=dict)

    @property
    def actions_count(self):
        return RecommendedAction.objects.filter(
            Q(device__owner=self.user) & RecommendedAction.get_affected_query()) \
            .values('action_id').distinct().count()

    @property
    def actions_resolved_since_monday(self):
        monday = (timezone.now() - relativedelta(weekday=MO(-1))).date()
        return RecommendedAction.objects.filter(device__owner=self.user, resolved_at__gte=monday)\
            .values('action_id').distinct().count()

    @property
    def github_repos(self):
        try:
            return github.list_repos(self.github_oauth_token)
        except github.GithubError:
            self.github_oauth_token = ''
            self.save(update_fields=['github_oauth_token'])

    def fetch_oauth_token(self, code, state):
        self.github_oauth_token = github.get_token_from_code(code, state)
        self.save(update_fields=['github_oauth_token'])

    def track_first_device(self):
        if self.user.devices.count() == 1 and settings.MIXPANEL_TOKEN:
            try:
                mp = Mixpanel(settings.MIXPANEL_TOKEN)
                mp.track(self.user.email, 'First Node')
            except MixpanelException:
                logger.exception('Failed to send First Device event')

    @property
    def average_trust_score(self):
        devices = Device.objects.filter(owner=self.user, trust_score__isnull=False)
        if not devices.exists():
            return None
        return devices.aggregate(Avg('trust_score'))['trust_score__avg']

    def sample_history(self):
        """
        Count the number of newly resolved user's RAs in the last 24h, save it together with the user's average trust
        score into a new HistoryRecord.
        """
        now = timezone.now()
        day_ago = now - timezone.timedelta(hours=24)
        ra_resolved = RecommendedAction.objects.filter(
            status=RecommendedAction.Status.NOT_AFFECTED,
            resolved_at__gt=day_ago, resolved_at__lte=now,
            device__owner=self.user
        )
        HistoryRecord.objects.create(owner=self.user,
                                     recommended_actions_resolved=ra_resolved.count(),
                                     average_trust_score=self.average_trust_score)

