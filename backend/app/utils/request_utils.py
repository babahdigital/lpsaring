_last_no_ip_log_time = 0.0
_last_backend_miss_log: dict = {}
# backend/app/utils/request_utils.py (OPTIMIZED AND DYNAMIC VERSION)
from flask import request, current_app
from typing import Optional
import re
import urllib.parse
import time
from app.infrastructure.gateways import mikrotik_client

# ✅ Global variables untuk reduce logging
_localhost_logged = False
_accepted_ips = set()
_proxy_reject_logs = set()

def get_client_ip() -> Optional[str]:
    """
    FIXED & ENHANCED: Deteksi IP klien yang ketat, dinamis, dan dengan prioritas yang benar.
    Menghilangkan asumsi dan fallback yang berbahaya.
    """
    # Ambil konfigurasi dinamis
    proxy_ips = current_app.config.get('NETWORK_PROXY_IPS', [])
    allow_localhost = current_app.config.get('NETWORK_ALLOW_LOCALHOST', False)

    # PRIORITAS 1: Parameter URL (dari MikroTik) - Paling akurat untuk captive portal
    url_ip = request.args.get('client_ip') or request.args.get('ip')
    if url_ip and is_valid_client_ip(url_ip, proxy_ips, allow_localhost):
        if url_ip not in _accepted_ips:  # ✅ Only log once per IP
            current_app.logger.info(f"[CLIENT-IP] ✅ From URL params: {url_ip}")
        # Tag source for downstream logs
        try: request.environ['CLIENT_IP_SOURCE'] = 'url_params:client_ip'
        except Exception: pass
        return url_ip
    
    # Kumpulkan kandidat dari proxy lebih awal untuk perbandingan
    # Pastikan variabel xff/xri terinisialisasi agar tidak UnboundLocalError
    xff = ''
    xri = None
    proxy_client_ip = (
        request.headers.get('X-Final-Client-IP') or
        request.headers.get('X-Client-IP') or
        request.headers.get('X-Client-IP-From-Args')
    )
    proxy_best: Optional[str] = None
    if proxy_client_ip and proxy_client_ip != '127.0.0.1' and is_valid_client_ip(proxy_client_ip, proxy_ips, allow_localhost):
        proxy_best = proxy_client_ip
    if not proxy_best:
        xff = request.headers.get('X-Forwarded-For', '')
        if xff:
            for candidate in [p.strip() for p in xff.split(',') if p.strip()]:
                if candidate == '127.0.0.1':
                    continue
                if is_valid_client_ip(candidate, proxy_ips, allow_localhost):
                    proxy_best = candidate
                    break
    if not proxy_best:
        xri = request.headers.get('X-Real-IP')
        if xri and xri != '127.0.0.1' and is_valid_client_ip(xri, proxy_ips, allow_localhost):
            proxy_best = xri

    # PRIORITAS 2: Headers dari deteksi Frontend - gunakan kecuali bertentangan dengan proxy
    frontend_ip = request.headers.get('X-Frontend-Detected-IP')
    if frontend_ip and is_valid_client_ip(frontend_ip, proxy_ips, allow_localhost):
        method = request.headers.get('X-Frontend-Detection-Method', 'unknown')
        if proxy_best and proxy_best != frontend_ip:
            # Lebih aman: percayai proxy ketika terjadi mismatch
            if proxy_best not in _accepted_ips:
                current_app.logger.info(f"[CLIENT-IP] ✅ From proxy (overrode frontend:{method}={frontend_ip}): {proxy_best}")
            try: request.environ['CLIENT_IP_SOURCE'] = 'proxy_overrode_frontend'
            except Exception: pass
            return proxy_best
        # Tidak ada proxy kandidat atau sama dengan frontend → gunakan frontend
        if frontend_ip not in _accepted_ips:
            current_app.logger.info(f"[CLIENT-IP] ✅ From frontend ({method}): {frontend_ip}")
        try: request.environ['CLIENT_IP_SOURCE'] = f'frontend:{method}'
        except Exception: pass
        return frontend_ip

    # PRIORITAS 3: JSON body (untuk endpoint seperti sync-device)
    try:
        if request.is_json:
            body = request.get_json(silent=True) or {}
            body_ip = body.get('ip') or body.get('client_ip')
            if body_ip and is_valid_client_ip(body_ip, proxy_ips, allow_localhost):
                if body_ip not in _accepted_ips:
                    current_app.logger.info(f"[CLIENT-IP] ✅ From JSON body: {body_ip}")
                try: request.environ['CLIENT_IP_SOURCE'] = 'json_body:ip'
                except Exception: pass
                return body_ip
    except Exception:
        pass

    # PRIORITAS 4: Header khusus dari reverse proxy (jika diset) - gunakan jika tersedia
    if proxy_best:
        if proxy_best not in _accepted_ips:
            current_app.logger.info(f"[CLIENT-IP] ✅ From proxy headers: {proxy_best}")
        try: request.environ['CLIENT_IP_SOURCE'] = 'proxy_headers'
        except Exception: pass
        return proxy_best
    # PRIORITAS 5/6 di-merge di atas (proxy_best)

    # PRIORITAS 7: request.remote_addr sebagai fallback aman
    # Bahkan jika header proxy ada namun tidak memberikan kandidat yang valid,
    # izinkan fallback ke remote_addr apabila valid dan bukan proxy.
    remote_ip = request.remote_addr
    # Hindari menerima IP jaringan docker bridge sebagai client IP (mis. 172.17/172.18)
    try:
        block_prefixes = current_app.config.get('NETWORK_REMOTE_ADDR_BLOCK_PREFIXES', ['172.17.', '172.18.'])
    except Exception:
        block_prefixes = ['172.17.', '172.18.']
    if remote_ip and not any(remote_ip.startswith(pfx) for pfx in block_prefixes) and is_valid_client_ip(remote_ip, proxy_ips, allow_localhost):
        if remote_ip not in _accepted_ips:
            current_app.logger.info(f"[CLIENT-IP] ✅ From remote_addr: {remote_ip}")
        try: request.environ['CLIENT_IP_SOURCE'] = 'remote_addr_fallback'
        except Exception: pass
        return remote_ip

    # TIDAK ADA FALLBACK BERBAHAYA!
    global _last_no_ip_log_time
    now = time.time()
    if now - _last_no_ip_log_time > 30:  # throttle warning setiap 30s
        current_app.logger.warning(f"[CLIENT-IP] ❌ Failed to detect valid client IP")
        _last_no_ip_log_time = now
    return None

