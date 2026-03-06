from app.infrastructure.gateways.mikrotik_client import remove_address_list_entry


class _Resource:
    def __init__(self):
        self.entries = [
            {"id": "*A", "address": "172.16.2.229", "list": "unauthorized", "comment": "lpsaring:unauthorized"}
        ]

    def get(self, **kwargs):
        address = kwargs.get("address")
        list_name = kwargs.get("list")
        return [
            entry
            for entry in self.entries
            if entry.get("address") == address and entry.get("list") == list_name
        ]

    def remove(self, **kwargs):
        if ".id" in kwargs:
            return

        entry_id = kwargs.get("id")
        self.entries = [entry for entry in self.entries if entry.get("id") != entry_id]


class _Api:
    def __init__(self, resource):
        self._resource = resource

    def get_resource(self, path):
        assert path == "/ip/firewall/address-list"
        return self._resource


def test_remove_address_list_entry_falls_back_to_id_and_verifies_deleted():
    resource = _Resource()
    api = _Api(resource)

    ok, message = remove_address_list_entry(api, "172.16.2.229", "unauthorized")

    assert ok is True
    assert message == "Sukses"
    assert resource.get(address="172.16.2.229", list="unauthorized") == []


class _ResourceRace:
    def __init__(self):
        self._first_get = True

    def get(self, **kwargs):
        if self._first_get:
            self._first_get = False
            return [{"id": "*A", ".id": "*A", "address": "172.16.2.229", "list": "unauthorized"}]
        return []

    def remove(self, **kwargs):
        raise RuntimeError("entry already removed by another process")


def test_remove_address_list_entry_returns_success_when_entry_already_gone_after_race():
    resource = _ResourceRace()
    api = _Api(resource)

    ok, message = remove_address_list_entry(api, "172.16.2.229", "unauthorized")

    assert ok is True
    assert message == "Sukses"
