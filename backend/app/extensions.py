# backend/app/extensions.py
# VERSI DISEMPURNAKAN

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# Tidak perlu import redis di sini lagi

# Hanya buat instance di sini
db = SQLAlchemy()
migrate = Migrate()
cors = CORS()
limiter = Limiter(
    key_func=get_remote_address,
    # Konfigurasi default limits dan storage akan diambil dari app.config saat init_app
)

# Tidak perlu instance Redis atau fungsi init_extensions di sini lagi
# karena ditangani di app/__init__.py