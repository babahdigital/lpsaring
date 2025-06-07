# backend/app/infrastructure/http/admin_routes.py
# VERSI FINAL 4: Penyesuaian untuk filter user & invoice di halaman transaksi, dan endpoint list user.

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
import uuid
from decimal import Decimal

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, Package, PackageProfile, ApprovalStatus, Transaction, TransactionStatus
from .decorators import admin_required
from .schemas.user_schemas import UserResponseSchema, UserUpdateByAdminSchema
from app.services.helpers import normalize_phone_number

admin_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')

# ==============================================================================
# Endpoint Statistik Dashboard
# ==============================================================================
@admin_bp.route('/dashboard/stats', methods=['GET'])
@admin_required
def get_dashboard_stats(current_admin: User):
    try:
        stats = {
            "totalUsers": 0,
            "pendingApprovals": 0,
            "activePackages": 0,
            "monthlyRevenue": 0
        }
        return jsonify(stats), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada endpoint dummy dashboard/stats: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat statistik."}), HTTPStatus.INTERNAL_SERVER_ERROR

# ==============================================================================
# Skema Pydantic
# ==============================================================================
class ProfileSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    profile_name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    data_quota_gb: Decimal = Field(..., ge=0, decimal_places=2, description="Kuota dalam GB. 0 berarti unlimited.")
    duration_days: int = Field(..., gt=0)
    class Config: from_attributes = True

class PackageSchema(BaseModel):
    id: Optional[uuid.UUID] = None
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    price: int = Field(..., ge=0)
    is_active: bool = True
    profile_id: uuid.UUID
    profile: Optional[ProfileSchema] = None
    class Config: from_attributes = True

