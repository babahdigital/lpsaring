# backend/app/infrastructure/http/__init__.py

from flask import Flask

def register_blueprints(app: Flask):
    """Fungsi Koordinator: Mengimpor dan mendaftarkan semua blueprint dari aplikasi."""

    # === Impor Semua Blueprint dari file-filenya ===
    from .auth_routes import auth_bp
    from .packages_routes import packages_bp
    from .transactions_routes import transactions_bp
    from .public_routes import public_bp
    from .public_promo_routes import public_promo_bp
    from .public_user_routes import public_user_bp
    
    # Import WebSocket blueprint if available
    try:
        from .websocket_routes import websocket_bp
    except ImportError:
        websocket_bp = None
    
    # Impor User-specific Blueprints
    from .user.profile_routes import profile_bp
    from .user.data_routes import data_bp

    # Impor blueprint dashboard
    from .dashboard_routes import dashboard_bp

    # Impor Komandan Blueprints
    from .komandan.komandan_routes import komandan_bp
    
    # Impor Admin Blueprints
    from .admin.user_management_routes import user_management_bp
    from .admin.package_management_routes import package_management_bp
    from .admin.settings_routes import settings_management_bp
    from .admin.profile_management_routes import profile_management_bp
    from .admin.promo_management_routes import promo_management_bp
    from .admin.request_management_routes import request_mgmt_bp
    from .admin.action_log_routes import action_log_bp


    # === Daftarkan Semua Blueprint dengan Prefix yang Benar ===
    
    # Prefix untuk API publik, user, dan umum
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(packages_bp, url_prefix='/api/packages')
    app.register_blueprint(transactions_bp, url_prefix='/api/transactions')
    
    # [PERBAIKAN] Mengubah prefix agar URL menjadi /api/public, bukan /api/settings/public
    app.register_blueprint(public_bp, url_prefix='/api')
    
    app.register_blueprint(public_promo_bp, url_prefix='/api/public/promos')
    app.register_blueprint(public_user_bp, url_prefix='/api/users') 

    # Prefix untuk data spesifik pengguna yang sudah login (/api/users/me/...)
    user_me_prefix = '/api/users'
    
    # Register WebSocket blueprint if available
    if websocket_bp:
        app.register_blueprint(websocket_bp, url_prefix='/api/ws')
    app.register_blueprint(profile_bp, url_prefix=user_me_prefix)
    app.register_blueprint(data_bp, url_prefix=user_me_prefix)
    
    # Daftarkan blueprint dashboard PENGGUNA dengan prefix yang benar (/api/dashboard).
    app.register_blueprint(dashboard_bp, url_prefix='/api/dashboard')

    # Prefix untuk API Komandan
    app.register_blueprint(komandan_bp, url_prefix='/api/komandan')

    if app.config.get('ENABLE_ADMIN_ROUTES', True):
        ADMIN_API_PREFIX = '/api/admin'
        
        app.register_blueprint(user_management_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(package_management_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(settings_management_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(profile_management_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(promo_management_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(request_mgmt_bp, url_prefix=ADMIN_API_PREFIX)
        app.register_blueprint(action_log_bp, url_prefix=ADMIN_API_PREFIX)

    @app.get('/healthz')
    def healthz():
        """Endpoint sederhana untuk memeriksa kesehatan aplikasi."""
        return {"status": "ok"}, 200

    @app.get('/readyz')
    def readyz():
        """Readiness probe: cek konektivitas komponen penting (DB, Redis)."""
        status = {"status": "ok", "dependencies": {}}
        code = 200
        # Cek database (SQLAlchemy) jika tersedia di app.extensions
        db = app.extensions.get('sqlalchemy') if hasattr(app, 'extensions') else None
        if db:
            try:  # type: ignore
                with app.app_context():
                    db.session.execute(db.text('SELECT 1'))  # type: ignore
                status['dependencies']['db'] = 'ok'
            except Exception as e:  # noqa: BLE001
                status['dependencies']['db'] = f'error: {e.__class__.__name__}'
                code = 503
        else:
            status['dependencies']['db'] = 'unavailable'
        # Cek Redis jika terdaftar di app.extensions (misal menggunakan redis client di extensions)
        redis_client = getattr(app, 'redis_client', None)
        if redis_client:
            try:
                pong = redis_client.ping()
                status['dependencies']['redis'] = 'ok' if pong else 'no-pong'
                if not pong:
                    code = 503
            except Exception as e:  # noqa: BLE001
                status['dependencies']['redis'] = f'error: {e.__class__.__name__}'
                code = 503
        else:
            status['dependencies']['redis'] = 'unavailable'
        return status, code