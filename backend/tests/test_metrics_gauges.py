import os
os.environ.setdefault('ALLOW_LAX_CONFIG_IMPORT', '1')

def test_metrics_gauges_presence(client):
    resp = client.get('/metrics')
    assert resp.status_code == 200
    body = resp.data.decode()
    # Gauges should be present (initialized even at zero)
    assert 'mac_grace_cache_size' in body
    assert 'mac_lookup_failure_ratio' in body
    # Histogram alias seconds buckets or sum
    assert 'mac_lookup_duration_seconds_sum' in body
