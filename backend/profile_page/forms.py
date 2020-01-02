from django import forms
from django.contrib.auth.forms import AuthenticationForm as DjangoAuthenticationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm

from registration.forms import RegistrationFormUniqueEmail, User

from phonenumber_field.formfields import PhoneNumberField

from .models import Profile


class ProfilePaymentPlanForm(forms.ModelForm):
    subscription_status = forms.CharField(required=False, label='Subscription status', disabled=True,
                                          widget=forms.TextInput(attrs={'placeholder': ''}))
    current_period_ends = forms.DateTimeField(required=False, label='Billing period ends', disabled=True,
                                              widget=forms.DateTimeInput(attrs={'placeholder': ''}))
    nodes_number = forms.IntegerField(min_value=1, initial=1, label='Nodes number (besides 1 given for free)')
    payment_method_id = forms.CharField(max_length=255, widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_plan'].choices = Profile.PAYMENT_PLAN_CHOICES[:2]
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['placeholder'] = ''

    class Meta:
        model = Profile
        fields = ['payment_plan']


class PasswordChangeForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['placeholder'] = ''


class ProfileForm(forms.Form):
    username = forms.CharField(disabled=True)
    payment_plan = forms.CharField(disabled=True)
    subscription_status = forms.CharField(required=False, label='Subscription status', disabled=True,
                                          widget=forms.TextInput(attrs={'placeholder': ''}))
    current_period_ends = forms.DateTimeField(required=False, label='Billing period ends', disabled=True,
                                              widget=forms.DateTimeInput(attrs={'placeholder': ''}))
    nodes_number = forms.IntegerField(required=False, label='Paid nodes (besides 1 given for free)',
                                      disabled=True, widget=forms.NumberInput(attrs={'placeholder': ''}))
    email = forms.EmailField()
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    company = forms.CharField(max_length=128, required=False)
    phone = PhoneNumberField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['placeholder'] = ''


class RegistrationForm(RegistrationFormUniqueEmail):
    """Registration form extended with few optional extra fields
    and with the `username` field disabled.
    """
    first_name = forms.CharField(max_length=30, required=False, label='First name (optional)')
    last_name = forms.CharField(max_length=150, required=False, label='Last name (optional)')
    company = forms.CharField(max_length=128, required=False, label='Company (optional)')
    phone = PhoneNumberField(required=False, label='Phone (optional)')
    payment_plan = forms.ChoiceField(choices=Profile.PAYMENT_PLAN_CHOICES[:2])
    nodes_number = forms.IntegerField(min_value=1, initial=1, label='Nodes number (besides 1 given for free)')
    payment_method_id = forms.CharField(max_length=255, widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['placeholder'] = ''

    def clean(self):
        self._validate_unique = True
        # Validate `payment_method_id` field's value if chosen plan is not free.
        if int(self.cleaned_data['payment_plan']) != Profile.PAYMENT_PLAN_FREE:
            payment_method_id = self.cleaned_data.get('payment_method_id', '').strip()
            if not payment_method_id or not payment_method_id.startswith('pm_'):
                raise forms.ValidationError('Wrong card info provided.')
        return self.cleaned_data

    class Meta:
        model = User
        fields = ["email"]


class AuthenticationForm(DjangoAuthenticationForm):
    """
    A form class based on the standard Django's AuthenticationForm with rewritten
    error message in order to make the `username` form field look like e-mail.
    """
    error_messages = {
        'invalid_login': "Please enter a correct e-mail and password. Note that both fields may be case-sensitive."
        ,
        'inactive': "This account is inactive.",
    }

    def clean_username(self):
        return self.cleaned_data['username'].lower()


class GithubForm(forms.Form):
    repo = forms.ChoiceField(required=False)

    def __init__(self, *args, **kwargs):
        repo_choices = kwargs.pop('repo_choices')
        super().__init__(*args, **kwargs)
        self.fields['repo'].choices = [(None, '')] + repo_choices
