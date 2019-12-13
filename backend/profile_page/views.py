from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView as DjangoLogoutView, LoginView as DjangoLoginView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import View, TemplateView, UpdateView

from registration.signals import user_registered
from registration.views import RegistrationView as BaseRegistrationView
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe
import djstripe.models
import djstripe.settings

from .forms import AuthenticationForm, GithubForm, ProfileForm, RegistrationForm, ProfileModelForm
from .mixins import LoginTrackMixin
from .models import Profile


class ProfileAccountView(LoginRequiredMixin, LoginTrackMixin, View):

    def dispatch(self, request, *args, **kwargs):
        self.user = request.user
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        if self.profile.paid_nodes_number > 0:
            nodes_number = self.profile.paid_nodes_number
        else:
            nodes_number = None
        self.initial_form_data = {'username': self.user.username, 'email': self.user.email,
                                  'first_name': self.user.first_name, 'last_name': self.user.last_name,
                                  'company': self.profile.company_name,
                                  'phone': self.profile.phone,
                                  'payment_plan': self.profile.get_payment_plan_display(),
                                  'nodes_number': nodes_number}
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = ProfileForm(initial=self.initial_form_data)
        return render(request, 'profile_account.html', {'form': form, 'tab_account': 'active'})

    def post(self, request, *args, **kwargs):
        form = ProfileForm(request.POST, initial=self.initial_form_data)
        if form.is_valid():
            self.user.email = form.cleaned_data['email']
            self.user.first_name = form.cleaned_data['first_name']
            self.user.last_name = form.cleaned_data['last_name']
            self.profile.company_name = form.cleaned_data['company']
            self.profile.phone = form.cleaned_data['phone']
            self.user.save(update_fields=['email', 'first_name', 'last_name'])
            self.profile.save(update_fields=['company_name', 'phone'])
            return HttpResponseRedirect(reverse('profile'))
        return render(request, 'profile_account.html', {'form': form, 'tab_account': 'active'})


class ProfileAPITokenView(LoginRequiredMixin, LoginTrackMixin, TemplateView):
    template_name = 'profile_token.html'
    extra_context = {'tab_api_token': 'active'}


class LoginView(DjangoLoginView):
    form_class = AuthenticationForm

    def form_valid(self, form):
        self.request.session['signed_in'] = True
        return super().form_valid(form)


class LogoutView(DjangoLogoutView):
    """
    Overwritten default Django's `LogoutView` in order to make it send a message
     with `django.contrib.messages` app.
    """

    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        logout(request)
        next_page = self.get_next_page()
        if next_page:
            messages.add_message(request, messages.INFO, 'You have successfully logged out. Now you can log in again.')
            # Redirect to this page until the session has been cleared.
            return HttpResponseRedirect(next_page)
        return super().dispatch(request, *args, **kwargs)


class GenerateAPITokenView(LoginRequiredMixin, LoginTrackMixin, View):
    def get(self, request, *args, **kwargs):
        if not hasattr(request.user, 'auth_token'):
            Token.objects.create(user=request.user)
        return HttpResponseRedirect(reverse('profile_token'))


class RevokeAPITokenView(LoginRequiredMixin, LoginTrackMixin, View):
    def get(self, request, *args, **kwargs):
        if hasattr(request.user, 'auth_token'):
            Token.objects.filter(user=request.user).delete()
        return HttpResponseRedirect(reverse('profile_token'))


class RegistrationView(BaseRegistrationView):
    """Overwritten standard registration view from the 'django-registration-redux' 3rd party app."""
    success_url = '/'
    form_class = RegistrationForm
    template_name = 'registration/registration_form.html'

    def register(self, form):
        new_user = form.save(commit=False)
        username_field = getattr(new_user, 'USERNAME_FIELD', 'username')
        # Save lowercased email as username.
        setattr(new_user, username_field, form.cleaned_data['email'].lower())
        new_user.first_name = form.cleaned_data.get('first_name', '')
        new_user.last_name = form.cleaned_data.get('last_name', '')
        new_user.save()
        new_user = authenticate(username=getattr(new_user, username_field), password=form.cleaned_data['password1'])
        login(self.request, new_user)
        user_registered.send(sender=self.__class__, user=new_user, request=self.request)
        profile, _ = Profile.objects.get_or_create(user=new_user)
        self.request.session['signed_up'] = True
        profile.payment_plan = int(form.cleaned_data['payment_plan'])
        profile.company_name = form.cleaned_data.get('company', '')
        profile.phone = form.cleaned_data.get('phone', '')
        profile.save(update_fields=['payment_plan', 'company_name', 'phone'])
        if profile.payment_plan != Profile.PAYMENT_PLAN_FREE:
            messages.add_message(self.request, messages.INFO,
                                 'Congratulations! We won\'t charge you for this plan for now.')
        #################
        # # TODO: properly handle free tier case.
        # Create the stripe Customer.
        nodes_number = form.cleaned_data.get('nodes_number')
        stripe_source = form.cleaned_data.get('stripe_source')
        if profile.payment_plan == Profile.PAYMENT_PLAN_STANDARD and nodes_number is not None and \
                stripe_source is not None:
            # Collect customer's info for Stripe.
            name = ('%s %s' % (form.cleaned_data.get('first_name', ''),
                               form.cleaned_data.get('last_name', ''))).strip()
            company = form.cleaned_data.get('company', '').strip()
            if company:
                name += ' (%s)' % company
            # Create a Stripe customer.
            stripe_customer = djstripe.models.Customer._api_create(
                email=new_user.email,
                phone=form.cleaned_data.get('phone'),
                name=name if name else None
            )
            # Create models instance for the customer.
            customer, created = djstripe.models.Customer.objects.get_or_create(
                id=stripe_customer["id"],
                defaults={
                    "subscriber": new_user,
                    "livemode": stripe_customer["livemode"],
                    "balance": stripe_customer.get("balance", 0),
                    "delinquent": stripe_customer.get("delinquent", False),
                },
            )
            # Add the source as the customer's default card
            customer.add_card(stripe_source)
            # Using the Stripe API, create a subscription for this customer,
            # using the customer's default payment source
            stripe_subscription = stripe.Subscription.create(customer=customer.id,
                                                             billing='charge_automatically',
                                                             plan=settings.WOTT_STANDARD_PLAN_ID,
                                                             quantity=nodes_number,
                                                             trial_from_plan=True,
                                                             api_key=djstripe.settings.STRIPE_SECRET_KEY)
            # Sync the Stripe API return data to the database,
            # this way we don't need to wait for a webhook-triggered sync
            djstripe.models.Subscription.sync_from_stripe_data(stripe_subscription)
        #################
        return new_user

    def get_initial(self):
        """
        Take a payment plan GET parameter value and pass it to the form
         as an initial value of its `payment_plan` field.
         All irrelevant values will be simply ignored by the form.
        Needed for setting appropriate plan value as default in the form field
         while redirected from the project site.
        """
        return {'payment_plan': self.request.GET.get('plan')}

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


