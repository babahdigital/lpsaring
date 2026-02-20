from app.infrastructure.gateways.mikrotik_client import upsert_dhcp_static_lease


class _FakeLeaseResource:
    def __init__(self, leases):
        self._leases = list(leases)
        self.add_calls = []
        self.set_calls = []
        self.remove_calls = []
        self.call_calls = []

    def get(self, **query):
        mac = (query.get("mac-address") or "").upper()
        if not mac:
            return list(self._leases)
        return [lease for lease in self._leases if str(lease.get("mac-address") or "").upper() == mac]

    def add(self, **data):
        self.add_calls.append(dict(data))
        # Mimic RouterOS lease row
        new_row = dict(data)
        new_row[".id"] = f"*new{len(self.add_calls)}"
        self._leases.append(new_row)

    def set(self, **data):
        self.set_calls.append(dict(data))

    def remove(self, id):
        self.remove_calls.append(id)
        self._leases = [lease for lease in self._leases if str(lease.get("id") or lease.get(".id")) != str(id)]

    def call(self, name, payload):
        self.call_calls.append((name, dict(payload)))


class _FakeApi:
    def __init__(self, lease_resource):
        self._lease_resource = lease_resource

    def get_resource(self, path):
        assert path == "/ip/dhcp-server/lease"
        return self._lease_resource


def test_upsert_dhcp_static_lease_requires_server_for_managed_comment():
    resource = _FakeLeaseResource([])
    api = _FakeApi(resource)

    ok, msg = upsert_dhcp_static_lease(
        api_connection=api,
        mac_address="AA:BB:CC:DD:EE:FF",
        address="172.16.2.10",
        comment="lpsaring|static-dhcp|user=08xxx|uid=abc",
        server=None,
    )

    assert ok is False
    assert "MIKROTIK_DHCP_LEASE_SERVER_NAME" in msg
    assert resource.add_calls == []
    assert resource.set_calls == []


def test_upsert_dhcp_static_lease_pinned_server_adds_when_no_matching_server():
    # Existing lease is on a different server (Kamtib). Previously, code would update leases[0].
    existing = {
        ".id": "*1",
        "mac-address": "AA:BB:CC:DD:EE:FF",
        "address": "172.16.3.79",
        "server": "Kamtib",
        "dynamic": "false",
        "comment": "something",
    }
    resource = _FakeLeaseResource([existing])
    api = _FakeApi(resource)

    ok, msg = upsert_dhcp_static_lease(
        api_connection=api,
        mac_address="AA:BB:CC:DD:EE:FF",
        address="172.16.2.171",
        comment="lpsaring|static-dhcp|user=08xxx|uid=abc",
        server="Klien",
    )

    assert ok is True
    assert msg == "Sukses"
    # Should create a new lease for server Klien (not update existing Kamtib lease)
    assert len(resource.add_calls) == 1
    assert resource.add_calls[0]["server"] == "Klien"
    assert resource.add_calls[0]["address"] == "172.16.2.171"
    assert resource.set_calls == []


def test_upsert_dhcp_static_lease_cleans_managed_other_servers_best_effort():
    leases = [
        {
            ".id": "*1",
            "mac-address": "AA:BB:CC:DD:EE:FF",
            "address": "172.16.3.79",
            "server": "Kamtib",
            "dynamic": "false",
            "comment": "lpsaring|static-dhcp|user=08xxx|uid=abc",
        },
        {
            ".id": "*2",
            "mac-address": "AA:BB:CC:DD:EE:FF",
            "address": "172.16.2.171",
            "server": "Klien",
            "dynamic": "false",
            "comment": "lpsaring|static-dhcp|user=08xxx|uid=abc",
        },
    ]
    resource = _FakeLeaseResource(leases)
    api = _FakeApi(resource)

    ok, _msg = upsert_dhcp_static_lease(
        api_connection=api,
        mac_address="AA:BB:CC:DD:EE:FF",
        address="172.16.2.171",
        comment="lpsaring|static-dhcp|user=08xxx|uid=abc",
        server="Klien",
    )

    assert ok is True
    # Kamtib managed lease should be removed.
    assert "*1" in resource.remove_calls
    # Then it should update the Klien lease (set called at least once)
    assert len(resource.set_calls) == 1
