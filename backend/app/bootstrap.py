# backend/app/bootstrap.py
"""
Aplikasi bootstrapper untuk inisialisasi fitur dan integrasi
"""
import logging
import time
from typing import Optional

from flask import Flask, current_app

logger = logging.getLogger(__name__)

def init_app_components(app: Flask) -> None:
    """
    Initialize application components that need to be bootstrapped after app creation
    but before first request
    """
    logger.info("Initializing application components...")
    
    # Initialize WebSockets if available
    try:
        # First check if flask-sock is installed
        import flask_sock  # type: ignore # pylance-disable
        from app.infrastructure.http.websocket_routes import sock
        
        # Register Sock extension with app
        logger.info("Initializing WebSocket support with Flask-Sock extension")
        sock.init_app(app)
        logger.info("WebSocket support enabled and initialized successfully")
    except ImportError as e:
        logger.warning(f"WebSocket support not available (flask-sock not installed)")
    except Exception as e:
        logger.error(f"Failed to initialize WebSockets: {str(e)}")
        import traceback
        logger.debug(f"WebSocket initialization error details: {traceback.format_exc()}")
    
    # Initialize ARP Warming if enabled in config
    try:
        logger.info("Initializing ARP warming system")
        # Use our safer wrapper function
        from app.utils.arp_warming_setup import setup_arp_warming
        if setup_arp_warming(app):
            logger.info("ARP warming system initialization started")
        else:
            logger.warning("ARP warming system initialization skipped")
    except Exception as e:
        logger.error(f"Failed to initialize ARP warming: {str(e)}")
        import traceback
        logger.debug(f"ARP warming initialization error details: {traceback.format_exc()}")
        
    # Register MikroTik connection cleanup with Flask teardown
    try:
        logger.info("Registering MikroTik connection cleanup handlers")
        
        @app.teardown_appcontext
        def cleanup_mikrotik_app_context(exception=None):
            """Clean up MikroTik connections in app context"""
            # This is just a placeholder for context cleanup if needed
            # Main cleanup is handled by atexit handler in mikrotik_client_impl.py
            mikrotik_pool = getattr(current_app, "mikrotik_api_pool", None)
            if mikrotik_pool:
                logger.debug("[MT-CLEANUP] App context teardown, noted MikroTik connection")
            
        logger.info("MikroTik connection cleanup handlers registered")
    except Exception as e:
        logger.error(f"Failed to register MikroTik cleanup handlers: {str(e)}")
        import traceback
        logger.debug(f"MikroTik cleanup registration error details: {traceback.format_exc()}")
    
    # Clear cache if configured
    if app.config.get('CACHE_CLEAR_ON_START', True):
        logger.info("Clearing cache on startup")
        try:
            from app.utils.cache_manager import cache_manager
            cache_manager.clear_ip_mac_cache()
            logger.info("Cache cleared on startup")
        except Exception as e:
            logger.error(f"Failed to clear cache: {str(e)}")
            
    logger.info("Application components initialized")
