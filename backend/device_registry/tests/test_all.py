import datetime
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.test import TestCase

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from device_registry import ca_helper
from device_registry.api_views import mtls_ping_view
from device_registry.models import Device, DeviceInfo, FirewallState, PortScan, average_trust_score, Credential
from device_registry.forms import DeviceAttrsForm, PortsForm, ConnectionsForm


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


TEST_RULES = {'INPUT': [{'src': '15.15.15.50/32', 'target': 'DROP'}, {'src': '15.15.15.51/32', 'target': 'DROP'}],
              'OUTPUT': [], 'FORWARD': []}

OPEN_PORTS_INFO = [{"host": "192.168.1.178", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4}]
OPEN_PORTS_INFO_TELNET = [{"host": "192.168.1.178", "port": 23, "proto": "tcp", "state": "open", "ip_version": 4}]

OPEN_CONNECTIONS_INFO = [
    {'ip_version': 4, 'type': 'tcp', 'local_address': ['192.168.1.178', 4567],
     'remote_address': ['192.168.1.177', 5678], 'status': 'open', 'pid': 3425}
]


class APIPingTest(TestCase):
    def setUp(self):
        self.api = APIRequestFactory()
        self.device0 = Device.objects.create(device_id='device0.d.wott-dev.local')
        self.ping_payload = {
            'device_operating_system_version': 'linux',
            'fqdn': 'test-device0',
            'ipv4_address': '127.0.0.1',
            'uptime': '0',
            'distr_id': 'Raspbian',
            'distr_release': '9.4',
            'scan_info': OPEN_PORTS_INFO,
            'netstat': OPEN_CONNECTIONS_INFO,
            'firewall_enabled': True,
            'firewall_rules': TEST_RULES
        }
        self.ping_headers = {
            'HTTP_SSL_CLIENT_SUBJECT_DN': 'CN=device0.d.wott-dev.local',
            'HTTP_SSL_CLIENT_VERIFY': 'SUCCESS'
        }

    def test_ping_endpoint(self):
        request = self.api.get(
            '/v0.2/ping/',
            **self.ping_headers,
            format='json'
        )
        response = mtls_ping_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.data, {'block_ports': [], 'block_networks': settings.SPAM_NETWORKS})

    def test_pong_data(self):
        # 1st request
        request = self.api.get(
            '/v0.2/ping/',
            **self.ping_headers,
            format='json'
        )
        response = mtls_ping_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.data, {'block_ports': [], 'block_networks': settings.SPAM_NETWORKS})
        # 2nd request
        self.device0.portscan.block_ports = [['192.168.1.178', 'tcp', 22, False]]
        self.device0.portscan.block_networks = [['192.168.1.177', False]]
        self.device0.portscan.save(update_fields=['block_ports', 'block_networks'])
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        response = mtls_ping_view(request)
        self.assertEqual(response.status_code, 200)

        request = self.api.get(
            '/v0.2/ping/',
            **self.ping_headers,
            format='json'
        )
        response = mtls_ping_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.data, {'block_ports': [['192.168.1.178', 'tcp', 22, False]],
                                             'block_networks': [['192.168.1.177', False]] + settings.SPAM_NETWORKS})

    def test_ping_creates_models(self):
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        devinfo_obj_count_before = DeviceInfo.objects.count()
        portscan_obj_count_before = PortScan.objects.count()
        mtls_ping_view(request)
        devinfo_obj_count_after = DeviceInfo.objects.count()
        portscan_obj_count_after = PortScan.objects.count()
        self.assertEqual(devinfo_obj_count_before, 0)
        self.assertEqual(portscan_obj_count_before, 0)
        self.assertEqual(devinfo_obj_count_after, 1)
        self.assertEqual(portscan_obj_count_after, 1)

    def test_ping_writes_scan_info(self):
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        portscan = PortScan.objects.get(device=self.device0)
        scan_info = portscan.scan_info
        self.assertListEqual(scan_info, OPEN_PORTS_INFO)

    def test_ping_writes_netstat(self):
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        portscan = PortScan.objects.get(device=self.device0)
        netstat = portscan.netstat
        self.assertListEqual(netstat, OPEN_CONNECTIONS_INFO)

    def test_ping_distr_info(self):
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        self.assertEqual(self.device0.deviceinfo.distr_id, 'Raspbian')
        self.assertEqual(self.device0.deviceinfo.distr_release, '9.4')

    def test_ping_writes_firewall_info_pos(self):
        request = self.api.post(
            '/v0.2/ping/',
            self.ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        firewall_state = FirewallState.objects.get(device=self.device0)
        self.assertTrue(firewall_state.enabled)
        self.assertDictEqual(firewall_state.rules, TEST_RULES)

    def test_ping_writes_firewall_info_neg(self):
        ping_payload = {
            'device_operating_system_version': 'linux',
            'fqdn': 'test-device0',
            'ipv4_address': '127.0.0.1',
            'uptime': '0',
            'scan_info': OPEN_PORTS_INFO,
            'netstat': OPEN_CONNECTIONS_INFO,
            'firewall_enabled': False,
            'firewall_rules': {'INPUT': [], 'OUTPUT': [], 'FORWARD': []}
        }
        request = self.api.post(
            '/v0.2/ping/',
            ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        firewall_state = FirewallState.objects.get(device=self.device0)
        self.assertFalse(firewall_state.enabled)
        self.assertDictEqual(firewall_state.rules, {'INPUT': [], 'OUTPUT': [], 'FORWARD': []})

    def test_ping_converts_json(self):
        scan_info = [{
            "host": "localhost",
            "port": 22,
            "proto": "tcp",
            "state": "open",
            "ip_version": 4
        }]
        firewall_rules = {'INPUT': [], 'OUTPUT': [], 'FORWARD': []}
        ping_payload = {
            'device_operating_system_version': 'linux',
            'fqdn': 'test-device0',
            'ipv4_address': '127.0.0.1',
            'uptime': '0',
            'scan_info': json.dumps(scan_info),
            'firewall_enabled': False,
            'firewall_rules': json.dumps(firewall_rules)
        }
        request = self.api.post(
            '/v0.2/ping/',
            ping_payload,
            **self.ping_headers,
            format='json'
        )
        mtls_ping_view(request)
        firewall_state = FirewallState.objects.get(device=self.device0)
        portscan = PortScan.objects.get(device=self.device0)
        self.assertListEqual(scan_info, portscan.scan_info)
        self.assertDictEqual(firewall_rules, firewall_state.rules)


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
        week_ago = timezone.now() - datetime.timedelta(days=7)
        hour_ago = timezone.now() - datetime.timedelta(hours=1)
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

        self.firewall0 = FirewallState.objects.create(device=self.device0, enabled=True)
        self.firewall1 = FirewallState.objects.create(device=self.device1, enabled=True)

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
        self.portscan4 = PortScan.objects.create(device=self.device4, scan_info=[
            {"host": "0.0.0.0", "port": 23, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "0.0.0.0", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "::", "port": 22, "proto": "tcp", "state": "open", "ip_version": 6}
        ])
        self.firewall4 = FirewallState.objects.create(device=self.device4, enabled=False)

    def test_fixed_issues(self):
        # initial state: firewall disabled, telnet port found, default password found - trust score low
        self.assertLess(self.device4.trust_score_percent(), 66)

        # fix issues: enable firewall, remove telnet, set non-default password
        self.portscan4.scan_info = [
            {"host": "0.0.0.0", "port": 22, "proto": "tcp", "state": "open", "ip_version": 4},
            {"host": "::", "port": 22, "proto": "tcp", "state": "open", "ip_version": 6}
        ]
        self.portscan4.save()
        self.firewall4.enabled = True
        self.firewall4.save()
        self.device_info4.default_password = False
        self.device_info4.save()

        # result: trust score high
        self.assertGreaterEqual(self.device4.trust_score_percent(), 66)

    def test_get_model(self):
        model = self.device_info0.device_model
        self.device_info0.device_model = '000d'
        self.assertEqual(self.device_info0.get_model(), 'Model B Rev 2')
        self.device_info0.device_model = '000D'  # case insensitive
        self.assertEqual(self.device_info0.get_model(), 'Model B Rev 2')
        self.device_info0.device_model = model

    def test_get_hardware_type(self):
        hw_type = self.device_info0.get_hardware_type()
        self.assertEqual(hw_type, 'Raspberry Pi')

    def test_active_inactive(self):
        active_inactive = Device.get_active_inactive(self.user0)
        self.assertListEqual(active_inactive, [2, 0])

    def test_get_expiration_date(self):
        exp_date = self.device0.get_cert_expiration_date()
        self.assertEqual(exp_date.date(), datetime.date(2019, 4, 4))

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
        self.assertEqual(self.device0.trust_score, (4.0 + 0.6 * 1.5) / 5.5)
        self.assertEqual(self.device1.trust_score, (4.0 + 0.7 * 1.5) / 5.5)

    def test_average_trust_score(self):
        score = average_trust_score(self.user1)
        self.assertEqual(score, ((4.0 + 0.6 * 1.5) / 5.5 + (4.0 + 0.7 * 1.5) / 5.5) / 2.0)


class FormsTests(TestCase):
    def setUp(self):
        self.device = Device.objects.create(device_id='device0.d.wott-dev.local')
        self.portscan = PortScan.objects.create(device=self.device, scan_info=OPEN_PORTS_INFO,
                                                netstat=OPEN_CONNECTIONS_INFO)

    def test_device_attrs_form(self):
        form_data = {'comment': 'Test comment', 'name': 'My device 1'}
        form = DeviceAttrsForm(data=form_data, instance=self.device)
        self.assertTrue(form.is_valid())

    def test_ports_form(self):
        ports_form_data = self.portscan.ports_form_data()
        form_data = {'is_ports_form': 'true', 'open_ports': ['0']}
        form = PortsForm(data=form_data, open_ports_choices=ports_form_data[0])
        self.assertTrue(form.is_valid())

    def test_networks_form(self):
        connections_form_data = self.portscan.connections_form_data()
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        form = ConnectionsForm(data=form_data, open_connections_choices=connections_form_data[0])
        self.assertTrue(form.is_valid())


class ActionsViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.user.set_password('123')
        self.user.save()
        self.device = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user,
                                            certificate=TEST_CERT)
        self.portscan = PortScan.objects.create(device=self.device, scan_info=OPEN_PORTS_INFO_TELNET,
                                                netstat=OPEN_CONNECTIONS_INFO)
        self.firewall = FirewallState.objects.create(device=self.device, enabled=False)
        self.device_info = DeviceInfo.objects.create(device=self.device, default_password=True)
        self.url = reverse('actions')

    def test_get(self):
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'We found disabled firewall present on <a href="/devices/{self.device.pk}/">{self.device.get_name()}</a>'
        )
        self.assertContains(
            response,
            f'We found default credentials present on <a href="/devices/{self.device.pk}/">{self.device.get_name()}</a>'
        )
        self.assertContains(
            response,
            f'We found enabled Telnet server present on <a href="/devices/{self.device.pk}/">{self.device.get_name()}</a>'
        )


class DeviceDetailViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.user.set_password('123')
        self.user.save()
        self.device = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user,
                                            certificate=TEST_CERT)
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
        self.firewall = FirewallState.objects.create(device=self.device)
        self.url = reverse('device-detail', kwargs={'pk': self.device.pk})
        self.url2 = reverse('device-detail-security', kwargs={'pk': self.device.pk})

        self.device_no_portscan = Device.objects.create(device_id='device1.d.wott-dev.local', owner=self.user,
                                                        certificate=TEST_CERT)
        self.firewall2 = FirewallState.objects.create(device=self.device_no_portscan)

        self.device_no_firewall = Device.objects.create(device_id='device2.d.wott-dev.local', owner=self.user,
                                                        certificate=TEST_CERT)
        self.portscan2 = PortScan.objects.create(device=self.device_no_firewall, scan_info=OPEN_PORTS_INFO,
                                                 netstat=OPEN_CONNECTIONS_INFO)

        self.device_no_logins = Device.objects.create(device_id='device3.d.wott-dev.local', owner=self.user,
                                                      certificate=TEST_CERT)
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

    def test_device_detail_not_logged_in(self):
        url = reverse('device-detail', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_device_detail_software_not_logged_in(self):
        url = reverse('device-detail-software', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_device_detail_security_not_logged_in(self):
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_device_detail_network_not_logged_in(self):
        url = reverse('device-detail-network', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_device_detail_hardware_not_logged_in(self):
        url = reverse('device-detail-hardware', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_credentials_not_logged_in(self):
        url = reverse('credentials')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_get(self):
        """
        If no questions exist, an appropriate message is displayed.
        """
        self.client.login(username='test', password='123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Device Profile')
        self.assertFalse(self.device.has_actions)
        self.assertNotContains(response, 'Show recommended actions')

    def test_actions_btn_pos(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail', kwargs={'pk': self.device_no_logins.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.device_no_logins.has_actions)
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
        self.assertContains(response, 'Device Profile')
        self.assertNotContains(response, '>Security<')
        self.assertNotContains(response, '>Hardware<')

    def test_no_firewall(self):
        """
        Security tab should not be rendered if Device object has no FirewallState.
        """
        url = reverse('device-detail', kwargs={'pk': self.device_no_firewall.pk})
        self.client.login(username='test', password='123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Device Profile')
        self.assertContains(response, '>Hardware<')
        self.assertNotContains(response, '>Security<')

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
        form_data = {'is_ports_form': 'true', 'open_ports': ['0']}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_ports, [['192.168.1.178', 'tcp', 22, False]])

    def test_open_connections(self):
        self.client.login(username='test', password='123')
        form_data = {'is_connections_form': 'true', 'open_connections': ['0']}
        self.client.post(self.url2, form_data)
        portscan = PortScan.objects.get(pk=self.portscan.pk)
        self.assertListEqual(portscan.block_networks, [['192.168.1.177', False]])

    def test_no_logins(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device_no_logins.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No recent login attempts detected')

    def test_logins(self):
        self.client.login(username='test', password='123')
        url = reverse('device-detail-security', kwargs={'pk': self.device.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<pre>pi:')
        self.assertContains(response, 'success: 1')


class APICredsTest(APITestCase):
    def setUp(self):
        self.url = reverse('mtls-creds')
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.credential = Credential.objects.create(owner=self.user, name='name1', key='key1',
                                                    value='as9dfyaoiufhoasdfjh')
        self.device0 = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user)
        self.headers = {
            'HTTP_SSL_CLIENT_SUBJECT_DN': 'CN=device0.d.wott-dev.local',
            'HTTP_SSL_CLIENT_VERIFY': 'SUCCESS'
        }

    def test_get(self):
        response = self.client.get(
            self.url,
            **self.headers,
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(response.json(), [{'key': 'key1', 'name': 'name1', 'value': 'as9dfyaoiufhoasdfjh',
                                                'pk': self.credential.pk}])

    def test_get_revoked_device(self):
        Device.objects.create(device_id='device1.d.wott-dev.local')
        headers = {
            'HTTP_SSL_CLIENT_SUBJECT_DN': 'CN=device1.d.wott-dev.local',
            'HTTP_SSL_CLIENT_VERIFY': 'SUCCESS'
        }
        response = self.client.get(
            self.url,
            **headers,
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertListEqual(response.json(), [])


class APIIsClaimedTest(APITestCase):
    def setUp(self):
        self.url = reverse('mtls-is_claimed')
        User = get_user_model()
        self.user = User.objects.create_user('test')
        self.device0 = Device.objects.create(device_id='device0.d.wott-dev.local', owner=self.user)
        self.headers = {
            'HTTP_SSL_CLIENT_SUBJECT_DN': 'CN=device0.d.wott-dev.local',
            'HTTP_SSL_CLIENT_VERIFY': 'SUCCESS'
        }

    def test_get(self):
        response = self.client.get(
            self.url,
            **self.headers,
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json(), {'claim_token': '', 'claimed': True})