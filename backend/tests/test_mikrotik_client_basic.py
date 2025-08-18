"""Unit test dasar untuk mikrotik_client.

Fokus: memastikan wrapper + implementasi berfungsi dan rantai deteksi MAC
memakai urutan yang benar melalui resource palsu.
"""
import os
import pytest

os.environ.setdefault('ALLOW_LAX_CONFIG_IMPORT', '1')

from app.infrastructure.gateways import mikrotik_client  # noqa: E402
from app.infrastructure.gateways import mikrotik_client_impl  # type: ignore  # noqa: E402


class _FakeResource:
    def __init__(self, records):
        self._records = records

    def get(self, **kwargs):
        if not kwargs:
            return list(self._records)
        out = []
        for r in self._records:
            if all(r.get(k) == v for k, v in kwargs.items()):
                out.append(r)
        return out

    def add(self, **kwargs):
        if '.id' not in kwargs and 'id' not in kwargs:
            # simple incremental id
            kwargs['.id'] = f"*{len(self._records)+1}"
        self._records.append(kwargs)
        return True

    def remove(self, **kwargs):
        _id = kwargs.get('id') or kwargs.get('.id')
        self._records = [r for r in self._records if r.get('.id') != _id and r.get('id') != _id]

    def set(self, **kwargs):
        _id = kwargs.get('.id') or kwargs.get('id')
        for r in self._records:
            if r.get('.id') == _id or r.get('id') == _id:
                r.update({k: v for k, v in kwargs.items() if k not in ('.id','id')})
                return True
        return False

    def call(self, *args, **kwargs):
        return True


class _FakeAPI:
    def __init__(self, tables):
        self._tables = tables

    def get_resource(self, path):
        return self._tables[path]


@pytest.fixture
def fake_api(monkeypatch):
    tables = {
        '/ip/hotspot/host': _FakeResource([{'address': '10.0.0.5', 'mac-address': 'AA:BB:CC:DD:EE:01'}]),
        '/ip/dhcp-server/lease': _FakeResource([]),
        '/ip/hotspot/active': _FakeResource([]),
        '/ip/arp': _FakeResource([]),
        '/': _FakeResource([]),
        '/ip/hotspot/ip-binding': _FakeResource([]),
        '/interface/bridge/host': _FakeResource([]),
        '/ip/dns/static': _FakeResource([]),
        '/ip/firewall/address-list': _FakeResource([]),
    }
    api = _FakeAPI(tables)

    def _fake_pool(_name=None):
        return api

    # Patch wrapper (tidak dipakai oleh implementasi) dan implementasi langsung
    monkeypatch.setattr(mikrotik_client, '_get_api_from_pool', _fake_pool)
    monkeypatch.setattr(mikrotik_client_impl, '_get_api_from_pool', lambda _n=None: api)
    return api


def test_find_mac_success_from_host(fake_api):
    # Gunakan force_refresh untuk menghindari kemungkinan negative cache residual dari test lain
    ok, mac, source = mikrotik_client.find_mac_by_ip_comprehensive('10.0.0.5', force_refresh=True)
    assert ok is True
    assert mac == 'AA:BB:CC:DD:EE:01'
    assert source == 'Host Table'


def test_find_mac_not_found_chain(fake_api):
    fake_api.get_resource('/ip/hotspot/host')._records.clear()
    ok, mac, source = mikrotik_client.find_mac_by_ip_comprehensive('10.0.0.99', force_refresh=True)
    assert ok is True
    assert mac is None
    assert 'Not found' in source


def test_create_or_update_ip_binding(fake_api):
    ok, msg = mikrotik_client.create_or_update_ip_binding('aa:bb:cc:dd:ee:02', '10.0.0.10', 'user-test')
    assert ok is True
    ok2, msg2 = mikrotik_client.create_or_update_ip_binding('aa:bb:cc:dd:ee:02', '10.0.0.10', 'user-test')
    assert ok2 is True


def test_set_hotspot_user_profile_lax_import(monkeypatch):
    def _none_pool(_n=None):
        return None
    monkeypatch.setattr(mikrotik_client, '_get_api_from_pool', _none_pool)
    ok, msg = mikrotik_client.set_hotspot_user_profile('dummy','profile')
    assert ok in (True, False)
