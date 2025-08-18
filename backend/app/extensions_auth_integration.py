# backend/app/extensions_auth_integration.py
"""
Extension untuk menambahkan auth optimization ke extensions.py yang sudah ada
File ini bisa di-import dari extensions.py utama
"""

import logging
import time
from typing import Optional
from flask import Flask

logger = logging.getLogger(__name__)

def init_auth_optimization(app: Flask, celery_app) -> bool:
    """
    Initialize auth optimization components
    Dipanggil dari extensions.py setelah Celery setup
    """
    try:
        # Import services (lazy import untuk menghindari circular dependency)
        from app.services.scheduler_integration import integrate_with_extensions
        
        # Integrate dengan Celery
        success = integrate_with_extensions(celery_app)
        
        if success:
            logger.info("[AUTH-INIT] Auth optimization initialized successfully")
        else:
            logger.warning("[AUTH-INIT] Auth optimization initialization had issues")
        
        return success
        
    except Exception as e:
        logger.error(f"[AUTH-INIT] Failed to initialize auth optimization: {e}")
        return False

def register_auth_blueprints(app: Flask) -> bool:
    """
    Register auth optimization blueprints
    """
    try:
        # Import dan register optimized auth routes
        from app.infrastructure.http.auth_routes import auth_bp
        
        # Register blueprint (sudah ada url_prefix di blueprint definition)
        app.register_blueprint(auth_bp)
        
        logger.info("[AUTH-BLUEPRINT] Auth optimization blueprints registered at /auth")
        return True
        
    except Exception as e:
        logger.error(f"[AUTH-BLUEPRINT] Failed to register auth blueprints: {e}")
        return False

def setup_auth_monitoring(app: Flask) -> bool:
    """
    Setup monitoring endpoints untuk auth optimization
    """
    try:
        @app.route('/health/auth', methods=['GET'])
        def auth_health_check():
            """Health check endpoint untuk auth system"""
            from flask import jsonify
            from app.services.auth_session_service import AuthSessionService
            
            try:
                stats = AuthSessionService.get_session_stats()
                return jsonify({
                    "status": "healthy",
                    "auth_stats": stats,
                    "timestamp": time.time()
                }), 200
            except Exception as e:
                return jsonify({
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": time.time()
                }), 500
        
        @app.route('/admin/auth/clear-cache', methods=['POST'])
        def clear_auth_cache():
            """Admin endpoint untuk clear auth cache"""
            from flask import jsonify, request
            from app.services.client_detection_service import ClientDetectionService
            
            try:
                client_ip = request.args.get('ip')
                client_mac = request.args.get('mac')
                
                ClientDetectionService.clear_cache(client_ip, client_mac)
                
                return jsonify({
                    "status": "success",
                    "message": "Auth cache cleared",
                    "cleared_for": {"ip": client_ip, "mac": client_mac}
                }), 200
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": str(e)
                }), 500
        
        logger.info("[AUTH-MONITORING] Auth monitoring endpoints setup")
        return True
        
    except Exception as e:
        logger.error(f"[AUTH-MONITORING] Failed to setup auth monitoring: {e}")
        return False

# Template untuk modifikasi extensions.py
"""
Tambahkan ini ke extensions.py yang sudah ada:

# Di bagian import
from app.extensions_auth_integration import (
    init_auth_optimization,
    register_auth_blueprints, 
    setup_auth_monitoring
)

# Setelah celery setup dalam create_flask_app_for_celery()
def create_flask_app_for_celery():
    app = create_app()
    
    # ... existing code ...
    
    # Tambahkan auth optimization setelah celery setup
    celery_app = make_celery(app)
    init_auth_optimization(app, celery_app)
    register_auth_blueprints(app)
    setup_auth_monitoring(app)
    
    return app

# Atau dalam app factory jika menggunakan pattern lain
def create_app():
    app = Flask(__name__)
    
    # ... existing extensions initialization ...
    
    # Initialize Celery
    celery_app = make_celery(app)
    
    # Initialize auth optimization
    init_auth_optimization(app, celery_app)
    register_auth_blueprints(app)
    setup_auth_monitoring(app)
    
    return app
"""
