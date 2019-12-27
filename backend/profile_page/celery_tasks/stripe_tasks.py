import djstripe.models


def sync_subscriptions():
    """
    Sync all existing subscriptions status with Stripe.
     It's needed because our local payments info storage subsystem knows nothing about
     subscriptions statuses change.
    """
    for subscription in djstripe.models.Subscription.objects.all():
        # TODO: reduce the amount of work by excluding from sync subscriptions with statuses that can't be changed.
        djstripe.models.Subscription.sync_from_stripe_data(subscription.api_retrieve())
