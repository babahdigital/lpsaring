"""
Quick-fix module for ARP warming implementation
Moved from app/utils/ip_mac_warming.py to isolate functionality
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

def setup_arp_warming(app):
    """
    Setup ARP warming with better error handling and immediate teardown registration
    """
    logger.info("[ARP-WARMING] Setting up ARP warming")
    
    if not app.config.get('ENABLE_ARP_WARMING', True):
        logger.info("[ARP-WARMING] ARP warming disabled in config")
        return False
    
    try:
        # Register teardown handler immediately - this is critical
        # This will ensure teardown is registered before any requests happen
        from app.utils.ip_mac_warming import stop_warming_thread
        
        @app.teardown_appcontext
        def shutdown_warming_on_teardown(exception=None):
            logger.debug("[ARP-WARMING] Teardown handler called")
            try:
                stop_warming_thread()
                logger.info("[ARP-WARMING] Stopped warming thread in teardown handler")
            except Exception as e:
                logger.warning(f"[ARP-WARMING] Error in teardown: {str(e)}")
        
        logger.info("[ARP-WARMING] Teardown handler registered successfully")
        
        # Start a background thread that will run once app context is established
        def delayed_start():
            logger.info("[ARP-WARMING] Delayed initialization starting")
            time.sleep(5)  # Wait 5 seconds for app to fully initialize
            
            try:
                with app.app_context():
                    from app.utils.ip_mac_warming import start_warming_thread
                    start_warming_thread()
                    logger.info("[ARP-WARMING] Successfully initialized ARP warming system")
            except Exception as e:
                logger.error(f"[ARP-WARMING] Failed to initialize: {str(e)}")
        
        # Create and start the thread
        thread = threading.Thread(target=delayed_start, daemon=True)
        thread.start()
        logger.info("[ARP-WARMING] Started ARP warming initialization thread")
        return True
    except Exception as e:
        logger.error(f"[ARP-WARMING] Failed to setup ARP warming: {str(e)}")
        return False
