import json
import uuid

from django.views.generic import DetailView, ListView, TemplateView, View, UpdateView, CreateView, DeleteView
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q

from .forms import ClaimDeviceForm, DeviceAttrsForm, PortsForm, ConnectionsForm, DeviceMetadataForm
from .forms import FirewallStateGlobalPolicyForm, GlobalPolicyForm
from .models import Action, Device, average_trust_score, PortScan, FirewallState, get_bootstrap_color, PairingKey
from .models import GlobalPolicy, RecommendedActions
from device_registry.api_views import DeviceListFilterMixin


class RootView(LoginRequiredMixin, DeviceListFilterMixin, ListView):
    model = Device
    template_name = 'root.html'
    context_object_name = 'mirai_devices'  # device list moved to ajax, so only mirai detected devices still here
    filter_dict = None

    def get_queryset(self):
        queryset = super().get_queryset()
        common_query = Q(owner=self.request.user, deviceinfo__detected_mirai=True)
        query = self.get_filter_q(set_filter_dict=True)
        return queryset.filter(common_query & query).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        avg_trust_score = average_trust_score(self.request.user)
        context.update({
            'avg_trust_score': avg_trust_score,
            'avg_trust_score_percent': int(avg_trust_score * 100) if avg_trust_score is not None else None,
            'avg_trust_score_color': get_bootstrap_color(
                int(avg_trust_score * 100)) if avg_trust_score is not None else None,
            'active_inactive': Device.get_active_inactive(self.request.user),
            'column_names': [
                'Node Name',
                'Hostname',
                'Last Ping',
                'Trust Score',
                'Recommended Actions'
            ],
            'filter_params': [(field_name, field_desc[1], field_desc[2]) for field_name, field_desc in
                              self.FILTER_FIELDS.items()],

            # TODO: convert this into a list of dicts for multiple filters
            'filter': self.filter_dict,
            'first_signin': self.request.user.profile.first_signin
        })
        self.request.user.profile.first_signin = False
        self.request.user.profile.save(update_fields=['first_signin'])
        return context


class GlobalPoliciesListView(LoginRequiredMixin, ListView):
    model = GlobalPolicy
    template_name = 'policies.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)


class ConvertPortsInfoMixin:
    def dicts_to_lists(self, ports):
        if ports:
            return [[d[k] for k in ('address', 'protocol', 'port', 'ip_version')] for d in ports]
        else:
            return []

    def lists_to_dicts(self, ports):
        return [{'address': d[0], 'protocol': d[1], 'port': d[2], 'ip_version': d[3]} for d in ports]


class GlobalPolicyCreateView(LoginRequiredMixin, CreateView, ConvertPortsInfoMixin):
    model = GlobalPolicy
    form_class = GlobalPolicyForm
    template_name = 'create_policy.html'
    success_url = reverse_lazy('global_policies')

    def form_valid(self, form):
        """
        Standard method overwritten in order to:
         - assign a proper owner
         - modify ports info to make it conform to the PortScan.block_ports field format
        """
        # Check name uniqueness.
        if GlobalPolicy.objects.filter(owner=self.request.user, name=form.cleaned_data['name']).exists():
            form.add_error('name', 'Global policy with this name already exists.')
            return super().form_invalid(form)

        self.object = form.save(commit=False)
        self.object.owner = self.request.user
        self.object.ports = self.dicts_to_lists(form.cleaned_data['ports'])
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        if 'pk' in kwargs:
            device = get_object_or_404(Device, owner=self.request.user, pk=kwargs['pk'])
            portscan_object, _ = PortScan.objects.get_or_create(device=device)
            firewallstate_object, _ = FirewallState.objects.get_or_create(device=device)
            if firewallstate_object.global_policy:
                return HttpResponseForbidden()
            # TODO: pass networks when we enable this field support.
            self.initial = {'policy': firewallstate_object.policy,
                            'ports': self.lists_to_dicts(portscan_object.block_ports)}
        return super().get(request, *args, **kwargs)


