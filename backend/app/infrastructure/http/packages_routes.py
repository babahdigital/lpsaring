# backend/app/infrastructure/http/packages_routes.py
# VERSI: Disesuaikan dengan nama field baru di model dan skema paket.
# PERBAIKAN: Mengatasi RuntimeError dan memastikan pemuatan Package.profile.
# PERBAIKAN FINAL: Menambahkan import HTTPStatus untuk mengatasi NameError.

from flask import Blueprint, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload # Import selectinload
from decimal import Decimal
from typing import Optional, Any, Dict, List # Import List
from http import HTTPStatus # <--- PERBAIKAN DI SINI

from app.extensions import db

# Flag untuk ketersediaan model, hindari akses current_app di luar konteks
MODELS_AVAILABLE = False
try:
    from app.infrastructure.db.models import Package, PackageProfile # Import PackageProfile
    MODELS_AVAILABLE = True
except ImportError as e:
    print(f"CRITICAL ERROR (packages_routes): Gagal mengimpor model: {e}")
    # Definisi placeholder untuk menghindari NameError
    class Package(object): # type: ignore
        id: Any
        name: str
        price: Decimal
        description: Optional[str]
        is_active: bool
        profile_id: Any
        profile: Any # Harus ada jika diakses
        speed_limit_kbps: Optional[int]
        data_quota_gb: float
        duration_days: int
    class PackageProfile(object): # type: ignore
        profile_name: str
        data_quota_gb: float
        duration_days: int

from .schemas.package_schemas import PackagePublic

packages_bp = Blueprint('packages_api', __name__, url_prefix='/api/packages')

@packages_bp.route('', methods=['GET'])
def get_packages():
    """
    Endpoint untuk mengambil daftar semua paket hotspot yang aktif.
    """
    current_app.logger.info("GET /api/packages endpoint requested")
    if not MODELS_AVAILABLE or not hasattr(db, 'session'):
        return jsonify({"success": False, "message": "Kesalahan konfigurasi server (model/database)."}), HTTPStatus.SERVICE_UNAVAILABLE
    try:
        packages_db = db.session.query(Package)\
            .options(selectinload(Package.profile))\
            .filter(Package.is_active == True)\
            .order_by(Package.price)\
            .all()
        count = len(packages_db)
        current_app.logger.info(f"Retrieved {count} active packages from database.")

        if count > 0:
            current_app.logger.debug("--- Inspecting Package Objects from DB Query ---")
            for idx, pkg_obj in enumerate(packages_db):
                # PERBAIKAN: Sesuaikan logging dengan struktur model baru
                quota_gb_value = getattr(pkg_obj, 'data_quota_gb', 'ATTR_NOT_FOUND')
                duration_days_value = getattr(pkg_obj, 'duration_days', 'ATTR_NOT_FOUND')
                current_app.logger.debug(
                    f"  Package {idx + 1}: Name='{pkg_obj.name}', "
                    f"QuotaGB={repr(quota_gb_value)}, "
                    f"DurationDays={repr(duration_days_value)}"
                )
            current_app.logger.debug("--- End Inspecting Package Objects ---")

        packages_validated = [PackagePublic.model_validate(pkg) for pkg in packages_db]
        packages_list = [pkg.model_dump(mode='json') for pkg in packages_validated]
        
        return jsonify({
            "success": True,
            "data": packages_list,
            "message": "Paket berhasil diambil." if count > 0 else "Tidak ada paket aktif yang tersedia saat ini."
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_packages: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Terjadi kesalahan internal pada server.", "error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR