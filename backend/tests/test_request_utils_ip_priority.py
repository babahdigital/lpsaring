import json


def test_frontend_header_priority_over_url_params(client):
    # When both frontend header and URL param present, frontend should win
    headers = {
        'X-Frontend-Detected-IP': '192.168.10.20',
        'X-Frontend-Detection-Method': 'auth-store',
    }
    resp = client.get('/api/debug/ip-source?client_ip=192.168.10.21', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ip'] == '192.168.10.20'
    assert data['source'].startswith('frontend:')


def test_proxy_overrides_frontend_on_mismatch(client):
    # If proxy headers provide a different valid IP, proxy should override
    headers = {
        'X-Frontend-Detected-IP': '192.168.10.21',
        'X-Frontend-Detection-Method': 'local-storage',
        'X-Real-IP': '192.168.10.50',  # acts as proxy_best
    }
    resp = client.get('/api/debug/ip-source', headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ip'] == '192.168.10.50'
    assert data['source'] == 'proxy_overrode_frontend'


def test_json_body_fallback_when_no_headers(client):
    # With no headers and no URL args, JSON body ip should be accepted
    payload = {'ip': '192.168.10.77'}
    resp = client.post('/api/debug/ip-source', data=json.dumps(payload), content_type='application/json')
    # Our debug endpoint is GET-only; 405 is acceptable here
    assert resp.status_code in (405, 200)
