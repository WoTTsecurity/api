from device_registry.forms import ClaimDeviceForm, DeviceCommentsForm
from django.views.generic.list import ListView
from django.views.generic import View
from django.http import HttpResponse, HttpResponseRedirect
from device_registry.models import Device, DeviceInfo, get_device_list, get_avg_trust_score
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required


@login_required
def root_view(request):
    return render(request, 'root.html', {
        'avg_trust_score': get_avg_trust_score(request.user),
        'active_inactive': Device.get_active_inactive(request.user),
        'devices': get_device_list(request.user)
    })

@login_required
def profile_view(request):
    return render(request, 'profile.html')


@login_required
def claim_device_view(request):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        form = ClaimDeviceForm(request.POST)

        if form.is_valid():
            get_device = get_object_or_404(
                Device,
                device_id=form.cleaned_data['device_id']
            )
            if get_device.claimed():
                return HttpResponse('Device has already been claimed.')

            if not get_device.claim_token == form.cleaned_data['claim_token']:
                return HttpResponse('Invalid claim/device id pair.')

            get_device.owner = request.user
            get_device.save()
            return HttpResponse('Successfully claimed {}.'.format(form.cleaned_data['device_id']))

    # if a GET (or any other method) we'll create a blank form
    else:
        form = ClaimDeviceForm()

    return render(request, 'claim_device.html', {'form': form})


class DeviceDetailView(View):
    def get(self, request, *args, **kwargs):
        device_info = get_object_or_404(
            DeviceInfo,
            device__id=kwargs['pk'],
            device__owner=request.user
        )
        device = get_object_or_404(
            Device,
            id=kwargs['pk'],
            owner=request.user
        )
        context = {'device_info': device_info, 'device': device}
        return render(request, 'device_info.html', context)

    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            form = DeviceCommentsForm(request.POST)
            if form.is_valid():
                device = get_object_or_404(Device, id=kwargs['pk'], owner=request.user)
                device.comment = form.cleaned_data['comment']
                device.save()

                return HttpResponseRedirect(reverse('device-detail', kwargs={'pk': kwargs['pk']}))

        device_info = get_object_or_404(
            DeviceInfo,
            device__id=kwargs['pk'],
            device__owner=request.user
        )
        device = get_object_or_404(
            Device,
            id=kwargs['pk'],
            owner=request.user
        )
        context = {'device_info': device_info, 'device': device}
        return render(request, 'device_info.html', context)