class GlobalPolicyEditView(LoginRequiredMixin, UpdateView, ConvertPortsInfoMixin):
    model = GlobalPolicy
    form_class = GlobalPolicyForm
    template_name = 'edit_policy.html'
    success_url = reverse_lazy('global_policies')

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def form_valid(self, form):
        """
        Standard method overwritten in order to:
         - modify ports info to make it conform to the PortScan.block_ports field format
        """
        # Check name uniqueness.
        if GlobalPolicy.objects.filter(owner=self.request.user, name=form.cleaned_data['name']).exclude(
                pk=form.instance.pk).exists():
            form.add_error('name', 'Global policy with this name already exists.')
            return super().form_invalid(form)

        self.object = form.save(commit=False)
        self.object.ports = self.dicts_to_lists(form.cleaned_data['ports'])
        self.object.save()
        return HttpResponseRedirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        """
        Standard method overwritten in order to:
         - modify ports info to format to the format expected by the frontend
        """
        self.object = self.get_object()
        self.object.ports = self.lists_to_dicts(self.object.ports)
        return self.render_to_response(self.get_context_data())


class GlobalPolicyDeleteView(LoginRequiredMixin, DeleteView):
    """
    Global policy delete view.

    The `get_queryset` method rewritten in order to limit access to other users' policies.
    """
    model = GlobalPolicy
    success_url = reverse_lazy('global_policies')

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)


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
                    text, style = 'Invalid claim/node id pair.', 'warning'
                else:
                    get_device.owner = request.user
                    get_device.claim_token = ""
                    get_device.save(update_fields=['owner', 'claim_token'])
                    text, style = f'You\'ve successfully claimed {get_device.get_name()}. ' \
                                  f'Learn more about the security state of the device by clicking&nbsp;' \
                                  f'<a class="claim-link" href="{reverse("device-detail-security", kwargs={"pk": get_device.pk})}">' \
                                  f'here</a>.', \
                                  'success'
            except Device.DoesNotExist:
                text, style = 'Invalid claim/node id pair.', 'warning'

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
            text, style = 'Invalid claim/node id pair.', 'warning'
            form = ClaimDeviceForm()
    else:
        form = ClaimDeviceForm()

    return render(request, 'claim_device.html', {
        'form': form,
        'alert_style': style,
        'alert_text': text
    })


class DeviceDetailView(LoginRequiredMixin, DetailView):
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
            if 'revoke_button' in form.data:
                self.object.owner = None
                self.object.claim_token = uuid.uuid4()
                self.object.save(update_fields=['owner', 'claim_token'])
                return HttpResponseRedirect(reverse('root'))
            else:
                form.save()
                return HttpResponseRedirect(reverse('device-detail', kwargs={'pk': kwargs['pk']}))
        return self.render_to_response(self.get_context_data(form=form))


class DeviceDetailSoftwareView(LoginRequiredMixin, DetailView):
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


