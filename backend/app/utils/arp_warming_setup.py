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
    Setup ARP warming with better error handling and long-running thread support
    """
    logger.info("[ARP-WARMING] Setting up ARP warming")
    
    if not app.config.get('ENABLE_ARP_WARMING', True):
        logger.info("[ARP-WARMING] ARP warming disabled in config")
        return False
    
    try:
        # Import necessary functions
        import atexit
        from app.utils.ip_mac_warming import stop_warming_thread
        
        # This teardown handler no longer stops the warming thread after each request
        @app.teardown_appcontext
        def shutdown_warming_on_teardown(exception=None):
            logger.debug("[ARP-WARMING] Teardown handler called")
            # We don't stop the warming thread here anymore
            # Just log that teardown was called to keep track
            pass
        
        # Register the stop_warming_thread function to be called when the application exits
        atexit.register(stop_warming_thread)
        
        logger.info("[ARP-WARMING] Teardown handler modified: thread will remain running between requests")
        
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