# Global variables untuk mengurangi log berulang
_localhost_logged = False
_accepted_ips = set()
_last_mac_log = {}  # Cache untuk MAC log
_backend_mac_attempt: dict = {}  # throttle lookup per IP

def get_client_mac() -> Optional[str]:
    """
    PERBAIKAN V5: Mengurangi log verbose dengan selective logging.
    
    Prioritas deteksi MAC:
    1. URL param `mac` (dari redirect mikrotik)
    2. Header `X-Frontend-Detected-MAC` (dari JavaScript frontend)
    """
    # PRIORITAS 1: URL param MAC (dari redirect)
    url_mac = request.args.get('mac')
    if url_mac:
        decoded_mac = url_mac
        max_decode_attempts = 3
        
        for attempt in range(max_decode_attempts):
            try:
                new_decoded = urllib.parse.unquote(decoded_mac)
                if new_decoded == decoded_mac:
                    break
                decoded_mac = new_decoded
            except Exception:
                break
        
        # Normalisasi format MAC
        normalized_mac = decoded_mac.replace('-', ':').replace('%3A', ':').replace('%3a', ':').upper()
        
        if is_valid_mac(normalized_mac):
            # Log hanya jika MAC berbeda dari sebelumnya
            global _last_mac_log
            current_time = time.time()
            if (_last_mac_log.get('url_mac') != normalized_mac or 
                current_time - _last_mac_log.get('url_time', 0) > 60):
                current_app.logger.info(f"[CLIENT-MAC] ✅ From URL: {normalized_mac}")
                _last_mac_log['url_mac'] = normalized_mac
                _last_mac_log['url_time'] = current_time
            return normalized_mac

    # PRIORITAS 2: Header dari Frontend / Reverse Proxy
    header_mac = request.headers.get('X-Frontend-Detected-MAC')
    if not header_mac:
        # Allow proxy to pass-through client MAC when available
        header_mac = (
            request.headers.get('X-Client-MAC') or
            request.headers.get('X-Client-MAC-From-Args')
        )
    if header_mac:
        # Apply decoding logic untuk frontend header
        decoded_header_mac = header_mac
        max_decode_attempts = 3
        
        for attempt in range(max_decode_attempts):
            try:
                new_decoded = urllib.parse.unquote(decoded_header_mac)
                if new_decoded == decoded_header_mac:
                    break
                decoded_header_mac = new_decoded
            except Exception:
                break
        
        # Normalisasi format MAC
        normalized_header_mac = decoded_header_mac.replace('-', ':').replace('%3A', ':').replace('%3a', ':').upper()
        
        if is_valid_mac(normalized_header_mac):
            # Log hanya jika MAC berbeda dari sebelumnya
            current_time = time.time()
            if (_last_mac_log.get('header_mac') != normalized_header_mac or 
                current_time - _last_mac_log.get('header_time', 0) > 60):
                current_app.logger.info(f"[CLIENT-MAC] ✅ From frontend: {normalized_header_mac}")
                _last_mac_log['header_mac'] = normalized_header_mac
                _last_mac_log['header_time'] = current_time
            return normalized_header_mac

    # Fallback: Backend MikroTik lookup jika diaktifkan & punya IP
    current_time = time.time()
    backend_enabled = current_app.config.get('BACKEND_MAC_LOOKUP_ENABLED', True)
    if backend_enabled:
        # Ambil IP yang sama dengan prioritas get_client_ip (hindari proxy/gateway seperti 10.0.0.1)
        ip_candidate = get_client_ip()
        if not ip_candidate:
            # Best-effort: coba ambil dari JSON body ip/client_ip jika valid dan bukan proxy
            try:
                if request.is_json:
                    body = request.get_json(silent=True) or {}
                    body_ip = body.get('ip') or body.get('client_ip')
                    if body_ip:
                        proxy_ips = current_app.config.get('NETWORK_PROXY_IPS', [])
                        allow_localhost = current_app.config.get('NETWORK_ALLOW_LOCALHOST', False)
                        if is_valid_client_ip(body_ip, proxy_ips, allow_localhost):
                            ip_candidate = body_ip
            except Exception:
                # Silent: fallback ke header biasa jika perlu
                pass
        if not ip_candidate:
            # Terakhir, fallback minimal ke header standar (tetap validasi agar tidak pakai proxy/gateway)
            header_ip = (
                request.headers.get('X-Frontend-Detected-IP') or
                request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
                request.headers.get('X-Real-IP')
            )
            if header_ip:
                proxy_ips = current_app.config.get('NETWORK_PROXY_IPS', [])
                allow_localhost = current_app.config.get('NETWORK_ALLOW_LOCALHOST', False)
                if is_valid_client_ip(header_ip, proxy_ips, allow_localhost):
                    ip_candidate = header_ip
                else:
                    # Jangan lakukan lookup jika hanya dapat IP proxy/gateway
                    return None
        if ip_candidate == '127.0.0.1':
            # Abaikan lookup untuk localhost agar fokus ke IP klien sebenarnya
            return None
        if ip_candidate and is_valid_ip_format(ip_candidate):
            last_attempt = _backend_mac_attempt.get(ip_candidate, 0)
            # Force refresh paling cepat tiap 45s; antara itu gunakan cache internal di gateway
            refresh_interval = 45
            force = current_time - last_attempt > refresh_interval
            if current_time - last_attempt > 10:  # minimal jeda antar attempt
                _backend_mac_attempt[ip_candidate] = current_time
                try:
                    ok, mac_mt, source = mikrotik_client.find_mac_by_ip_comprehensive(ip_candidate, force_refresh=force)
                    if ok and mac_mt:
                        current_app.logger.info(f"[CLIENT-MAC] ✅ Backend lookup ({source}): {mac_mt}")
                        return mac_mt
                    else:
                        # Throttle miss log per IP setiap 90s
                        last_miss = _last_backend_miss_log.get(ip_candidate, 0)
                        if current_time - last_miss > 90:
                            current_app.logger.debug(f"[CLIENT-MAC] Backend lookup miss ({source}) untuk {ip_candidate}")
                            _last_backend_miss_log[ip_candidate] = current_time
                except Exception as e:  # pragma: no cover
                    last_miss = _last_backend_miss_log.get('_error', 0)
                    if current_time - last_miss > 60:
                        current_app.logger.warning(f"[CLIENT-MAC] Backend lookup error: {e}")
    # Log "no MAC found" hanya sekali per menit
    if current_time - _last_mac_log.get('no_mac_time', 0) > 60:
        current_app.logger.debug(f"[CLIENT-MAC] No valid MAC found")
        _last_mac_log['no_mac_time'] = current_time
    return None

