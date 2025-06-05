# backend/app/utils/request_utils.py
from flask import request, current_app
from typing import Optional

def get_client_ip() -> Optional[str]:
    """
    Mendapatkan IP klien asli. ProxyFix seharusnya sudah mengatur request.remote_addr
    dengan benar jika header X-Forwarded-For ada dan dipercaya.
    Fungsi ini menambahkan logging untuk diagnosis.
    """
    if not current_app:
        # Fallback logging jika current_app tidak tersedia (seharusnya tidak terjadi dalam endpoint)
        print("WARNING: current_app not available in get_client_ip. Logging to stdout.")
        # Membuat logger dummy sederhana jika current_app.logger tidak tersedia
        class DummyLogger:
            def debug(self, msg): print(f"DEBUG: {msg}")
            def warning(self, msg): print(f"WARNING: {msg}")
            def info(self, msg): print(f"INFO: {msg}")
            def error(self, msg): print(f"ERROR: {msg}")
        logger = DummyLogger()
    else:
        logger = current_app.logger

    # Koreksi pada baris f-string: Gunakan tanda kutip ganda untuk string di dalam getattr
    request_id_environ_key = 'FLASK_REQUEST_ID' # Variabel untuk kejelasan
    request_id = getattr(request.environ, 'get', lambda k, d: d)(request_id_environ_key, 'N/A')
    logger.debug(f"--- IP Detection (utils): Headers for request_id: {request_id} ---")

    for header, value in request.headers.items():
        if header.lower().startswith('x-forwarded') or \
           header.lower() in ['x-real-ip', 'remote_addr', 'host', 'user-agent', 'cf-connecting-ip']: # Tambahkan CF-Connecting-IP
            logger.debug(f"Header: {header} = {value}")

    # Prioritaskan header yang lebih spesifik jika ada (misalnya Cloudflare)
    client_ip = request.headers.get('CF-Connecting-IP')
    if client_ip:
        logger.debug(f"IP determined from CF-Connecting-IP header: {client_ip}")
        return client_ip

    # Jika tidak ada header Cloudflare, gunakan request.remote_addr yang sudah diproses ProxyFix
    client_ip = request.remote_addr
    logger.debug(f"IP determined by request.remote_addr (post-ProxyFix): {client_ip}")

    # Log tambahan untuk X-Forwarded-For jika ada, untuk perbandingan
    if 'X-Forwarded-For' in request.headers:
        logger.debug(f"Raw X-Forwarded-For header value: {request.headers.get('X-Forwarded-For')}")
    else:
        logger.debug("X-Forwarded-For header NOT present.")
        
    if not client_ip: # Fallback jika remote_addr None (seharusnya jarang terjadi setelah ProxyFix)
        logger.warning("request.remote_addr is None. Falling back to X-Real-IP or direct request.environ.get('REMOTE_ADDR').")
        client_ip = request.headers.get('X-Real-IP', request.environ.get('REMOTE_ADDR'))
        if client_ip:
            logger.debug(f"IP determined from X-Real-IP or direct environ: {client_ip}")
        else:
            logger.warning("Could not determine client IP from any known headers or remote_addr.")
            
    return client_ip