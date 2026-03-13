from flask import Flask

from app.infrastructure.gateways.mikrotik_client import get_hotspot_host_usage_map


class _HostResource:
    def __init__(self, rows):
        self.rows = list(rows)

    def get(self, **_kwargs):
        return list(self.rows)


class _Api:
    def __init__(self, rows):
        self._resource = _HostResource(rows)

    def get_resource(self, path):
        assert path == "/ip/hotspot/host"
        return self._resource


def test_get_hotspot_host_usage_map_prefers_local_hotspot_row_for_duplicate_mac():
    app = Flask(__name__)
    app.config["HOTSPOT_CLIENT_IP_CIDRS"] = ["172.16.2.0/23"]
    api = _Api(
        [
            {
                "mac-address": "66:93:21:1F:07:B5",
                "address": "154.30.75.26",
                "to-address": "154.30.75.26",
                "server": "srv-user",
                "bypassed": "true",
                "authorized": "false",
                "idle-time": "3d",
                "uptime": "3d",
                "bytes-in": "80",
                "bytes-out": "0",
            },
            {
                "mac-address": "66:93:21:1F:07:B5",
                "address": "172.16.2.190",
                "to-address": "172.16.2.190",
                "server": "srv-user",
                "bypassed": "true",
                "authorized": "false",
                "idle-time": "0s",
                "uptime": "5d",
                "bytes-in": "174288444",
                "bytes-out": "1798674679",
            },
        ]
    )

    with app.app_context():
        ok, usage_map, msg = get_hotspot_host_usage_map(api)

    assert ok is True
    assert msg == "Sukses"
    assert usage_map["66:93:21:1F:07:B5"]["address"] == "172.16.2.190"
    assert usage_map["66:93:21:1F:07:B5"]["source_address"] == "172.16.2.190"
    assert usage_map["66:93:21:1F:07:B5"]["to_address"] == "172.16.2.190"
    assert usage_map["66:93:21:1F:07:B5"]["bytes_in"] == 174288444
    assert usage_map["66:93:21:1F:07:B5"]["bytes_out"] == 1798674679


def test_get_hotspot_host_usage_map_prefers_fresher_local_row_over_stale_high_byte_row():
    app = Flask(__name__)
    app.config["HOTSPOT_CLIENT_IP_CIDRS"] = ["172.16.2.0/23"]
    api = _Api(
        [
            {
                "mac-address": "AA:BB:CC:DD:EE:99",
                "address": "172.16.2.11",
                "to-address": "172.16.2.11",
                "server": "srv-user",
                "bypassed": "true",
                "authorized": "false",
                "idle-time": "2d",
                "uptime": "10d",
                "bytes-in": "999999999",
                "bytes-out": "999999999",
            },
            {
                "mac-address": "AA:BB:CC:DD:EE:99",
                "address": "172.16.2.88",
                "to-address": "172.16.2.88",
                "server": "srv-user",
                "bypassed": "true",
                "authorized": "false",
                "idle-time": "5s",
                "uptime": "2h",
                "bytes-in": "1234",
                "bytes-out": "5678",
            },
        ]
    )

    with app.app_context():
        ok, usage_map, msg = get_hotspot_host_usage_map(api)

    assert ok is True
    assert msg == "Sukses"
    assert usage_map["AA:BB:CC:DD:EE:99"]["address"] == "172.16.2.88"
    assert usage_map["AA:BB:CC:DD:EE:99"]["source_address"] == "172.16.2.88"


def test_get_hotspot_host_usage_map_uses_translated_local_ip_when_original_ip_is_outside_hotspot_cidr():
    app = Flask(__name__)
    app.config["HOTSPOT_CLIENT_IP_CIDRS"] = ["172.16.2.0/23"]
    api = _Api(
        [
            {
                "mac-address": "2E:96:F8:D4:90:2E",
                "address": "172.16.0.2",
                "to-address": "172.16.2.172",
                "server": "srv-user",
                "bypassed": "false",
                "authorized": "true",
                "idle-time": "10s",
                "uptime": "1h",
                "bytes-in": "100",
                "bytes-out": "200",
            }
        ]
    )

    with app.app_context():
        ok, usage_map, msg = get_hotspot_host_usage_map(api)

    assert ok is True
    assert msg == "Sukses"
    assert usage_map["2E:96:F8:D4:90:2E"]["address"] == "172.16.2.172"
    assert usage_map["2E:96:F8:D4:90:2E"]["source_address"] == "172.16.0.2"
    assert usage_map["2E:96:F8:D4:90:2E"]["to_address"] == "172.16.2.172"