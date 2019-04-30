from django import forms


class ClaimDeviceForm(forms.Form):
    device_id = forms.CharField()
    claim_token = forms.CharField()


class DeviceCommentsForm(forms.Form):
    comment = forms.CharField()


class ProfileForm(forms.Form):
    email = forms.CharField()
    first_name = forms.CharField(required=False)
    last_name = forms.CharField(required=False)
    company = forms.CharField(required=False)
