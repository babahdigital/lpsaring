# backend/app/infrastructure/http/admin/package_management_routes.py
# VERSI FINAL: Disesuaikan dengan nama profil 'user' untuk kuota.

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from http import HTTPStatus
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from typing import Optional
import uuid

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import Package, PackageProfile, Transaction, User
from app.infrastructure.http.decorators import admin_required
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, _is_profile_valid

# Definisi Blueprint
package_management_bp = Blueprint("package_management_api", __name__)


# --- Skema Pydantic untuk Paket ---
class ProfileSimpleSchema(BaseModel):
    id: uuid.UUID
    profile_name: str
    model_config = ConfigDict(from_attributes=True)


class PackageSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    price: int = Field(..., ge=0)
    is_active: bool = True
    profile_id: Optional[uuid.UUID] = None
    data_quota_gb: float = Field(..., ge=0)
    duration_days: int = Field(..., gt=0)
    profile: Optional[ProfileSimpleSchema] = None
    model_config = ConfigDict(from_attributes=True)


# --- Rute CRUD untuk Paket (Packages) ---
@package_management_bp.route("/packages", methods=["GET"])
@admin_required
def get_packages_list(current_admin: User):
    """Mengambil daftar paket jualan dengan paginasi."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("itemsPerPage", 10, type=int), 100)

        sort_by = (request.args.get("sortBy") or "created_at").strip()
        sort_order = (request.args.get("sortOrder") or "desc").strip().lower()
        is_asc = sort_order == "asc"

        sort_columns = {
            "created_at": Package.created_at,
            "name": Package.name,
            "price": Package.price,
            "data_quota_gb": Package.data_quota_gb,
            "duration_days": Package.duration_days,
            "is_active": Package.is_active,
        }
        sort_col = sort_columns.get(sort_by, Package.created_at)
        sort_expr = sort_col.asc() if is_asc else sort_col.desc()

        # Stable ordering: when primary sort ties, fall back to created_at desc.
        query = db.select(Package).options(selectinload(Package.profile)).order_by(sort_expr, Package.created_at.desc())
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        return jsonify(
            {
                "items": [PackageSchema.from_orm(p).model_dump() for p in pagination.items],
                "totalItems": pagination.total,
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error retrieving package list: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat daftar paket."}), HTTPStatus.INTERNAL_SERVER_ERROR


@package_management_bp.route("/packages", methods=["POST"])
@admin_required
def create_package(current_admin: User):
    """
    Membuat paket jualan baru, dengan logika pemilihan profil otomatis.
    - Paket dengan kuota (data_quota_gb > 0) akan menggunakan profil dari settings.
    - Paket unlimited (data_quota_gb == 0) akan menggunakan profil unlimited dari settings.
    """
    try:
        package_data = PackageSchema.model_validate(request.get_json())

        user_profile_name = (
            settings_service.get_setting("MIKROTIK_USER_PROFILE")
            or settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE")
            or "user"
        )
        unlimited_profile_name = settings_service.get_setting("MIKROTIK_UNLIMITED_PROFILE") or "unlimited"

        if package_data.data_quota_gb == 0:
            target_profile_name = unlimited_profile_name
        else:
            target_profile_name = user_profile_name

        current_app.logger.info(
            f"Membuat paket '{package_data.name}'. Mencari profil Mikrotik target: '{target_profile_name}'"
        )

        target_profile = db.session.scalar(db.select(PackageProfile).filter_by(profile_name=target_profile_name))

        if not target_profile:
            current_app.logger.warning(
                "Profil '%s' belum ada di database. Verifikasi ke Mikrotik...",
                target_profile_name,
            )
            with get_mikrotik_connection() as api:
                if not api:
                    error_message = (
                        "Tidak bisa menghubungi Mikrotik untuk verifikasi profil. Pastikan koneksi Mikrotik aktif."
                    )
                    current_app.logger.error(error_message)
                    return jsonify({"message": error_message}), HTTPStatus.CONFLICT
                is_valid, resolved_name = _is_profile_valid(api, target_profile_name)

            if not is_valid:
                error_message = (
                    f"Profil '{target_profile_name}' tidak ditemukan di Mikrotik. "
                    "Silakan buat profil tersebut di Mikrotik terlebih dahulu."
                )
                current_app.logger.critical(error_message)
                return jsonify({"message": error_message}), HTTPStatus.CONFLICT

            try:
                target_profile = PackageProfile()
                target_profile.profile_name = resolved_name
                db.session.add(target_profile)
                db.session.flush()
                current_app.logger.info(
                    "Profil '%s' dibuat otomatis di database dari Mikrotik.",
                    resolved_name,
                )
            except IntegrityError:
                db.session.rollback()
                target_profile = db.session.scalar(db.select(PackageProfile).filter_by(profile_name=resolved_name))
                if not target_profile:
                    error_message = f"Profil '{resolved_name}' gagal dibuat dan tidak ditemukan di database."
                    current_app.logger.error(error_message)
                    return jsonify({"message": error_message}), HTTPStatus.CONFLICT

        package_data.profile_id = target_profile.id

        new_package = Package(**package_data.model_dump(exclude={"id", "profile"}))
        db.session.add(new_package)
        db.session.commit()

        created_package = db.session.get(Package, new_package.id)
        if not created_package:
            current_app.logger.error("Paket baru tidak ditemukan setelah commit. package_id=%s", new_package.id)
            return jsonify({"message": "Paket berhasil disimpan tetapi gagal dimuat ulang."}), HTTPStatus.CREATED
        current_app.logger.info(
            f"Paket '{created_package.name}' (ID: {created_package.id}) berhasil dibuat dengan profile_id: {created_package.profile_id} (Profil: '{target_profile_name}')"
        )
        return jsonify(PackageSchema.from_orm(created_package).model_dump()), HTTPStatus.CREATED

    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama paket sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyimpan paket: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan paket."}), HTTPStatus.INTERNAL_SERVER_ERROR


# Rute PUT dan DELETE tetap sama dan tidak perlu diubah.
@package_management_bp.route("/packages/<uuid:package_id>", methods=["PUT"])
@admin_required
def update_package(current_admin: User, package_id):
    """Memperbarui paket jualan yang ada."""
    pkg = db.session.get(Package, package_id)
    if not pkg:
        return jsonify({"message": "Paket tidak ditemukan."}), HTTPStatus.NOT_FOUND
    try:
        package_data = PackageSchema.model_validate(request.get_json())
        update_dict = package_data.model_dump(exclude_unset=True, exclude={"id", "profile", "profile_id"})
        for key, value in update_dict.items():
            setattr(pkg, key, value)
        db.session.commit()
        updated_package = db.session.get(Package, pkg.id)
        return jsonify(PackageSchema.from_orm(updated_package).model_dump()), HTTPStatus.OK
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama paket sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui paket: {e}", exc_info=True)
        return jsonify({"message": "Gagal memperbarui paket."}), HTTPStatus.INTERNAL_SERVER_ERROR


@package_management_bp.route("/packages/<uuid:package_id>", methods=["DELETE"])
@admin_required
def delete_package(current_admin: User, package_id):
    """Menghapus sebuah paket, mencegah penghapusan jika ada riwayat transaksi."""
    pkg = db.session.get(Package, package_id)
    if not pkg:
        return jsonify({"message": "Paket tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if db.session.query(Transaction.id).filter_by(package_id=pkg.id).first():
        return jsonify({"message": "Paket tidak dapat dihapus karena memiliki riwayat transaksi."}), HTTPStatus.CONFLICT
    db.session.delete(pkg)
    db.session.commit()
    return jsonify({"message": "Paket berhasil dihapus."}), HTTPStatus.OK
