# backend/app/infrastructure/http/packages_routes.py
# VERSI: Disesuaikan dengan nama field baru di model dan skema paket.

from flask import Blueprint, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import Package
from .schemas.package_schemas import PackagePublic

packages_bp = Blueprint('packages_api', __name__, url_prefix='/api/packages')

@packages_bp.route('', methods=['GET'])
def get_packages():
    """
    Endpoint untuk mengambil daftar semua paket hotspot yang aktif.
    Mengembalikan daftar paket dalam format JSON {success: bool, data: [], message?: string}.
    """
    current_app.logger.info("GET /api/packages endpoint requested")
    try:
        packages_db = db.session.query(Package)\
            .filter(Package.is_active == True)\
            .order_by(Package.price)\
            .all()

        count = len(packages_db)
        current_app.logger.info(f"Retrieved {count} active packages from database.")

        if count > 0:
            current_app.logger.debug("--- Inspecting Package Objects from DB Query ---")
            for idx, pkg_obj in enumerate(packages_db):
                price_value = getattr(pkg_obj, 'price', 'ATTRIBUTE_NOT_FOUND')
                price_type_name = type(price_value).__name__
                # Log field baru
                quota_gb_value = getattr(pkg_obj, 'data_quota_gb', 'ATTRIBUTE_NOT_FOUND')
                quota_gb_type = type(quota_gb_value).__name__
                
                current_app.logger.debug(
                    f"  Package {idx + 1}: ID={pkg_obj.id}, Name='{pkg_obj.name}', "
                    f"Price_Raw={repr(price_value)} (Type: {price_type_name}), "
                    f"QuotaGB_Raw={repr(quota_gb_value)} (Type: {quota_gb_type})"
                )
            current_app.logger.debug("--- End Inspecting Package Objects ---")
        else:
             current_app.logger.debug("No active packages found in DB to inspect.")

        try:
            packages_validated = [PackagePublic.model_validate(pkg) for pkg in packages_db]
            packages_list = [pkg.model_dump(mode='json') for pkg in packages_validated]
            current_app.logger.debug(f"Successfully serialized {len(packages_list)} packages using Pydantic.")
            
            return jsonify({
                "success": True,
                "data": packages_list,
                "message": "Paket berhasil diambil." if count > 0 else "Tidak ada paket aktif yang tersedia saat ini."
            }), 200

        except Exception as validation_or_serialization_error:
            current_app.logger.error(f"Pydantic validation/serialization error: {validation_or_serialization_error}", exc_info=True)
            return jsonify({"success": False, "message": "Gagal memproses data paket.", "error": str(validation_or_serialization_error)}), 500

    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error fetching packages: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal mengambil data paket dari database.", "error": str(e)}), 500
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_packages: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Terjadi kesalahan internal pada server.", "error": str(e)}), 500