def is_valid_ip_format(ip: str) -> bool:
    """Hanya memvalidasi format IP address."""
    if not ip or not isinstance(ip, str):
        return False
    
    ip_pattern = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return bool(ip_pattern.match(ip))

def is_valid_client_ip(ip: str, proxy_ips: list, allow_localhost: bool) -> bool:
    """
    Validasi dinamis: IP harus formatnya benar, bukan proxy dari config,
    dan menghormati flag localhost untuk development.
    """
    if not is_valid_ip_format(ip):
        return False
    
    if ip == "127.0.0.1":
        if allow_localhost:
            # ✅ REDUCE LOG: Hanya log sekali untuk localhost
            global _localhost_logged
            if not _localhost_logged:
                current_app.logger.debug(f"[DEV-SKIP] Melewati IP localhost untuk testing: {ip}")
                _localhost_logged = True
            return True
        else:
            current_app.logger.debug(f"[DEV-REJECT] Menolak IP localhost karena NETWORK_ALLOW_LOCALHOST=False.")
            return False
    
    if ip in proxy_ips:
        # Log throttling untuk proxy rejections
        global _proxy_reject_logs
        if ip not in _proxy_reject_logs:
            current_app.logger.debug(f"[PROXY-REJECT] Menolak IP '{ip}' karena ada di daftar NETWORK_PROXY_IPS.")
            _proxy_reject_logs.add(ip)
        return False
    
    # ✅ REDUCE LOG: Hanya log sekali per IP per session
    global _accepted_ips
    if ip not in _accepted_ips:
        current_app.logger.info(f"[CLIENT-ACCEPT] Menerima IP client dinamis yang valid: {ip}")
        _accepted_ips.add(ip)
    return True

