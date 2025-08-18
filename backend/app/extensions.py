# backend/app/extensions.py
# VERSI FINAL: Memastikan Celery memiliki akses ke semua layanan yang diperlukan.

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from celery import Celery

# Impor komponen yang perlu diinisialisasi
from app.infrastructure.gateways.mikrotik_pool import init_mikrotik_pool

# 1. Deklarasikan semua objek ekstensi di sini.
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
limiter = Limiter(key_func=get_remote_address)


# 2. Definisikan factory untuk Celery.
def make_celery(app: Flask) -> Celery:
    """Membuat instance Celery yang terkonfigurasi dengan konteks aplikasi Flask."""
    celery = Celery(
        app.import_name,
        include=['app.tasks']  # Pastikan tasks di-load oleh worker
    )
    celery.config_from_object(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery

# 3. Definisikan factory untuk membuat "app" khusus untuk Celery.
def create_flask_app_for_celery() -> Flask:
    """Membuat aplikasi Flask sementara khusus untuk inisialisasi konteks Celery."""
    app = Flask('hotspot_app_celery_init')
    config_name = os.getenv('FLASK_CONFIG', 'default')
    
    # Impor konfigurasi dinamis
    from config import config_options, Config
    app.config.from_object(config_options.get(config_name, Config()))

    # --- [PERBAIKAN KUNCI] ---
    # Inisialisasi SEMUA ekstensi yang dibutuhkan oleh Celery tasks
    # dengan aplikasi sementara ini.
    db.init_app(app)
    init_mikrotik_pool(app) # Ini adalah baris yang hilang dan krusial.
    # --- [AKHIR PERBAIKAN KUNCI] ---

    return app

# 4. Jalankan factory untuk membuat app dan celery yang siap pakai.
# Objek-objek ini akan diimpor oleh worker Celery dan file konfigurasi utama.
flask_for_celery = create_flask_app_for_celery()
celery_app = make_celery(flask_for_celery)