import os

os.environ.setdefault('ALLOW_LAX_CONFIG_IMPORT', '1')


def test_metrics_endpoint(client):
    resp = client.get('/metrics')
    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'mac_lookup_total' in body
    assert 'mac_lookup_duration_ms_sum' in body
    # Histogram bucket presence (at least one default bucket like le="5" or others)
    assert 'mac_lookup_duration_bucket' in body
    # Seconds alias metrics
    assert 'mac_lookup_duration_seconds_sum' in body
    assert 'mac_lookup_duration_seconds_count' in body


def test_multi_pool_monkeypatch(monkeypatch):
    from app.infrastructure.gateways import mikrotik_client_impl as impl
    monkeypatch.setenv('MIKROTIK_POOL_SIZE', '2')

    class _FakePool:
        def get_api(self):
            return object()

    monkeypatch.setattr(impl, '_create_connection_pool', lambda: _FakePool())
    api1 = impl._get_api_from_pool()
    api2 = impl._get_api_from_pool()
    assert api1 is not None and api2 is not None