class DeviceDetailSecurityView(LoginRequiredMixin, DetailView):
    model = Device
    template_name = 'device_info_security.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        has_global_policy = False
        try:
            context['firewall'] = self.object.firewallstate
        except FirewallState.DoesNotExist:
            context['firewall'] = None
        else:
            context['global_policy_form'] = FirewallStateGlobalPolicyForm(instance=self.object.firewallstate)
            has_global_policy = bool(self.object.firewallstate.global_policy)
            context['has_global_policy'] = has_global_policy
        try:
            context['portscan'] = self.object.portscan
        except PortScan.DoesNotExist:
            context['portscan'] = None
        else:
            if not has_global_policy:
                ports_form_data = self.object.portscan.ports_form_data()
                context['ports_choices'] = bool(ports_form_data[0])
                context['choices_extra_data'] = ports_form_data[3]
                context['ports_form'] = PortsForm(ports_choices=ports_form_data[0],
                                                  initial={'open_ports': ports_form_data[1],
                                                           'policy': self.object.firewallstate.policy})
                connections_form_data = self.object.portscan.connections_form_data()
                context['connections_choices'] = bool(connections_form_data[0])
                context['connections_form'] = ConnectionsForm(open_connections_choices=connections_form_data[0],
                                                              initial={'open_connections': connections_form_data[1]})
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        portscan = self.object.portscan
        firewallstate = self.object.firewallstate

        if 'global_policy' in request.POST:
            form = FirewallStateGlobalPolicyForm(request.POST, instance=firewallstate)
            if form.is_valid():
                firewallstate.global_policy = form.cleaned_data["global_policy"]
                firewallstate.save(update_fields=['global_policy'])

        elif 'is_ports_form' in request.POST:
            if firewallstate and firewallstate.global_policy:
                return HttpResponseForbidden()
            ports_form_data = self.object.portscan.ports_form_data()
            form = PortsForm(request.POST, ports_choices=ports_form_data[0])
            if form.is_valid():
                out_data = []
                for element in form.cleaned_data['open_ports']:
                    port_record_index = int(element)
                    out_data.append(ports_form_data[2][port_record_index])
                portscan.block_ports = out_data
                firewallstate.policy = form.cleaned_data['policy']
                # Stop snoozing 'Permissive firewall policy detected' recommended action.
                if int(firewallstate.policy) == FirewallState.POLICY_ENABLED_BLOCK and \
                        RecommendedActions.permissive_policy.value in self.object.snoozed_actions:
                    self.object.snoozed_actions.remove(RecommendedActions.permissive_policy.value)
                    updated_fields = ['update_trust_score', 'snoozed_actions']
                else:
                    updated_fields = ['update_trust_score']
                with transaction.atomic():
                    portscan.save(update_fields=['block_ports'])
                    firewallstate.save(update_fields=['policy'])
                    self.object.update_trust_score = True
                    self.object.save(update_fields=updated_fields)

        elif 'is_connections_form' in request.POST:
            if firewallstate and firewallstate.global_policy:
                return HttpResponseForbidden()
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


class DeviceDetailNetworkView(LoginRequiredMixin, DetailView):
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


class DeviceDetailHardwareView(LoginRequiredMixin, DetailView):
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


class DeviceDetailMetadataView(LoginRequiredMixin, DetailView):
    model = Device
    template_name = 'device_info_metadata.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self.object, 'portscan'):
            context['portscan'] = self.object.portscan
        else:
            context['portscan'] = None
        if hasattr(self.object, 'firewallstate'):
            context['firewall'] = self.object.firewallstate
        else:
            context['firewall'] = None
        if 'dev_md' not in context:
            device_metadata = self.object.deviceinfo.device_metadata
            context['dev_md'] = []
            for key, value in device_metadata.items():
                if isinstance(value, str):
                    context['dev_md'].append([key, value])
                else:
                    context['dev_md'].append([key, json.dumps(value)])
        if 'form' not in context:
            context['form'] = DeviceMetadataForm(instance=self.object.deviceinfo)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = DeviceMetadataForm(request.POST, instance=self.object.deviceinfo)
        if form.is_valid() and "device_metadata" in form.cleaned_data:
            self.object.deviceinfo.device_metadata = form.cleaned_data["device_metadata"]
            self.object.deviceinfo.save(update_fields=['device_metadata'])
            return HttpResponseRedirect(reverse('device-detail-metadata', kwargs={'pk': kwargs['pk']}))
        return self.render_to_response(self.get_context_data(form=form))


class CredentialsView(LoginRequiredMixin, TemplateView):
    template_name = 'credentials.html'

    def get_context_data(self, **kwargs):
        context = super(CredentialsView, self).get_context_data(**kwargs)
        context['pi_credentials_path'] = '/opt/wott/credentials'
        return context


class PairingKeysView(LoginRequiredMixin, TemplateView):
    template_name = 'pairing_keys.html'


