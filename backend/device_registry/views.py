from django.views.generic import DetailView, ListView
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required

from device_registry.forms import ClaimDeviceForm, DeviceAttrsForm, PortsForm, ConnectionsForm, CredentialsForm
from device_registry.models import Action, Device, get_device_list, average_trust_score, PortScan, FirewallState, \
    Credential
from device_registry.models import get_bootstrap_color
from profile_page.forms import ProfileForm
from profile_page.models import Profile


@login_required
def root_view(request):
    avg_trust_score = average_trust_score(request.user)
    return render(request, 'root.html', {
        'avg_trust_score': avg_trust_score,
        'avg_trust_score_percent': int(avg_trust_score * 100) if avg_trust_score is not None else None,
        'avg_trust_score_color': get_bootstrap_color(
            int(avg_trust_score * 100)) if avg_trust_score is not None else None,
        'active_inactive': Device.get_active_inactive(request.user),
        'devices': get_device_list(request.user)
    })

@login_required
def profile_view(request):
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    if request.method == 'POST':
        form = ProfileForm(request.POST)

        if form.is_valid():
            user.email = form.cleaned_data['email']
            user.first_name = form.cleaned_data['first_name']
            user.last_name = form.cleaned_data['last_name']
            profile.company_name = form.cleaned_data['company']
            profile.save()
            user.save()
    return render(request, 'profile.html')


@login_required
def claim_device_view(request):
    # if this is a POST request we need to process the form data
    text = style = None
    if request.method == 'POST':
        form = ClaimDeviceForm(request.POST)

        if form.is_valid():
            try:
                get_device = Device.objects.get(
                    device_id=form.cleaned_data['device_id']
                )
                if get_device.claimed:
                    text, style = 'Device has already been claimed.', 'warning'
                elif not get_device.claim_token == form.cleaned_data['claim_token']:
                    text, style = 'Invalid claim/device id pair.', 'warning'
                else:
                    get_device.owner = request.user
                    get_device.save()
                    text, style = f'You\'ve successfully claimed {get_device.get_name()}. '\
                                  f'Learn more about the security state of the device by clicking&nbsp;'\
                                  f'<a class="claim-link" href="{reverse("device-detail-security", kwargs={"pk": get_device.pk})}">' \
                                  f'here</a>.', \
                                  'success'
            except Device.DoesNotExist:
                text, style = 'Invalid claim/device id pair.', 'warning'

    # GET with claim_token and device_id set will fill the form.
    # Empty GET or any other request will generate empty form.
    if request.method == 'GET' and \
        'claim_token' in request.GET and \
            'device_id' in request.GET:
        try:
            Device.objects.get(
                device_id=request.GET['device_id']
            )
            form = ClaimDeviceForm(request.GET)
        except Device.DoesNotExist:
            text, style = 'Invalid claim/device id pair.', 'warning'
            form = ClaimDeviceForm()
    else:
        form = ClaimDeviceForm()

    return render(request, 'claim_device.html', {
        'form': form,
        'alert_style': style,
        'alert_text': text
    })


class DeviceDetailView(DetailView):
    model = Device
    template_name = 'device_info_overview.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        if 'form' not in context:
            context['form'] = DeviceAttrsForm(instance=self.object)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = DeviceAttrsForm(request.POST, instance=self.object)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('device-detail', kwargs={'pk': kwargs['pk']}))
        else:
            return self.render_to_response(self.get_context_data(form=form))


class DeviceDetailSoftwareView(DetailView):
    model = Device
    template_name = 'device_info_software.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        return context


