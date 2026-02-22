# backend/app/utils/request_utils.py
from flask import request, current_app
from typing import Optional
import ipaddress


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
            def debug(self, msg):
                print(f"DEBUG: {msg}")

            def warning(self, msg):
                print(f"WARNING: {msg}")

            def info(self, msg):
                print(f"INFO: {msg}")

            def error(self, msg):
                print(f"ERROR: {msg}")

        logger = DummyLogger()
    else:
        logger = current_app.logger

    # Koreksi pada baris f-string: Gunakan tanda kutip ganda untuk string di dalam getattr
    request_id_environ_key = "FLASK_REQUEST_ID"  # Variabel untuk kejelasan
    request_id = getattr(request.environ, "get", lambda k, d: d)(request_id_environ_key, "N/A")
    if current_app and current_app.config.get("LOG_IP_HEADER_DEBUG", False):
        logger.debug(f"--- IP Detection (utils): Headers for request_id: {request_id} ---")
        for header, value in request.headers.items():
            if header.lower().startswith("x-forwarded") or header.lower() in [
                "x-real-ip",
                "remote_addr",
                "host",
                "user-agent",
                "cf-connecting-ip",
            ]:
                logger.debug(f"Header: {header} = {value}")

    def _is_trusted_proxy(ip_value: Optional[str]) -> bool:
        if not ip_value:
            return False
        trusted = current_app.config.get("TRUSTED_PROXY_CIDRS", []) if current_app else []
        try:
            ip_obj = ipaddress.ip_address(ip_value)
        except ValueError:
            return False
        for cidr in trusted:
            try:
                if ip_obj in ipaddress.ip_network(cidr, strict=False):
                    return True
            except ValueError:
                continue
        return False

    # Prioritaskan header yang lebih spesifik jika dipercaya (misalnya Cloudflare)
    client_ip = request.headers.get("CF-Connecting-IP")
    if client_ip and current_app and current_app.config.get("TRUST_CF_CONNECTING_IP", False):
        if _is_trusted_proxy(request.remote_addr):
            logger.debug(f"IP determined from CF-Connecting-IP header: {client_ip}")
            return client_ip
        logger.warning("CF-Connecting-IP diabaikan karena remote_addr tidak trusted.")

    x_forwarded_for = request.headers.get("X-Forwarded-For")
    log_ip_info = bool(
        current_app
        and (current_app.config.get("LOG_BINDING_DEBUG", False) or current_app.config.get("LOG_IP_HEADER_DEBUG", False))
    )
    if log_ip_info:
        logger.info(f"X-Forwarded-For header: {x_forwarded_for}")
    if x_forwarded_for:
        logger.debug(f"Raw X-Forwarded-For header value: {x_forwarded_for}")
        if _is_trusted_proxy(request.remote_addr):
            for part in x_forwarded_for.split(","):
                candidate = part.strip()
                if not candidate:
                    continue
                try:
                    ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                logger.debug(f"IP determined from X-Forwarded-For header: {candidate}")
                if log_ip_info:
                    logger.info(f"IP determined: source=X-Forwarded-For ip={candidate}")
                return candidate
            logger.warning("X-Forwarded-For present but no valid IPs found.")
    else:
        logger.debug("X-Forwarded-For header NOT present.")

    # Jika tidak ada header Cloudflare atau X-Forwarded-For yang valid, gunakan request.remote_addr
    client_ip = request.remote_addr
    logger.debug(f"IP determined by request.remote_addr (post-ProxyFix): {client_ip}")
    if log_ip_info:
        logger.info(f"IP determined: source=remote_addr ip={client_ip}")

    if not client_ip:  # Fallback jika remote_addr None (seharusnya jarang terjadi setelah ProxyFix)
        logger.warning(
            "request.remote_addr is None. Falling back to X-Real-IP or direct request.environ.get('REMOTE_ADDR')."
        )
        client_ip = request.headers.get("X-Real-IP", request.environ.get("REMOTE_ADDR"))
        if client_ip:
            logger.debug(f"IP determined from X-Real-IP or direct environ: {client_ip}")
            if log_ip_info:
                logger.info(f"IP determined: source=x-real-ip ip={client_ip}")
        else:
            logger.warning("Could not determine client IP from any known headers or remote_addr.")

    return client_ip