class PairingKeySaveFileView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        if 'pk' in request.GET:
            try:
                key = PairingKey.objects.get(key=request.GET['pk'], owner=request.user)
                return self._save_file_response(key)
            except PairingKey.DoesNotExist:
                return HttpResponseBadRequest('Pairing-key not found')
        else:
            return HttpResponseRedirect(reverse('pairing-keys'))

    def _save_file_response(self, key_object):
        data = "[DEFAULT]\n\nenroll_token = {}".format(key_object.key.hex)
        response = HttpResponse(data, content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename = "config.ini"'
        return response


@login_required
def actions_view(request, device_pk=None):
    if device_pk is not None:
        device = get_object_or_404(Device, pk=device_pk, owner=request.user)
        device_name = device.get_name()
    else:
        device_name = None
    actions = []

    # Default username/password used action.
    devices = request.user.devices.filter(deviceinfo__default_password=True).exclude(
        snoozed_actions__contains=RecommendedActions.default_credentials.value)
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        text_blocks = []
        for dev in devices:
            device_text_block = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            'Default credentials detected',
            '<p>We found default credentials present on %s. Please consider changing them as soon as possible.</p>' %
            ('this node' if device_name else full_string),
            [RecommendedActions.default_credentials.value, list(devices.values_list('pk', flat=True))]
        )
        actions.append(action)

    # Firewall disabled action.
    devices = request.user.devices.exclude(
        firewallstate__policy=FirewallState.POLICY_ENABLED_BLOCK).exclude(
        snoozed_actions__contains=RecommendedActions.permissive_policy.value)
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        text_blocks = []
        for dev in devices:
            device_text_block = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            'Permissive firewall policy detected',
            '<p>We found permissive firewall policy present on %s. Please consider change it to more restrictive one.'
            '</p>' % ('this node' if device_name else full_string),
            [RecommendedActions.permissive_policy.value, list(devices.values_list('pk', flat=True))]
        )
        actions.append(action)

    # Vulnerable packages found action.
    devices = request.user.devices.filter(deb_packages__vulnerabilities__isnull=False).exclude(
        snoozed_actions__contains=RecommendedActions.vulnerable_packages.value).distinct()
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        text_blocks = []
        for dev in devices:
            device_text_block = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>' \
                                f'({dev.vulnerable_packages.count()} packages)'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        action = Action(
            'Vulnerable packages found',
            """<p>We found vulnerable packages on %s. These packages could be used by an attacker to either gain 
            access to your node, or escalate permission. It is recommended that you address this at your earliest 
            convenience.</p>
            <p>Run <code>sudo apt-get update && sudo apt-get upgrade</code> to bring your system up to date.</p>
            <p>Please note that there might be vulnerabilities detected that are yet to be fixed by the operating 
            system vendor.</p>""" % ('this node' if device_name else full_string),
            [RecommendedActions.vulnerable_packages.value, list(devices.values_list('pk', flat=True))]
        )
        actions.append(action)

    # Insecure services found action.
    devices = request.user.devices.exclude(deb_packages_hash='').filter(
        deb_packages__name__in=Device.INSECURE_SERVICES).exclude(
        snoozed_actions__contains=RecommendedActions.insecure_services.value).distinct()
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        action_header = 'Insecure services found'
        for dev in devices:
            services_str = ' '.join(dev.insecure_services.values_list('name', flat=True))
            full_string = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>'
            action_text = '<p>We found insecure services installed on %s. Because these services are ' \
                          'considered insecure, it is recommended that you uninstall them.' \
                          '</p><p>Run <code>sudo apt-get purge %s</code> to disable all insecure ' \
                          'services.</p>' % ('this node' if device_name else full_string, services_str)
            action = Action(action_header, action_text, [RecommendedActions.insecure_services.value, [dev.pk]])
            actions.append(action)

    # Insecure MongoDB, MySQL, MariaDB
    SERVICE_PORTS = {
        'mongod': (27017, 'MongoDB')
    }
    if device_pk is not None:
        processes = device.deviceinfo.processes
        found = set()
        for p in processes:
            service = p[0].get('name')
            if service not in found and service in SERVICE_PORTS:
                port = SERVICE_PORTS[service][0]
                listening = [r for r in device.portscan.scan_info if int(r['port'])==port and r['proto']=='tcp'] # TODO: host is any
                found_service = found_docker = False
                for sock in listening:
                    process = processes.get(sock.get('pid'))
                    if not process:
                        continue
                    name = process['name']
                    if name == service:
                        found_service = process
                        break
                    elif name == 'docker-proxy':
                        found_docker = process
                if (found_docker and any(p.get('container') == 'docker' and p.get('name') == service for p in process))\
                        or found_service:
                    found.add(service)
        for s in found:
            service_full_name = SERVICE_PORTS[s][1]
            action_header = f'Your {service_full_name} instance may be publicly accessible'
            service_port = SERVICE_PORTS[s]
            action_text = f'''
                <p>We have detected that a {service_full_name} instance on $HOST may be accessible remotely.
                Consider either blocking port {service_port} through the 
                WoTT firewall management tool, or re-configure {service_full_name} to only listen on localhost.</p>'''
            action = Action(actions[-1].id + 1, action_header, action_text, [])
            actions.append(action)

    # Configuration issue found action.
    devices = request.user.devices.exclude(audit_files__in=('', [])).exclude(
        snoozed_actions__contains=RecommendedActions.sshd_config_issues.value)
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        action_header = 'Insecure configuration for <strong>OpenSSH</strong> found'
        for dev in devices:
            sshd_issues = dev.sshd_issues
            if sshd_issues:
                recommendations = ''
                for issue in sshd_issues:
                    recommendations += f'<li>Change "<strong>{issue[0]}</strong>" from "<strong>{issue[1]}' \
                                       f'</strong>" to "<strong>{issue[2]}</strong>"</li>'
                recommendations = '<ul>%s</ul>' % recommendations
                full_string = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>'
                action_text = '<p>We found insecure configuration issues with OpenSSH on %s. To improve the ' \
                              'security posture of your node, please consider making the following ' \
                              'changes:%s</p>' % ('this node' if device_name else full_string, recommendations)
                action = Action(action_header, action_text, [RecommendedActions.sshd_config_issues.value, [dev.pk]])
                actions.append(action)

    # Automatic security update disabled action.
    devices = request.user.devices.filter(auto_upgrades=False).exclude(
        snoozed_actions__contains=RecommendedActions.auto_updates.value)
    if device_pk is not None:
        devices = devices.filter(pk=device_pk)
    if devices.exists():
        action_header = 'Consider enable automatic security updates'
        text_blocks = []
        for dev in devices:
            device_text_block = f'<a href="{reverse("device-detail", kwargs={"pk": dev.pk})}">{dev.get_name()}</a>'
            text_blocks.append(device_text_block)
        full_string = ', '.join(text_blocks)
        if len(text_blocks) > 1:
            full_string = f'your nodes {full_string} are'
            # Provide Debian's link if more than 1 device.
            doc_url = 'https://wiki.debian.org/UnattendedUpgrades'
        else:
            full_string = f'your node {full_string} is'
            if dev.os_release.get('distro') == 'ubuntu':
                doc_url = 'https://help.ubuntu.com/lts/serverguide/automatic-updates.html'
            else:  # Everything besides Ubuntu is Debian.
                doc_url = 'https://wiki.debian.org/UnattendedUpgrades'
        action_text = '<p>We found that %s not configured to automatically install security updates. Consider ' \
                      'enabling this feature.</p>' \
                      '<p>Details for how to do this can be found <a href="%s" target="_blank">here</a>.</p>' % \
                      ('this node is' if device_name else full_string, doc_url)
        action = Action(action_header, action_text,
                        [RecommendedActions.auto_updates.value, list(devices.values_list('pk', flat=True))])
        actions.append(action)

    return render(request, 'actions.html', {
        'actions': actions,
        'device_name': device_name,
        'device_pk': device_pk
    })
