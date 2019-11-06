import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.test import TestCase
from django.utils.http import urlencode

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from device_registry import ca_helper
from device_registry.models import DebPackage, Device, DeviceInfo, FirewallState, PortScan, average_trust_score, \
                                   GlobalPolicy, PairingKey, Vulnerability
from device_registry.forms import DeviceAttrsForm, PortsForm, ConnectionsForm, FirewallStateGlobalPolicyForm
from device_registry.forms import GlobalPolicyForm
from profile_page.models import Profile


def generate_cert(common_name=None, subject_alt_name=None):
    private_key = ec.generate_private_key(
        ec.SECP256R1(), default_backend()
    )
    builder = x509.CertificateSigningRequestBuilder()

    builder = builder.subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u'{}'.format(common_name)),
        x509.NameAttribute(NameOID.COUNTRY_NAME, u'UK'),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u'London'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u'Web of Trusted Things'),
    ]))

    if subject_alt_name:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(u'{}'.format(subject_alt_name))]
            ),
            critical=False
        )

    csr = builder.sign(private_key, hashes.SHA256(), default_backend())

    serialized_private_key = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    serialized_csr = csr.public_bytes(serialization.Encoding.PEM)

    return {
        'csr': serialized_csr.decode(),
        'key': serialized_private_key.decode()
    }


class CsrHelperTests(TestCase):

    def test_common_name_matches_san_and_device_id(self):
        """
        Test if the function returns True for when the
        device_id matches the common name and subject alt name.
        """

        device_id = 'foobar.{}'.format(settings.COMMON_NAME_PREFIX)
        cert = generate_cert(common_name=device_id, subject_alt_name=device_id)

        self.assertIs(
            ca_helper.csr_is_valid(csr=cert['csr'], device_id=device_id),
            True
        )

    def test_common_name_does_not_match_san(self):
        """
        csr_is_valid should return False when the common name
        does not match the subject alt name.
        """

        device_id = 'foobar.{}'.format(settings.COMMON_NAME_PREFIX)
        cert = generate_cert(
            common_name=device_id,
            subject_alt_name='foobar2.d.wott.local'
        )

        self.assertIs(
            ca_helper.csr_is_valid(csr=cert['csr'], device_id=device_id),
            False
        )

    def test_common_name_does_not_match_valid_domain(self):
        """
        csr_is_valid should return False when the common name
        does not match the accepted domain.
        """

        device_id = 'foobar.com'
        cert = generate_cert(
            common_name=device_id,
            subject_alt_name=device_id
        )

        self.assertIs(
            ca_helper.csr_is_valid(csr=cert['csr'], device_id=device_id),
            False
        )


OPEN_PORTS_INFO = [{"host": "192.168.1.178", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4}]

OPEN_CONNECTIONS_INFO = [
    {'ip_version': 4, 'type': 'tcp', 'local_address': ['192.168.1.178', 4567],
     'remote_address': ['192.168.1.177', 5678], 'status': 'open', 'pid': 3425}
]

TEST_CERT = """-----BEGIN CERTIFICATE-----
MIIC5TCCAc2gAwIBAgIJAPMjGMrzQcI/MA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNV
BAMMCWxvY2FsaG9zdDAeFw0xOTAzMDUyMDE5MjRaFw0xOTA0MDQyMDE5MjRaMBQx
EjAQBgNVBAMMCWxvY2FsaG9zdDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoC
ggEBAOgfhzltW1Bx/PLve7sk228G9FeBQmTVkEwiU1tgagvIzM8fhoeDnXoMVRf5
GPWZr4h0E4BtDRQUO7NqgW+r3RQMq4nJljTV9f8Om3Owx41BM5M5w5YH75JZzcZ1
OVBmJRPOG06I3Hk/uQjCGo1YN7ZggAdUmFQqQ03GdstqQhd6UzbV2dPphq+R2npV
oAjByawBwuxi+NJXxz20dUVkXrrxGgDUKcUn4NPsIUGf9hSHZcDMZ3XQcQQ/ykD9
i/zeVU6jGnsMOO+YZUguBlq/GKI2fzezfG7fv394oAJP9mV0T8k9ArciTigUehuv
a8sHA+vrvRXCNbpV8vEQbRh/+0sCAwEAAaM6MDgwFAYDVR0RBA0wC4IJbG9jYWxo
b3N0MAsGA1UdDwQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDATANBgkqhkiG9w0B
AQsFAAOCAQEAL+KRDdqbbAFiMROy7eNkbMUj3Dp4S24y5QnGjFl4eSFLWu9UhBT+
FcElSbo1vKaW5DJi+XG9snyZfqEuknQlBEDTuBlOEqguGpmzYE/+T0wt9zLTByN8
N44fGr4f9ORj6Y6HJkzdlp+XCDdzHb2+3ienNle6bWlmBpbQaMVrayDxJ5yxldgJ
czUUClEc0OJDMw8PsHyYvrl+jk0JFXgDqBgAutPzSiC+pWL3H/5DO8t/NcccNNlR
2UZyh8r3qmVWo1jROR98z/J59ytNgMfYTmVI+ClUWKF5OWEOneKTf7dvic0Bqiyb
1lti7kgwF5QeRU2eEn3VC2F5JreBMpTkeA==
-----END CERTIFICATE-----
"""


class DeviceModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user0 = User.objects.create_user('test')
        self.user1 = User.objects.create_user('test-no-device')
        week_ago = timezone.now() - timezone.timedelta(days=7)
        hour_ago = timezone.now() - timezone.timedelta(hours=1)
        self.device0 = Device.objects.create(
            device_id='device0.d.wott-dev.local',
            last_ping=week_ago,
            owner=self.user1,
            certificate=TEST_CERT
        )
        self.device1 = Device.objects.create(
            device_id='device1.d.wott-dev.local',
            last_ping=hour_ago,
            owner=self.user1
        )
        self.device2 = Device.objects.create(
            device_id='device2.d.wott-dev.local',
            last_ping=hour_ago,
            owner=self.user0
        )
        self.device3 = Device.objects.create(
            device_id='device3.d.wott-dev.local',
            last_ping=hour_ago,
            owner=self.user0
        )

        self.device_info0 = DeviceInfo.objects.create(
            device=self.device0,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
            selinux_state={'enabled': True, 'mode': 'enforcing'},
            app_armor_enabled=True,
            logins={'pi': {'failed': 1, 'success': 1}}
        )
        self.device_info1 = DeviceInfo.objects.create(
            device=self.device1,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
            selinux_state={'enabled': True, 'mode': 'enforcing'},
            app_armor_enabled=True,
            logins={'pi': {'failed': 1, 'success': 1}}
        )

        portscan0 = [
            {"host": "192.168.1.178", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "192.168.1.178", "port": 25, "proto": "tcp", "state": "open", "ip_version": 4}
        ]
        portscan1 = [
            {"host": "192.168.1.178", "port": 80, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "192.168.1.178", "port": 110, "proto": "tcp", "state": "open", "ip_version": 4}
        ]
        self.portscan0 = PortScan.objects.create(device=self.device0, scan_info=portscan0)
        self.portscan1 = PortScan.objects.create(device=self.device1, scan_info=portscan1)

        self.firewall0 = FirewallState.objects.create(device=self.device0, policy=FirewallState.POLICY_ENABLED_BLOCK)
        self.firewall1 = FirewallState.objects.create(device=self.device1, policy=FirewallState.POLICY_ENABLED_BLOCK)

        self.user4 = User.objects.create_user('test-fixing-issues')
        self.device4 = Device.objects.create(
            device_id='device4.d.wott-dev.local',
            last_ping=hour_ago,
            owner=self.user4
        )
        self.device_info4 = DeviceInfo.objects.create(
            device=self.device4,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
            selinux_state={'enabled': False},
            app_armor_enabled=False,
            default_password=True,
            logins={'pi': {'failed': 1, 'success': 1}}
        )
        PortScan.objects.create(device=self.device4, scan_info=[
            {"host": "0.0.0.0", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "::", "port": 22, "proto": "tcp", "state": "open", "ip_version": 6},
            {"host": "0.0.0.0", "port": 80, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "::", "port": 80, "proto": "tcp", "state": "open", "ip_version": 6},
        ])
        self.firewall4 = FirewallState.objects.create(device=self.device4, policy=FirewallState.POLICY_ENABLED_ALLOW)

    def test_fixed_issues(self):
        self.device4.update_trust_score_now()
        # initial state: firewall disabled, default password found - trust score low
        self.assertLess(self.device4.trust_score_percent(), 66)
        self.firewall4.policy = FirewallState.POLICY_ENABLED_BLOCK
        self.firewall4.save()
        self.device_info4.default_password = False
        self.device_info4.save()
        self.device4.update_trust_score_now()

        # result: trust score high
        self.assertGreaterEqual(self.device4.trust_score_percent(), 66)

    def test_get_model(self):
        model = self.device_info0.device_model
        self.device_info0.device_model = 'Model B Rev 2'
        self.assertEqual(self.device_info0.get_model(), 'Model B Rev 2')
        self.device_info0.device_model = model

    def test_get_hardware_type(self):
        hw_type = self.device_info0.get_hardware_type()
        self.assertEqual(hw_type, 'Raspberry Pi')

    def test_active_inactive(self):
        active_inactive = Device.get_active_inactive(self.user0)
        self.assertListEqual(active_inactive, [2, 0])

    def test_bad_ports_score(self):
        ps = self.device0.portscan
        assert ps
        score0 = self.portscan0.get_score()
        score1 = self.portscan1.get_score()
        self.assertEqual(score0, 0.6)
        self.assertEqual(score1, 0.7)

    def test_empty_average_trust_score(self):
        user = self.user0
        avg_score = average_trust_score(user)
        self.assertIsNone(avg_score)

    def test_trust_score(self):
        self.device0.update_trust_score_now()
        self.device1.update_trust_score_now()
        all_good_except_port_score = sum(Device.COEFFICIENTS.values()) - Device.COEFFICIENTS['port_score']
        self.assertEqual(self.device0.trust_score,
                         (all_good_except_port_score + 0.6 * Device.COEFFICIENTS['port_score']) /
                         sum(Device.COEFFICIENTS.values()))
        self.assertEqual(self.device1.trust_score,
                         (all_good_except_port_score + 0.7 * Device.COEFFICIENTS['port_score']) /
                         sum(Device.COEFFICIENTS.values()))

    def test_average_trust_score(self):
        self.device0.update_trust_score_now()
        self.device1.update_trust_score_now()
        score = average_trust_score(self.user1)
        self.assertEqual(score, ((self.device0.trust_score + self.device1.trust_score) / 2.0))

    def test_cpu_vulnerable(self):
        self.assertIsNone(self.device0.cpu_vulnerable)

        pkg = DebPackage.objects.create(os_release_codename='buster', name='linux', version='5.0.0',
                                        source_name='linux', source_version='5.0.0', arch=DebPackage.Arch.i386)
        pkg.save()
        self.device0.kernel_deb_package = pkg

        self.device0.cpu = {'vendor': 'GenuineIntel', 'vulnerable': True}
        self.device0.save()
        self.assertTrue(self.device0.cpu_vulnerable)

        self.device0.cpu = {'vendor': 'GenuineIntel', 'vulnerable': False}
        self.device0.save()
        self.assertFalse(self.device0.cpu_vulnerable)

        self.device0.cpu = {'vendor': 'GenuineIntel', 'vulnerable': None, 'mitigations_disabled': True}
        self.device0.save()
        self.assertTrue(self.device0.cpu_vulnerable)

        vuln = Vulnerability.objects.create(os_release_codename='buster', name='CVE-2017-5753', package='linux',
                                            other_versions=[], is_binary=False, urgency=Vulnerability.Urgency.HIGH,
                                            fix_available=True)
        pkg.vulnerabilities.add(vuln)
        pkg.save()
        self.device0.cpu = {'vendor': 'GenuineIntel', 'vulnerable': None, 'mitigations_disabled': False}
        self.device0.save()
        self.assertTrue(self.device0.cpu_vulnerable)

        self.device0.cpu = {'vendor': 'AuthenticAMD'}
        self.device0.save()
        self.assertFalse(self.device0.cpu_vulnerable)


class FormsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.device = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user)
        self.device_info = DeviceInfo.objects.create(
            device=self.device,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
        )
        self.portscan = PortScan.objects.create(device=self.device, scan_info=OPEN_PORTS_INFO,
                                                netstat=OPEN_CONNECTIONS_INFO)
        self.firewallstate = FirewallState.objects.create(device=self.device)

    def test_device_metadata_form(self):
        form_data = {'device_metadata': {"test": "value"}}
        form = DeviceAttrsForm(data=form_data, instance=self.device)
        self.assertTrue(form.is_valid())

    def test_device_attrs_form(self):
        form_data = {'comment': 'Test comment', 'name': 'My device 1'}
        form = DeviceAttrsForm(data=form_data, instance=self.device)
        self.assertTrue(form.is_valid())

    def test_ports_form(self):
        ports_form_data = self.portscan.ports_form_data()
        form_data = {'is_ports_form': 'true', 'open_ports': ['0'], 'policy': self.firewallstate.policy}
        form = PortsForm(data=form_data, ports_choices=ports_form_data[0])
        self.assertTrue(form.is_valid())

    def test_networks_form(self):
        connections_form_data = self.portscan.connections_form_data()
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        form = ConnectionsForm(data=form_data, open_connections_choices=connections_form_data[0])
        self.assertTrue(form.is_valid())

    def test_global_policy_form(self):
        gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)
        form_data = {'global_policy': str(gp.pk)}
        form = FirewallStateGlobalPolicyForm(data=form_data, instance=self.firewallstate)
        self.assertTrue(form.is_valid())


class DeviceDetailViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.user.set_password('123')
        self.user.save()
        self.user2 = User.objects.create_user('user')
        self.device = Device.objects.create(
            device_id='device0.d.wott-dev.local', owner=self.user, certificate=TEST_CERT,
            cpu={'vulnerable': True, 'vendor': 'GenuineIntel'},
            certificate_expires=timezone.datetime(2019, 7, 4, 13, 55, tzinfo=timezone.utc))
        self.deviceinfo = DeviceInfo.objects.create(
            device=self.device,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
            selinux_state={'enabled': True, 'mode': 'enforcing'},
            app_armor_enabled=True,
            logins={'pi': {'failed': 1, 'success': 1}}
        )
        self.portscan = PortScan.objects.create(device=self.device, scan_info=OPEN_PORTS_INFO,
                                                netstat=OPEN_CONNECTIONS_INFO)
        self.firewall = FirewallState.objects.create(device=self.device, policy=FirewallState.POLICY_ENABLED_BLOCK)
        self.url = reverse('device-detail', kwargs={'pk': self.device.pk})
        self.url2 = reverse('device-detail-security', kwargs={'pk': self.device.pk})
        self.url3 = reverse('device-detail-metadata', kwargs={'pk': self.device.pk})

        self.device_no_portscan = Device.objects.create(device_id='device1.d.wott-dev.local', owner=self.user,
                                                        certificate=TEST_CERT)
        self.firewall2 = FirewallState.objects.create(device=self.device_no_portscan)

        self.device_no_firewall = Device.objects.create(device_id='device2.d.wott-dev.local', owner=self.user,
                                                        certificate=TEST_CERT)
        self.portscan2 = PortScan.objects.create(device=self.device_no_firewall, scan_info=OPEN_PORTS_INFO,
                                                 netstat=OPEN_CONNECTIONS_INFO)

        self.device_no_logins = Device.objects.create(
            device_id='device3.d.wott-dev.local', owner=self.user, certificate=TEST_CERT,
            certificate_expires=timezone.datetime(2019, 7, 4, 13, 55, tzinfo=timezone.utc))
        self.deviceinfo3 = DeviceInfo.objects.create(
            device=self.device_no_logins,
            device_manufacturer='Raspberry Pi',
            device_model='900092',
            selinux_state={'enabled': True, 'mode': 'enforcing'},
            app_armor_enabled=True,
            logins={},
            default_password=True
        )
        self.portscan3 = PortScan.objects.create(device=self.device_no_logins, scan_info=OPEN_PORTS_INFO,
                                                 netstat=OPEN_CONNECTIONS_INFO)
        self.firewall3 = FirewallState.objects.create(device=self.device_no_logins)
        self.gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)

    def test_device_detail_not_logged_in(self):
        url = reverse('device-detail', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/')

    def test_device_detail_security_not_logged_in(self):
        response = self.client.get(self.url2)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/security/')

    def test_device_detail_network_not_logged_in(self):
        url = reverse('device-detail-network', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/network/')

    def test_device_detail_hardware_not_logged_in(self):
        url = reverse('device-detail-hardware', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/hardware/')

    def test_credentials_not_logged_in(self):
        url = reverse('credentials')
        response = self.client.get(url)
        self.assertRedirects(response, '/accounts/login/?next=/credentials/')

    def test_get(self):
        """
        If no questions exist, an appropriate message is displayed.
        """
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Node Profile')
        self.assertEqual(self.device.actions_count, 0)
        self.assertNotContains(response, 'Show recommended actions')

    def test_actions_btn_pos(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail', kwargs={'pk': self.device_no_logins.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(self.device_no_logins.actions_count, 0)
        self.assertContains(response, 'Recommended Actions')

    def test_no_portscan(self):
        """
        Neither Hardware nor Security tabs should be rendered if Device object
        has no PortScan.
        """
        url = reverse('device-detail', kwargs={'pk': self.device_no_portscan.pk})
        self.client.login(username='test', password='123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Node Profile')
        self.assertNotContains(response, '<a id="tab-security"')
        self.assertNotContains(response, '<a id="tab-hardware"')

    def test_no_firewall(self):
        """
        Security tab should not be rendered if Device object has no FirewallState.
        """
        url = reverse('device-detail', kwargs={'pk': self.device_no_firewall.pk})
        self.client.login(username='test', password='123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Node Profile')
        self.assertContains(response, '<a id="tab-hardware"')
        self.assertNotContains(response, '<a id="tab-security"')

    def test_device_metadata(self):
        self.client.login(username='test', password='123')
        form_data = {'device_metadata': '{"test": "value"}'}
        self.client.post(self.url3, form_data)
        response = self.client.get(self.url3)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.context_data["device"].deviceinfo.device_metadata, {"test": "value"})

    def test_comment(self):
        self.client.login(username='test', password='123')
        form_data = {'comment': 'Test comment'}
        self.client.post(self.url, form_data)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test comment')

    def test_device_name(self):
        self.client.login(username='test', password='123')
        form_data = {'name': 'My device 1'}
        self.client.post(self.url, form_data)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My device 1')

    def test_open_ports(self):
        self.client.login(username='test', password='123')
        form_data = {'is_ports_form': 'true', 'open_ports': ['0'], 'policy': self.firewall.policy}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_ports, [['192.168.1.178', 'tcp', 22, False]])
        response = self.client.get(self.url2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Firewall Ports Policy')
        self.assertInHTML('<span id="ports-table-column-1">Allowed</span>', response.rendered_content)

    def test_open_ports_global_policy(self):
        self.client.login(username='test', password='123')
        form_data = {'is_ports_form': 'true', 'open_ports': ['0'], 'policy': self.firewall.policy}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_ports, [['192.168.1.178', 'tcp', 22, False]])
        self.firewall.global_policy = self.gp
        self.firewall.save(update_fields=['global_policy'])
        response = self.client.get(self.url2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open Ports')
        self.assertNotContains(response, '<th scope="col" width="5%"><span\n                                      '
                                         'id="ports-table-column-1">Allowed</span></th>')

    def test_open_ports_forbidden(self):
        self.client.login(username='test', password='123')
        self.firewall.global_policy = self.gp
        self.firewall.save(update_fields=['global_policy'])
        form_data = {'is_ports_form': 'true', 'open_ports': ['0'], 'policy': self.firewall.policy}
        response = self.client.post(self.url2, form_data)
        self.assertEqual(response.status_code, 403)

    def test_open_connections(self):
        self.client.login(username='test', password='123')
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_networks, [['192.168.1.177', False]])
        response = self.client.get(self.url2)
        self.assertEqual(response.status_code, 200)
        self.assertInHTML('<input type="checkbox" value="0" id="connections-check-all">Blocked',
                          response.rendered_content)

    def test_open_connections_global_policy(self):
        self.client.login(username='test', password='123')
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_networks, [['192.168.1.177', False]])
        self.firewall.global_policy = self.gp
        self.firewall.save(update_fields=['global_policy'])
        response = self.client.get(self.url2)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<th scope="col" width="5%">Blocked</th>')

    def test_open_connections_forbidden(self):
        self.client.login(username='test', password='123')
        self.firewall.global_policy = self.gp
        self.firewall.save(update_fields=['global_policy'])
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        response = self.client.post(self.url2, form_data)
        self.assertEqual(response.status_code, 403)

    def test_no_logins(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device_no_logins.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No recent login attempts detected')

    def test_logins(self):
        self.client.login(username='test', password='123')
        response = self.client.get(self.url2)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<pre>pi:')
        self.assertContains(response, 'success: 1')

    def test_insecure_services(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '>telnetd<')
        self.assertNotContains(response, '>fingerd<')
        self.assertNotContains(response, 'No insecure services detected')

        self.device.set_deb_packages([
            {'name': 'python2', 'version': 'VERSION', 'source_name': 'python2', 'source_version': 'abcd',
             'arch': 'i386', 'os_release_codename': 'jessie'},
            {'name': 'python3', 'version': 'VERSION', 'source_name': 'python3', 'source_version': 'abcd',
             'arch': 'i386', 'os_release_codename': 'jessie'}
        ], {'codename': 'jessie'})
        self.device.deb_packages_hash = 'abcdef'
        self.device.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '>telnetd<')
        self.assertNotContains(response, '>fingerd<')
        self.assertContains(response, 'No insecure services detected')
        self.assertListEqual(list(self.device.deb_packages.values('name', 'version', 'arch', 'os_release_codename')),
                             [{'name': 'python2', 'version': 'VERSION', 'arch': 'i386',
                               'os_release_codename': 'jessie'},
                              {'name': 'python3', 'version': 'VERSION', 'arch': 'i386',
                               'os_release_codename': 'jessie'}])

        self.device.set_deb_packages([
            {'name': 'telnetd', 'version': 'VERSION', 'source_name': 'telnetd', 'source_version': 'abcd',
             'arch': 'i386', 'os_release_codename': 'jessie'},
            {'name': 'fingerd', 'version': 'VERSION', 'source_name': 'fingerd', 'source_version': 'abcd',
             'arch': 'i386', 'os_release_codename': 'jessie'}
        ], {'codename': 'jessie'})
        self.device.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'telnetd</li>')
        self.assertContains(response, 'fingerd</li>')
        self.assertNotContains(response, 'No insecure services detected')
        self.assertListEqual(list(self.device.deb_packages.values('name', 'version', 'arch', 'os_release_codename')),
                             [{'name': 'telnetd', 'version': 'VERSION', 'arch': 'i386',
                               'os_release_codename': 'jessie'},
                              {'name': 'fingerd', 'version': 'VERSION', 'arch': 'i386',
                               'os_release_codename': 'jessie'}])

    def test_vulnerable_packages_render(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})

        # No packages - should render N/A
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertInHTML('''
            <th scope="row">
                Vulnerable Packages
            </th>
            <td>
                N/A
            </td>''', response.rendered_content)

        self.device.deb_packages_hash = 'aabbccdd'
        self.device.save()
        self.device.set_deb_packages([
            {'name': 'python2', 'version': 'VERSION', 'source_name': 'python2', 'source_version': 'abcd',
             'arch': 'i386'},
            {'name': 'python3', 'version': 'VERSION', 'source_name': 'python3', 'source_version': 'abcd',
             'arch': 'i386'}
        ], os_info={'codename': 'stretch'})
        # No vulnerable packages - green check mark
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertInHTML('''
            <th scope="row">
                Vulnerable Packages
            </th>
            <td>
                <span class="p-1 text-success">
                    <i class="fas fa-check" ></i>
                </span>
            </td>
                ''', response.rendered_content)

        v = Vulnerability.objects.create(name='CVE-123', package='python2', is_binary=False, other_versions=[],
                                         urgency=Vulnerability.Urgency.NONE, fix_available=True)
        self.device.deb_packages.get(name='python2').vulnerabilities.add(v)

        # Has vulnerable packages - should render them
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'python2')
        self.assertContains(response, 'CVE-123')

    def test_cpu_vulnerable_render(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})

        response = self.client.get(url)
        self.assertContains(response, 'Patched against Meltdown/Spectre')

        self.device.cpu['vendor'] = 'AuthenticAMD'
        self.device.save()
        response = self.client.get(url)
        self.assertNotContains(response, 'Patched against Meltdown/Spectre')

    def test_global_policies_list(self):
        gp2 = GlobalPolicy.objects.create(name='gp2', owner=self.user2, policy=GlobalPolicy.POLICY_ALLOW)
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Current user's global policy is available as an option.
        self.assertContains(response, '<option value="%d">%s</option>' % (self.gp.pk, self.gp.name))
        # Other user's global policy is not available as an option.
        self.assertNotContains(response, '<option value="%d">%s</option>' % (gp2.pk, gp2.name))

    def test_device_detail_software_not_logged_in(self):
        url = reverse('device-detail-software', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/software/')

    @patch('django.utils.timezone.now')
    def test_get_device_detail_software(self, mock_timezone):
        mock_timezone.return_value = timezone.datetime(2019, 11, 5, tzinfo=timezone.utc)
        self.client.login(username='test', password='123')
        url = reverse('device-detail-software', kwargs={'pk': self.device.pk})
        # Unknown distro.
        response = self.client.get(url)
        self.assertInHTML('<td id="eol_info">N/A</td>', response.rendered_content)
        # Supported distro version.
        self.device.os_release = {'distro': 'raspbian', 'version': '10', 'codename': 'buster',
                                  'distro_root': 'debian', 'full_version': '10 (buster)'}
        self.device.save(update_fields=['os_release'])
        response = self.client.get(url)
        # print(response.content)
        self.assertInHTML('<td id="eol_info">July 1, 2022</td>', response.rendered_content)
        # Outdated distro version.
        self.device.os_release = {'distro': 'debian', 'version': '7', 'codename': 'wheezy',
                                  'distro_root': 'debian', 'full_version': '7 (wheezy)'}
        self.device.save(update_fields=['os_release'])
        response = self.client.get(url)
        self.assertInHTML('<td id="eol_info"><span class="p-1 text-danger"><i class="fas fa-exclamation-circle" >'
                          '</i></span>May 31, 2018</td>', response.rendered_content)


class PairingKeysView(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.url = reverse('pairing-keys')
        self.pairing_key = PairingKey.objects.create(owner=self.user)

    def test_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/pairing-keys/')

    def test_get(self):
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pairing Keys')

    def test_get_file(self):
        self.client.login(username='test', password='123')
        url = f'/pairing-keys/download?pk={self.pairing_key.pk}'
        data = f'[DEFAULT]\n\nenroll_token = {self.pairing_key.key.hex}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), data)


class RootViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.user.set_password('123')
        self.user.save()
        Profile.objects.create(user=self.user)

        self.device0 = Device.objects.create(
            device_id='device0.d.wott-dev.local',
            owner=self.user,
            certificate=TEST_CERT,
            name='First',
            last_ping=timezone.now() - timezone.timedelta(days=1, hours=1)
        )
        self.deviceinfo0 = DeviceInfo.objects.create(
            device=self.device0,
            fqdn='FirstFqdn',
            default_password=False,
            detected_mirai=True,
        )

        self.device1 = Device.objects.create(
            device_id='device1.d.wott-dev.local',
            owner=self.user,
            certificate=TEST_CERT,
            last_ping=timezone.now() - timezone.timedelta(days=2, hours=23)
        )
        self.deviceinfo1 = DeviceInfo.objects.create(
            device=self.device1,
            fqdn='SecondFqdn',
            default_password=True,
            detected_mirai=True,
        )
        PortScan.objects.create(device=self.device0)
        PortScan.objects.create(device=self.device1)

    def test_wizard(self):
        self.client.login(username='test', password='123')
        response = self.client.get(reverse('root'))
        self.assertContains(response, 'tour.start();')
        response = self.client.post(reverse('wizard-complete'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('root'))
        self.assertNotContains(response, 'tour.start();')

    def test_no_filter(self):
        self.client.login(username='test', password='123')
        url = reverse('root')
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0, self.device1])

    def test_filter_date(self):
        self.client.login(username='test', password='123')

        url = reverse('root') + '?' + urlencode({
            'filter_by': 'last-ping',
            'filter_predicate': 'eq',
            'filter_value': '1,days'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0])

        url = reverse('root') + '?' + urlencode({
            'filter_by': 'last-ping',
            'filter_predicate': 'eq',
            'filter_value': '2,days'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device1])

        url = reverse('root') + '?' + urlencode({
            'filter_by': 'last-ping',
            'filter_predicate': 'lt',
            'filter_value': '1,days'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0, self.device1])

        url = reverse('root') + '?' + urlencode({
            'filter_by': 'last-ping',
            'filter_predicate': 'gt',
            'filter_value': '1,days'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [])

    def test_filter_name(self):
        self.client.login(username='test', password='123')

        # Context-insensitive filter by node name set in device.name (exact match)
        url = reverse('root') + '?' + urlencode({
            'filter_by': 'device-name',
            'filter_predicate': 'eq',
            'filter_value': 'first'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0])

        # Context-insensitive filter by node name set in deviceinfo.fqdn (exact match)
        url = reverse('root') + '?' + urlencode({
            'filter_by': 'device-name',
            'filter_predicate': 'eq',
            'filter_value': 'firstfqdn'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0])

        # Context-insensitive filter by node name set in device.name (not match)
        url = reverse('root') + '?' + urlencode({
            'filter_by': 'device-name',
            'filter_predicate': 'neq',
            'filter_value': 'first'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device1])

        # Context-insensitive filter by node name set in device.name (contains)
        url = reverse('root') + '?' + urlencode({
            'filter_by': 'device-name',
            'filter_predicate': 'c',
            'filter_value': 'fir'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device0])

        # Context-insensitive filter by node name set in device.name (not contains)
        url = reverse('root') + '?' + urlencode({
            'filter_by': 'device-name',
            'filter_predicate': 'nc',
            'filter_value': 'fir'
        })
        response = self.client.get(url)
        self.assertListEqual(list(response.context['object_list']), [self.device1])

    def test_recommended_actions_count(self):
        self.client.login(username='test', password='123')
        response = self.client.get(reverse('root'))
        self.assertEqual(response.status_code, 200)
        self.assertInHTML('<a class="sidebar-link" id="sidebar-actions" href="/actions/">Recommended Actions<span '
                          'class="badge badge-pill badge-danger ml-2">2</span></a>', response.rendered_content)


class SaveDeviceSettingsAsPolicyViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.device = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user)
        self.portscan = PortScan.objects.create(device=self.device, scan_info=OPEN_PORTS_INFO,
                                                netstat=OPEN_CONNECTIONS_INFO)
        self.firewallstate = FirewallState.objects.create(device=self.device)
        self.url = reverse('save_as_policy', kwargs={'pk': self.device.pk})

    def test_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next=/devices/{self.device.pk}/security/save-as-policy/')

    def test_get(self):
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        # TODO: check page content.

    def test_get_forbidden(self):
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        self.client.login(username='test', password='123')
        gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        self.firewallstate.global_policy = gp
        self.firewallstate.save(update_fields=['global_policy'])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(GlobalPolicy.objects.count(), 1)


class GlobalPolicyDeleteViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)
        self.url = reverse('delete_global_policy', kwargs={'pk': self.gp.pk})

    def test_not_logged_in(self):
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        response = self.client.post(self.url)
        self.assertRedirects(response, f'/accounts/login/?next=/policies/{self.gp.pk}/delete/')
        self.assertEqual(GlobalPolicy.objects.count(), 1)

    def test_post(self):
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        self.client.login(username='test', password='123')
        response = self.client.post(self.url)
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        self.assertRedirects(response, '/policies/')


class GlobalPolicyEditViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)
        self.url = reverse('edit_global_policy', kwargs={'pk': self.gp.pk})

    def test_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/accounts/login/?next=/policies/{self.gp.pk}/')

    def test_get(self):
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div class="form-group"><label for="id_name">Name</label><input type="text" '
                                      'name="name" value="gp1" maxlength="32" class="form-control" placeholder="Name" '
                                      'title="" required id="id_name"></div>')
        self.assertContains(response, '<option value="1" selected>Allow by default</option>')
        self.assertContains(response, '<div class="form-group"><label for="id_ports">Ports</label><textarea '
                                      'name="ports" cols="40" rows="10" class="form-control" placeholder="Ports" '
                                      'title="" id="id_ports">\n[]</textarea></div>')

    def test_post(self):
        self.client.login(username='test', password='123')
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK)}
        response = self.client.post(self.url, form_data)
        self.assertRedirects(response, '/policies/')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div class="form-group"><label for="id_name">Name</label><input type="text" '
                                      'name="name" value="My policy" maxlength="32" class="form-control" '
                                      'placeholder="Name" title="" required id="id_name"></div>')
        self.assertContains(response, '<option value="2" selected>Block by default</option>')

    def test_post_non_unique_name(self):
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        GlobalPolicy.objects.create(owner=self.user, name='Policy 1', policy=GlobalPolicy.POLICY_ALLOW)
        self.assertEqual(GlobalPolicy.objects.count(), 2)
        self.client.login(username='test', password='123')
        form_data = {'name': 'Policy 1', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(None)}
        response = self.client.post(self.url, form_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Global policy with this name already exists.')
        self.assertEqual(GlobalPolicy.objects.count(), 2)


class GlobalPolicyCreateViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.url = reverse('create_global_policy')

    def test_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/policies/add/')

    def test_get(self):
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_post(self):
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        self.client.login(username='test', password='123')
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK)}
        response = self.client.post(self.url, form_data)
        self.assertRedirects(response, '/policies/')
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        gp = GlobalPolicy.objects.all()[0]
        response = self.client.get(reverse('edit_global_policy', kwargs={'pk': gp.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div class="form-group"><label for="id_name">Name</label><input type="text" '
                                      'name="name" value="My policy" maxlength="32" class="form-control" '
                                      'placeholder="Name" title="" required id="id_name"></div>')
        self.assertContains(response, '<option value="2" selected>Block by default</option>')

    def test_post_non_unique_name(self):
        self.assertEqual(GlobalPolicy.objects.count(), 0)
        GlobalPolicy.objects.create(owner=self.user, name='Policy 1', policy=GlobalPolicy.POLICY_ALLOW)
        self.assertEqual(GlobalPolicy.objects.count(), 1)
        self.client.login(username='test', password='123')
        form_data = {'name': 'Policy 1', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(None)}
        response = self.client.post(self.url, form_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Global policy with this name already exists.')
        self.assertEqual(GlobalPolicy.objects.count(), 1)


class GlobalPoliciesListViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='test', password='123')
        self.url = reverse('global_policies')

    def test_not_logged_in(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, '/accounts/login/?next=/policies/')

    def test_get(self):
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<h5 class="card-title">Policies</h5>')


class GlobalPolicyFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.gp = GlobalPolicy.objects.create(name='gp1', owner=self.user, policy=GlobalPolicy.POLICY_ALLOW)

    def test_success(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False},
                      {'address': '2002:c0a8:101::', 'protocol': 'udp', 'port': 34, 'ip_version': True}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_wrong_key(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False},
                      {'address': '0.0.0.1', 'xxx': 'yyy', 'protocol': 'udp', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['Wrong or missing fields.']})

    def test_missing_key(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False},
                      {'address': '0.0.0.1', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['Wrong or missing fields.']})

    def test_duplicated_rule(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False},
                      {'address': '0.0.0.1', 'protocol': 'udp', 'port': 34, 'ip_version': False},
                      {'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"0.0.0.0:34/udp" is a duplicating/conflicting rule.']})

    def test_wrong_address(self):
        ports_data = [{'address': '0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"0.0.0" is not a correct IP address.']})

    def test_wrong_protocol(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'xxx', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"xxx" is not a valid protocol value.']})

    def test_wrong_port_type(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': '34', 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"34" is not a valid port value.']})

    def test_wrong_port_value(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': -34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"-34" is not a valid port value.']})

    def test_wrong_ip_version(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': 'false'}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"false" is not a valid IP version field value.']})

    def test_wrong_ipv6_address(self):
        ports_data = [{'address': '0.0.0.0', 'protocol': 'udp', 'port': 34, 'ip_version': True}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"0.0.0.0" is wrong IP address format for IPv6.']})

    def test_wrong_ipv4_address(self):
        ports_data = [{'address': '2002:c0a8:101::', 'protocol': 'udp', 'port': 34, 'ip_version': False}]
        form_data = {'name': 'My policy', 'policy': str(GlobalPolicy.POLICY_BLOCK), 'ports': json.dumps(ports_data)}
        form = GlobalPolicyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertDictEqual(form.errors, {'ports': ['"2002:c0a8:101::" is wrong IP address format for IPv4.']})
