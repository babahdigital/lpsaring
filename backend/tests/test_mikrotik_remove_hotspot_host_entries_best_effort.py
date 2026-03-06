from app.infrastructure.gateways.mikrotik_client import remove_hotspot_host_entries_best_effort


class _HostResource:
    def __init__(self, entries):
        self.entries = list(entries)
        self.queries = []

    def get(self, **kwargs):
        self.queries.append(dict(kwargs))
        matched = []
        for entry in self.entries:
            if all(str(entry.get(k) or "") == str(v) for k, v in kwargs.items()):
                matched.append(dict(entry))
        return matched

    def remove(self, **kwargs):
        entry_id = kwargs.get("id") or kwargs.get(".id")
        self.entries = [
            entry for entry in self.entries
            if (entry.get("id") or entry.get(".id")) != entry_id
        ]


class _FailingHostResource:
    def get(self, **_kwargs):
        raise RuntimeError("router unavailable")

    def remove(self, **_kwargs):
        return None


class _Api:
    def __init__(self, resource):
        self._resource = resource

    def get_resource(self, path):
        assert path == "/ip/hotspot/host"
        return self._resource


def test_remove_hotspot_host_entries_best_effort_falls_back_to_mac_only():
    resource = _HostResource(
        [
            {
                "id": "*1",
                "mac-address": "AA:BB:CC:DD:EE:FF",
                "address": "172.16.2.10",
                "user": "08123456789",
            }
        ]
    )
    api = _Api(resource)

    ok, msg, removed = remove_hotspot_host_entries_best_effort(
        api_connection=api,
        mac_address="AA:BB:CC:DD:EE:FF",
        address="172.16.99.99",  # stale IP hint
        username="08999999999",  # stale username hint
        allow_username_only_fallback=False,
    )

    assert ok is True
    assert msg == "Sukses"
    assert removed == 1
    assert resource.entries == []
    assert {"mac-address": "AA:BB:CC:DD:EE:FF", "address": "172.16.99.99", "user": "08999999999"} in resource.queries
    assert {"mac-address": "AA:BB:CC:DD:EE:FF"} in resource.queries


def test_remove_hotspot_host_entries_best_effort_returns_error_when_query_fails():
    api = _Api(_FailingHostResource())

    ok, msg, removed = remove_hotspot_host_entries_best_effort(
        api_connection=api,
        mac_address="AA:BB:CC:DD:EE:11",
        address=None,
        username=None,
        allow_username_only_fallback=False,
    )

    assert ok is False
    assert removed == 0
    assert "router unavailable" in msg
