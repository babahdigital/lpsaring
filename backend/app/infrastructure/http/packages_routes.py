# backend/app/infrastructure/http/packages_routes.py

from flask import Blueprint, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from decimal import Decimal # Import Decimal untuk memeriksa tipe

from app.extensions import db
from app.infrastructure.db.models import Package
from .schemas.package_schemas import PackagePublic # Pastikan import dari path yang benar

# Definisikan Blueprint
packages_bp = Blueprint('packages_api', __name__, url_prefix='/api/packages')

@packages_bp.route('', methods=['GET'])
def get_packages():
    """
    Endpoint untuk mengambil daftar semua paket hotspot yang aktif.
    Mengembalikan daftar paket dalam format JSON {success: bool, data: [], message?: string}.
    """
    current_app.logger.info("GET /api/packages endpoint requested")
    try:
        # Query database: Ambil paket aktif, urutkan berdasarkan harga
        packages_db = db.session.query(Package)\
            .filter(Package.is_active == True)\
            .order_by(Package.price)\
            .all()

        count = len(packages_db)
        current_app.logger.info(f"Retrieved {count} active packages from database.")

        # --- MULAI LOGGING KRUSIAL ---
        # Log ini akan menunjukkan nilai price SEBELUM diproses Pydantic
        if count > 0:
            current_app.logger.debug("--- Inspecting Package Objects from DB Query ---")
            for idx, pkg_obj in enumerate(packages_db):
                # Coba akses atribut 'price', beri nilai default jika tidak ada
                price_value = getattr(pkg_obj, 'price', 'ATTRIBUTE_NOT_FOUND')
                # Dapatkan nama tipe data dari nilai price
                price_type_name = type(price_value).__name__ if price_value != 'ATTRIBUTE_NOT_FOUND' else 'N/A'
                current_app.logger.debug(
                    f"  Package {idx + 1}: "
                    f"ID={pkg_obj.id}, "
                    f"Name='{pkg_obj.name}', "
                    # Tampilkan nilai mentah yang didapat dari SQLAlchemy
                    f"Price_Raw_Value={repr(price_value)}, "
                    # Tampilkan tipe data nilai tersebut (Harusnya Decimal)
                    f"Price_Raw_Type={price_type_name}"
                )
            current_app.logger.debug("--- End Inspecting Package Objects ---")
        else:
             current_app.logger.debug("No active packages found in DB to inspect.")
        # --- SELESAI LOGGING KRUSIAL ---

        # Serialisasi menggunakan Pydantic (setelah logging)
        try:
            # Ubah list objek SQLAlchemy menjadi list objek Pydantic
            # Pydantic akan validasi & konversi tipe sesuai skema PackagePublic
            packages_validated = [PackagePublic.model_validate(pkg) for pkg in packages_db]

            # Ubah objek Pydantic menjadi list of dicts (siap untuk JSON)
            # Pydantic akan konversi price (int di skema) menjadi number JSON
            packages_list = [pkg.model_dump(mode='json') for pkg in packages_validated]

            current_app.logger.debug(f"Successfully serialized {len(packages_list)} packages using Pydantic.")
            # Optional: Log data yang akan dikirim jika masih bermasalah
            # current_app.logger.debug(f"Data being sent to frontend: {packages_list}")

            # --- Struktur Respons Konsisten ---
            return jsonify({
                "success": True,
                "data": packages_list,
                "message": "Paket berhasil diambil." if count > 0 else "Tidak ada paket aktif yang tersedia saat ini."
            }), 200
            # -----------------------------------

        # Tangkap error spesifik Pydantic (jika perlu, tapi Exception umum cukup)
        # except ValidationError as validation_error:
        #     current_app.logger.error(f"Pydantic validation error: {validation_error.errors()}", exc_info=True)
        #     return jsonify({"success": False, "message": "Data paket tidak valid.", "errors": validation_error.errors()}), 400
        except Exception as validation_or_serialization_error: # Tangkap potensi error Pydantic/lainnya
            current_app.logger.error(f"Pydantic validation/serialization error: {validation_or_serialization_error}", exc_info=True)
            return jsonify({"success": False, "message": "Gagal memproses data paket.", "error": str(validation_or_serialization_error)}), 500

    except SQLAlchemyError as e:
        # Log error database dengan traceback
        current_app.logger.error(f"Database error fetching packages: {e}", exc_info=True)
        # Kirim respons error ke client
        return jsonify({"success": False, "message": "Gagal mengambil data paket dari database.", "error": str(e)}), 500
    except Exception as e:
        # Log error tak terduga lainnya
        current_app.logger.error(f"Unexpected error in get_packages: {e}", exc_info=True)
        # Kirim respons error umum ke client
        return jsonify({"success": False, "message": "Terjadi kesalahan internal pada server.", "error": str(e)}), 500

# --- Rute lain bisa ditambahkan di bawah ini ---