class DeviceDetailSecurityView(DetailView):
    model = Device
    template_name = 'device_info_security.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        else:
            ports_form_data = self.object.portscan.ports_form_data()
            context['ports_choices'] = bool(ports_form_data[0])
            context['ports_form'] = PortsForm(open_ports_choices=ports_form_data[0],
                                              initial={'open_ports': ports_form_data[1]})
            connections_form_data = self.object.portscan.connections_form_data()
            context['connections_choices'] = bool(connections_form_data[0])
            context['connections_form'] = ConnectionsForm(open_connections_choices=connections_form_data[0],
                                                          initial={'open_connections': connections_form_data[1]})
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        portscan = self.object.portscan
        if 'is_ports_form' in request.POST:
            ports_form_data = self.object.portscan.ports_form_data()
            form = PortsForm(request.POST, open_ports_choices=ports_form_data[0])
            if form.is_valid():
                out_data = []
                for element in form.cleaned_data['open_ports']:
                    port_record_index = int(element)
                    out_data.append(ports_form_data[2][port_record_index])
                portscan.block_ports = out_data
                portscan.save(update_fields=['block_ports'])
        elif 'is_connections_form' in request.POST:
            connections_form_data = self.object.portscan.connections_form_data()
            form = ConnectionsForm(request.POST, open_connections_choices=connections_form_data[0])
            if form.is_valid():
                out_data = []
                for element in form.cleaned_data['open_connections']:
                    connection_record_index = int(element)
                    out_data.append(connections_form_data[2][connection_record_index])
                portscan.block_networks = out_data
                portscan.save(update_fields=['block_networks'])
        return HttpResponseRedirect(reverse('device-detail-security', kwargs={'pk': kwargs['pk']}))


class DeviceDetailNetworkView(DetailView):
    model = Device
    template_name = 'device_info_network.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        return context


class DeviceDetailHardwareView(DetailView):
    model = Device
    template_name = 'device_info_hardware.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        return context


class CredentialsView(ListView):
    model = Credential
    template_name = 'credentials.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)


@login_required
def actions_view(request, device_pk=None):
    if device_pk is not None:
        device = get_object_or_404(Device, pk=device_pk)
        device_name = device.get_name()
    else:
        device_name = None
    actions = []

    # Default username/password used action.
    insecure_password_devices = request.user.devices.filter(deviceinfo__default_password=True)
    if device_pk is not None:
        insecure_password_devices = insecure_password_devices.filter(pk=device_pk)
    if insecure_password_devices.exists():
        text_blocks = []
        for dev in insecure_password_devices:
            device_text_block = f'<a href="{ reverse("device-detail", kwargs={"pk": dev.pk}) }">{ dev.get_name() }</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            1,
            'Default credentials detected',
            'We found default credentials present on %s. Please consider changing them as soon as possible.' %
            ('this device' if device_name else full_string), []
        )
        actions.append(action)

    # Firewall disabled action.
    disabled_firewall_devices = request.user.devices.filter(firewallstate__enabled=False)
    if device_pk is not None:
        disabled_firewall_devices = disabled_firewall_devices.filter(pk=device_pk)
    if disabled_firewall_devices.exists():
        text_blocks = []
        for dev in disabled_firewall_devices:
            device_text_block = f'<a href="{ reverse("device-detail", kwargs={"pk": dev.pk}) }">{ dev.get_name() }</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            2,
            'Disabled firewall detected',
            'We found disabled firewall present on %s. Please consider enabling it.' %
            ('this device' if device_name else full_string), []
        )
        actions.append(action)

    # Telnet server running action.
    enabled_telnet_devices = request.user.devices.filter(portscan__scan_info__contains=[{'port': 23}]).exclude(
        portscan__block_ports__contains=[[23]])
    if device_pk is not None:
        enabled_telnet_devices = enabled_telnet_devices.filter(pk=device_pk)
    if enabled_telnet_devices.exists():
        text_blocks = []
        for dev in enabled_telnet_devices:
            device_text_block = f'<a href="{ reverse("device-detail", kwargs={"pk": dev.pk}) }">{ dev.get_name() }</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            3,
            'Enabled Telnet server detected',
            'We found enabled Telnet server present on %s. Please consider disabling it.' %
            ('this device' if device_name else full_string),
            ['buttons/block_telnet.html']
        )
        actions.append(action)

    return render(request, 'actions.html', {
        'actions': actions,
        'device_name': device_name,
        'device_pk': device_pk
    })