def is_valid_mac(mac: str) -> bool:
    """Validasi format MAC address yang lebih ketat."""
    if not mac or not isinstance(mac, str):
        return False
    
    mac_pattern = re.compile(r'^([0-9A-F]{2}[:-]){5}([0-9A-F]{2})$')
    return bool(mac_pattern.match(mac.upper()))

# Helper functions for backward compatibility
def is_valid_ip(ip: str) -> bool:
    """Alias untuk is_valid_ip_format untuk backward compatibility."""
    return is_valid_ip_format(ip)

def is_valid_client_ip_for_hotspot(ip: str) -> bool:
    """
    Backward compatibility wrapper untuk fungsi lama.
    Menggunakan konfigurasi dinamis dari current_app.config.
    """
    proxy_ips = current_app.config.get('NETWORK_PROXY_IPS', [])
    allow_localhost = current_app.config.get('NETWORK_ALLOW_LOCALHOST', True)
    return is_valid_client_ip(ip, proxy_ips, allow_localhost)

def is_captive_browser_request() -> bool:
    """
    Deteksi apakah request berasal dari captive browser.
    """
    # Check for captive portal markers
    referer = request.headers.get('Referer', '')
    user_agent = request.headers.get('User-Agent', '')
    
    # URL parameter indicators
    has_captive_params = bool(
        request.args.get('client_ip') or 
        request.args.get('client_mac') or 
        'captive' in referer.lower()
    )
    
    # User agent indicators
    captive_ua_markers = [
        'CaptiveNetworkSupport',
        'wispr',
        'CaptivePortalLogin'
    ]
    
    has_captive_ua = any(marker in user_agent for marker in captive_ua_markers)
    
    return has_captive_params or has_captive_ua