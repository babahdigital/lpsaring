# backend/app/infrastructure/gateways/mikrotik_pool.py
# pyright: reportAttributeAccessIssue=false

import logging
from flask import Flask
from routeros_api import RouterOsApiPool
from routeros_api.exceptions import RouterOsApiConnectionError

logger = logging.getLogger(__name__)

def init_mikrotik_pool(app: Flask):
    """
    Menginisialisasi RouterOS API connection pool dan menyimpannya di app context.
    Dipanggil saat aplikasi Flask dibuat.
    """
    required_configs = [
        'MIKROTIK_HOST',
        'MIKROTIK_USERNAME',
        'MIKROTIK_PASSWORD'
    ]
    
    for config in required_configs:
        if not app.config.get(config):
            logger.warning(
                f"Konfigurasi '{config}' tidak ditemukan. "
                "MikroTik API Pool tidak akan diinisialisasi."
            )
            app.mikrotik_api_pool = None
            return

    try:
        host = app.config['MIKROTIK_HOST']
        username = app.config['MIKROTIK_USERNAME']
        password = app.config['MIKROTIK_PASSWORD']
        port = app.config.get('MIKROTIK_PORT', 8728)
        
        # --- [PERBAIKAN UTAMA] ---
        # Gunakan konfigurasi SSL dan Plaintext Login dari app.config
        use_ssl = app.config.get('MIKROTIK_USE_SSL', False)
        plaintext_login = app.config.get('MIKROTIK_PLAIN_TEXT_LOGIN', True)
        
        logger.info(f"Mencoba menginisialisasi MikroTik API Pool untuk host: {host}:{port} (SSL: {use_ssl})")

        pool = RouterOsApiPool(
            host=host,
            username=username,
            password=password,
            port=port,
            use_ssl=use_ssl,
            plaintext_login=plaintext_login
        )
        # --- [AKHIR PERBAIKAN] ---
        
        app.mikrotik_api_pool = pool
        
        logger.info("MikroTik API Pool berhasil diinisialisasi.")

    except RouterOsApiConnectionError as e:
        logger.error(f"Gagal terhubung ke MikroTik saat inisialisasi pool: {e}", exc_info=True)
        app.mikrotik_api_pool = None
    except Exception as e:
        logger.error(f"Error tak terduga saat inisialisasi MikroTik API Pool: {e}", exc_info=True)
        app.mikrotik_api_pool = None