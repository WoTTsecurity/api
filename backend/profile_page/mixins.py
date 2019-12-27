import djstripe.models
import djstripe.settings


class LoginTrackMixin:
    """
    Set either signed_in or signed_up in context if the user has just signed in or registered.
    One of those will be set only once which allows on-page JS code to take proper actions like send tracking events.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for attr in ('signed_in', 'signed_up'):
            if attr in self.request.session:
                context[attr] = self.request.session[attr]
                del self.request.session[attr]
        return context


class StripeContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not djstripe.models.Plan.objects.exists():
            raise Exception(
                "No Product Plans in the dj-stripe database - create some in your "
                "stripe account and then "
                "run `./manage.py djstripe_sync_plans_from_stripe` "
                "(or use the dj-stripe webhooks)")
        context["STRIPE_PUBLIC_KEY"] = djstripe.settings.STRIPE_PUBLIC_KEY
        return context


class SyncSubscriptionsMixin:
    def sync_subscriptions(self, request):
        subscriptions = djstripe.models.Subscription.objects.filter(customer__subscriber=request.user)
        for subscription in subscriptions:
            djstripe.models.Subscription.sync_from_stripe_data(subscription.api_retrieve())