class WizardCompleteView(LoginRequiredMixin, LoginTrackMixin, APIView):
    def post(self, request, *args, **kwargs):
        request.user.profile.wizard_shown = True
        request.user.profile.save(update_fields=['wizard_shown'])
        return Response(status=status.HTTP_200_OK)


class GithubIntegrationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        profile = request.user.profile
        if None in [settings.GITHUB_APP_ID, settings.GITHUB_APP_PEM, settings.GITHUB_APP_CLIENT_ID,
                    settings.GITHUB_APP_CLIENT_SECRET, settings.GITHUB_APP_REDIRECT_URL, settings.GITHUB_APP_NAME]:
            context = {'github_authorized': None}
        else:
            repos = profile.github_repos
            if repos is None:
                profile.github_random_state = uuid4().hex
                profile.save(update_fields=['github_random_state'])
                context = {
                    'github_authorized': False,
                    'github_auth_url': f'https://github.com/login/oauth/authorize?'
                                       f'client_id={settings.GITHUB_APP_CLIENT_ID}&'
                                       f'redirect_uri={settings.GITHUB_APP_REDIRECT_URL}&'
                                       f'state={profile.github_random_state}'
                }
            else:
                if profile.github_repo_id not in repos:
                    profile.github_repo_id = None  # Not saving because this is a GET
                form = GithubForm({'repo': profile.github_repo_id},
                                  repo_choices=[(repo_id, repo['full_name']) for repo_id, repo in repos.items()])
                context = {
                    'form': form,
                    'github_authorized': True,
                    'github_inst_url': f'https://github.com/apps/{settings.GITHUB_APP_NAME}/installations/new'
                }
        context['tab_github_integration'] = 'active'
        return render(request, 'profile_github.html', context)

    def post(self, request, *args, **kwargs):
        profile = request.user.profile
        repos = profile.github_repos
        form = GithubForm(request.POST,
                          repo_choices=[(repo_id, repo['full_name']) for repo_id, repo in repos.items()])
        if form.is_valid():
            repo = form.cleaned_data['repo']
            repo = int(repo) if repo else None
            if profile.github_repo_id != repo:
                profile.github_repo_id = repo
                profile.github_repo_url = repos[repo]['url'] if repo else ''
                profile.github_issues = {}
                profile.save(update_fields=['github_repo_id', 'github_repo_url', 'github_issues'])
            return HttpResponseRedirect(reverse('github_integration'))
        return render(request, 'profile_github.html', {'form': form, 'tab_github_integration': 'active'})


class SlackIntegrationView(LoginRequiredMixin, LoginTrackMixin, TemplateView):
    template_name = 'coming_soon.html'
    extra_context = {'tab_slack_integration': 'active', 'header': 'Slack Integration'}


class PaymentPlanView(LoginRequiredMixin, LoginTrackMixin, UpdateView):
    form_class = ProfileModelForm
    template_name = 'profile_payment.html'
    extra_context = {'tab_payment_plan': 'active'}
    success_url = reverse_lazy('profile')

    def get_object(self, queryset=None):
        return self.request.user.profile

    def form_valid(self, form):
        # TODO: put in one transaction.
        self.object = form.save()
        #######
        payment_plan = form.cleaned_data['payment_plan']
        nodes_number = form.cleaned_data.get('nodes_number')
        if payment_plan == Profile.PAYMENT_PLAN_FREE:
            # TODO: disable existing subscription or do nothing.
            pass
        elif payment_plan == Profile.PAYMENT_PLAN_STANDARD and nodes_number is not None:
            customer, created = djstripe.models.Customer.get_or_create(self.request.user)
            if not created:
                subscription = customer.subscription
                # TODO: create subscription if it's missing.
                subscription.update(quantity=nodes_number)
        #######
        return HttpResponseRedirect(self.get_success_url())

    def get_initial(self):
        initial = super().get_initial()
        initial['nodes_number'] = self.request.user.profile.paid_nodes_number
        return initial


class GithubCallbackView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        profile = request.user.profile
        if profile.github_random_state != request.GET.get('state'):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        request.user.profile.fetch_oauth_token(request.GET.get('code'), profile.github_random_state)
        return render(request, 'github_callback.html')