# ==============================================================================
# Endpoint Manajemen Pengguna
# ==============================================================================
@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    try:
        # PENYESUAIAN 1: Tambahkan logika untuk mengambil semua user untuk filter
        if request.args.get('all') == 'true':
            query = db.select(User).order_by(User.full_name.asc())
            if not current_admin.is_super_admin_role:
                query = query.where(User.role == UserRole.USER)
            all_users = db.session.scalars(query).all()
            # Hanya kembalikan data yang perlu untuk selection
            users_data = [
                {"id": str(user.id), "full_name": user.full_name, "phone_number": user.phone_number}
                for user in all_users
            ]
            return jsonify(users_data), HTTPStatus.OK

        # Logika paginasi yang sudah ada tetap dipertahankan
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        search_query = request.args.get('search', '').strip()

        query = db.select(User)
        if not current_admin.is_super_admin_role:
            query = query.where(User.role == UserRole.USER)

        if search_query:
            search_term = f"%{search_query}%"
            query = query.where(or_(User.full_name.ilike(search_term), User.phone_number.ilike(search_term)))
        
        if hasattr(User, sort_by):
            column_to_sort = getattr(User, sort_by)
            query = query.order_by(column_to_sort.desc() if sort_order.lower() == 'desc' else column_to_sort.asc())
        else:
            query = query.order_by(User.created_at.desc())

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        users_data = [UserResponseSchema.from_orm(user).model_dump() for user in pagination.items]

        return jsonify({"items": users_data, "totalItems": pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar pengguna: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    user_to_update = db.session.get(User, user_id)
    if not user_to_update: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if not current_admin.is_super_admin_role and user_to_update.is_admin_role: return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    data = request.get_json()
    if not data: return jsonify({"message": "Data tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    try:
        update_data = UserUpdateByAdminSchema.model_validate(data)
        
        if update_data.phone_number:
            normalized_phone = normalize_phone_number(update_data.phone_number)
            if normalized_phone != user_to_update.phone_number:
                existing_user = db.session.scalar(db.select(User).filter_by(phone_number=normalized_phone))
                if existing_user:
                    return jsonify({"message": f"Nomor telepon {normalized_phone} sudah terdaftar."}), HTTPStatus.CONFLICT
            user_to_update.phone_number = normalized_phone

        for field, value in update_data.model_dump(exclude={'phone_number'}, exclude_unset=True).items():
            if field == 'role' and not current_admin.is_super_admin_role: continue
            if field == 'role' and user_to_update.id == current_admin.id and value != UserRole.SUPER_ADMIN:
                return jsonify({"message": "Super Admin tidak dapat mengubah perannya sendiri."}), HTTPStatus.FORBIDDEN
            setattr(user_to_update, field, value)

        db.session.commit()
        return jsonify(UserResponseSchema.from_orm(user_to_update).model_dump()), HTTPStatus.OK
    except ValidationError as e: return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui pengguna {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/users/<uuid:user_id>/approve', methods=['PATCH'])
@admin_required
def approve_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if user.approval_status == ApprovalStatus.APPROVED: return jsonify({"message": "Pengguna sudah disetujui."}), HTTPStatus.OK

    user.approval_status = ApprovalStatus.APPROVED
    user.is_active = True
    user.approved_at = datetime.now(dt_timezone.utc)
    user.approved_by_id = current_admin.id
    db.session.commit()
    return jsonify({"message": f"Pengguna {user.full_name} berhasil disetujui."}), HTTPStatus.OK

@admin_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if user.id == current_admin.id: return jsonify({"message": "Anda tidak dapat menghapus akun Anda sendiri."}), HTTPStatus.FORBIDDEN
    if not current_admin.is_super_admin_role and user.is_admin_role: return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    action_message = f"Pendaftaran pengguna {user.full_name} berhasil ditolak dan dihapus." if user.approval_status == ApprovalStatus.PENDING_APPROVAL else f"Pengguna {user.full_name} berhasil dihapus."
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": action_message}), HTTPStatus.OK

# ==============================================================================
# Endpoint Manajemen Profil Admin Sendiri
# ==============================================================================
@admin_bp.route('/users/me', methods=['PUT'])
@admin_required
def update_own_admin_profile(current_admin: User):
    """Memperbarui profil admin yang sedang login (nama & telepon)."""
    data = request.get_json()
    if not data:
        return jsonify({"message": "Data tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    # Anda bisa membuat skema Pydantic khusus untuk ini jika ingin validasi lebih ketat
    # Untuk sementara, validasi manual:
    full_name = data.get('full_name')
    phone_number = data.get('phone_number')

    if not full_name or len(full_name) < 2:
        return jsonify({"errors": [{"loc": ["full_name"], "msg": "Nama lengkap wajib diisi dan minimal 2 karakter."}]}), HTTPStatus.UNPROCESSABLE_ENTITY

    try:
        normalized_phone = normalize_phone_number(phone_number) # Gunakan helper yang sudah ada
    except (ValueError, TypeError) as e:
        return jsonify({"errors": [{"loc": ["phone_number"], "msg": str(e)}]}), HTTPStatus.UNPROCESSABLE_ENTITY

    # Cek jika nomor telepon baru sudah digunakan oleh orang lain
    if normalized_phone != current_admin.phone_number:
        existing_user = db.session.scalar(db.select(User).filter_by(phone_number=normalized_phone))
        if existing_user:
            return jsonify({"message": f"Nomor telepon {normalized_phone} sudah terdaftar untuk pengguna lain."}), HTTPStatus.CONFLICT
    
    current_admin.full_name = full_name
    current_admin.phone_number = normalized_phone
    
    try:
        db.session.commit()
        # Mengembalikan data user yang lengkap menggunakan skema yang sudah ada
        return jsonify(UserResponseSchema.from_orm(current_admin).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui profil admin {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat menyimpan profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

# ==============================================================================
# Endpoint Manajemen Profil & Paket
# ==============================================================================
@admin_bp.route('/profiles', methods=['GET'])
@admin_required
def get_profiles_list(current_admin: User):
    try:
        if request.args.get('all') == 'true':
            profiles = db.session.scalars(db.select(PackageProfile).order_by(PackageProfile.profile_name)).all()
            return jsonify([ProfileSchema.from_orm(p).model_dump() for p in profiles]), HTTPStatus.OK

        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        pagination = db.paginate(db.select(PackageProfile).order_by(PackageProfile.created_at.desc()), page=page, per_page=per_page, error_out=False)
        
        return jsonify({"items": [ProfileSchema.from_orm(p).model_dump() for p in pagination.items], "totalItems": pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil daftar profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/profiles', methods=['POST'])
@admin_required
def create_profile(current_admin: User):
    try:
        profile_data = ProfileSchema.model_validate(request.get_json())
        new_profile = PackageProfile(**profile_data.model_dump(exclude={'id'}))
        db.session.add(new_profile)
        db.session.commit()
        return jsonify(ProfileSchema.from_orm(new_profile).model_dump()), HTTPStatus.CREATED
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama profil sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e: return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyimpan profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/profiles/<uuid:profile_id>', methods=['PUT'])
@admin_required
def update_profile(current_admin: User, profile_id):
    profile = db.session.get(PackageProfile, profile_id)
    if not profile: return jsonify({"message": "Profil tidak ditemukan."}), HTTPStatus.NOT_FOUND
    try:
        profile_data = ProfileSchema.model_validate(request.get_json())
        for key, value in profile_data.model_dump(exclude={'id'}).items():
            setattr(profile, key, value)
        db.session.commit()
        return jsonify(ProfileSchema.from_orm(profile).model_dump()), HTTPStatus.OK
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama profil sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e: return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui profil: {e}", exc_info=True)
        return jsonify({"message": "Gagal memperbarui profil."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/profiles/<uuid:profile_id>', methods=['DELETE'])
@admin_required
def delete_profile(current_admin: User, profile_id):
    profile = db.session.scalar(db.select(PackageProfile).where(PackageProfile.id == profile_id).options(selectinload(PackageProfile.packages)))
    if not profile: return jsonify({"message": "Profil tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if profile.packages: return jsonify({"message": "Profil tidak dapat dihapus karena masih digunakan oleh beberapa paket."}), HTTPStatus.CONFLICT
    
    db.session.delete(profile)
    db.session.commit()
    return jsonify({"message": "Profil berhasil dihapus."}), HTTPStatus.OK

@admin_bp.route('/packages', methods=['GET'])
@admin_required
def get_packages_list(current_admin: User):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        search_query = request.args.get('search', '').strip()
        
        query = db.select(Package).options(joinedload(Package.profile))
        if search_query:
            query = query.join(PackageProfile).filter(or_(Package.name.ilike(f"%{search_query}%"), PackageProfile.profile_name.ilike(f"%{search_query}%")))
            
        query = query.order_by(Package.created_at.desc())
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        
        return jsonify({"items": [PackageSchema.from_orm(p).model_dump() for p in pagination.items], "totalItems": pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar paket: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil daftar paket."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/packages', methods=['POST'])
@admin_required
def create_package(current_admin: User):
    try:
        package_data = PackageSchema.model_validate(request.get_json())
        new_package = Package(**package_data.model_dump(exclude={'id', 'profile'}))
        db.session.add(new_package)
        db.session.commit()
        created_package = db.session.get(Package, new_package.id)
        return jsonify(PackageSchema.from_orm(created_package).model_dump()), HTTPStatus.CREATED
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama paket sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e: return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal menyimpan paket: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan paket."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/packages/<uuid:package_id>', methods=['PUT'])
@admin_required
def update_package(current_admin: User, package_id):
    pkg = db.session.get(Package, package_id)
    if not pkg: return jsonify({"message": "Paket tidak ditemukan."}), HTTPStatus.NOT_FOUND
    try:
        package_data = PackageSchema.model_validate(request.get_json())
        for key, value in package_data.model_dump(exclude={'id', 'profile'}).items():
            setattr(pkg, key, value)
        db.session.commit()
        updated_package = db.session.get(Package, pkg.id)
        return jsonify(PackageSchema.from_orm(updated_package).model_dump()), HTTPStatus.OK
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Nama paket sudah ada."}), HTTPStatus.CONFLICT
    except ValidationError as e: return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui paket: {e}", exc_info=True)
        return jsonify({"message": "Gagal memperbarui paket."}), HTTPStatus.INTERNAL_SERVER_ERROR

@admin_bp.route('/packages/<uuid:package_id>', methods=['DELETE'])
@admin_required
def delete_package(current_admin: User, package_id):
    pkg = db.session.get(Package, package_id)
    if not pkg: return jsonify({"message": "Paket tidak ditemukan."}), HTTPStatus.NOT_FOUND
    if db.session.query(Transaction.id).filter_by(package_id=pkg.id).first():
        return jsonify({"message": "Paket tidak dapat dihapus karena memiliki riwayat transaksi."}), HTTPStatus.CONFLICT
        
    db.session.delete(pkg)
    db.session.commit()
    return jsonify({"message": "Paket berhasil dihapus."}), HTTPStatus.OK
# ==============================================================================
# Endpoint Manajemen Transaksi (Disesuaikan)
# ==============================================================================
@admin_bp.route('/transactions', methods=['GET'])
@admin_required
def get_transactions_list(current_admin: User):
    """
    Mengambil daftar semua transaksi dengan paginasi, sorting, dan filter.
    Mendukung filter berdasarkan user_id dan pencarian berdasarkan order_id.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        
        # PENYESUAIAN 2: Ambil parameter baru
        search_query = request.args.get('search', '').strip() # Ini sekarang hanya untuk Order ID
        user_id_filter = request.args.get('user_id', None) # Filter spesifik pengguna

        query = db.select(Transaction).options(
            joinedload(Transaction.user),
            joinedload(Transaction.package)
        )

        # Logika Filter Gabungan
        if user_id_filter:
            try:
                user_uuid = uuid.UUID(user_id_filter)
                query = query.where(Transaction.user_id == user_uuid)
            except ValueError:
                return jsonify({"message": "Format user_id tidak valid."}), HTTPStatus.BAD_REQUEST

        if search_query:
            search_term = f"%{search_query}%"
            query = query.where(Transaction.midtrans_order_id.ilike(search_term))

        sortable_columns = {
            'created_at': Transaction.created_at,
            'amount': Transaction.amount,
            'status': Transaction.status,
            'order_id': Transaction.midtrans_order_id,
        }
        
        if sort_by in sortable_columns:
            column_to_sort = sortable_columns[sort_by]
            query = query.order_by(column_to_sort.desc() if sort_order.lower() == 'desc' else column_to_sort.asc())
        else:
            query = query.order_by(Transaction.created_at.desc())

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        
        transactions_data = []
        for tx in pagination.items:
            transactions_data.append({
                "id": str(tx.id),
                "order_id": tx.midtrans_order_id,
                "amount": float(tx.amount) if tx.amount is not None else 0,
                "status": tx.status.value if tx.status else 'UNKNOWN',
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "user": {
                    "full_name": tx.user.full_name if tx.user else "N/A",
                    "phone_number": tx.user.phone_number if tx.user else "N/A"
                },
                "package_name": tx.package.name if tx.package else "N/A"
            })

        return jsonify({
            "items": transactions_data,
            "totalItems": pagination.total
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error mengambil daftar transaksi: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat mengambil data transaksi."}), HTTPStatus.INTERNAL_SERVER_ERROR


@admin_bp.route('/transactions/export', methods=['GET'])
@admin_required
def export_transactions(current_admin: User):
    """
    Menghasilkan laporan transaksi dalam format CSV atau PDF, mendukung filter.
    """
    # PENYESUAIAN 3: Ambil semua filter saat ekspor
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    user_id_filter = request.args.get('user_id') # Ambil filter pengguna juga
    export_format = request.args.get('format')
    
    if not all([start_date_str, end_date_str, export_format]):
        return jsonify({"message": "Parameter start_date, end_date, dan format diperlukan."}), HTTPStatus.BAD_REQUEST
        
    current_app.logger.info(f"Admin {current_admin.id} meminta ekspor transaksi dari {start_date_str} hingga {end_date_str} untuk user '{user_id_filter or 'Semua'}' dalam format {export_format}.")
    
    # Di sini Anda akan menambahkan logika query yang juga menggunakan user_id_filter
    # dan logika pembuatan file seperti yang direncanakan.
    
    return jsonify({
        "message": f"Fungsi ekspor {export_format} sedang dalam pengembangan.",
        "params_received": {
            "start": start_date_str,
            "end": end_date_str,
            "user_id": user_id_filter,
            "format": export_format
        }
    }), HTTPStatus.NOT_IMPLEMENTED