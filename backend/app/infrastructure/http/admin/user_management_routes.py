# backend/app/infrastructure/http/admin/user_management_routes.py
import uuid
from datetime import datetime, timezone as dt_timezone
from flask import Blueprint, jsonify, request, current_app, make_response, render_template
from sqlalchemy import func, or_, select
from http import HTTPStatus
from pydantic import ValidationError
import sqlalchemy as sa

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, UserBlok, UserKamar, ApprovalStatus
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.http.schemas.user_schemas import (
    UserResponseSchema,
    AdminSelfProfileUpdateRequestSchema,
    UserQuotaDebtItemResponseSchema,
)
from app.utils.formatters import get_phone_number_variations

from app.infrastructure.db.models import UserQuotaDebt


# [FIX] Menambahkan kembali impor yang hilang untuk endpoint /mikrotik-status
from app.utils.formatters import format_to_local_phone
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details

from app.services import settings_service
from app.services.user_management import (
    user_approval,
    user_deletion,
    user_profile as user_profile_service
)

user_management_bp = Blueprint('user_management_api', __name__)

# --- SEMUA ROUTE LAINNYA DI ATAS INI TIDAK BERUBAH ---
# (create_user, update_user, approve_user, dll. tetap sama)

@user_management_bp.route('/users', methods=['POST'])
@admin_required
def create_user_by_admin(current_admin: User):
    data = request.get_json()
    if not data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST
    try:
        success, message, new_user = user_profile_service.create_user_by_admin(current_admin, data)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(new_user)
        return jsonify(UserResponseSchema.from_orm(new_user).model_dump()), HTTPStatus.CREATED
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>', methods=['PUT'])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    data = request.get_json()
    if not data:
        return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
    try:
        success, message, updated_user = user_profile_service.update_user_by_admin_comprehensive(user, current_admin, data)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(updated_user)
        return jsonify(UserResponseSchema.from_orm(updated_user).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/approve', methods=['PATCH'])
@admin_required
def approve_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    try:
        success, message = user_approval.approve_user_account(user, current_admin)
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        db.session.refresh(user)
        return jsonify({"message": message, "user": UserResponseSchema.from_orm(user).model_dump()}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/reject', methods=['POST'])
@admin_required
def reject_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_approval.reject_user_account(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/<uuid:user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user: 
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND

    try:
        # [PERUBAHAN] Panggil fungsi baru yang lebih cerdas
        success, message = user_deletion.process_user_removal(user, current_admin)
        
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.FORBIDDEN
        
        db.session.commit()
        return jsonify({"message": message}), HTTPStatus.OK

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat memproses penghapusan user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/users/<uuid:user_id>/reset-hotspot-password', methods=['POST'])
@admin_required
def admin_reset_hotspot_password(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_profile_service.reset_user_hotspot_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    db.session.refresh(user)
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/<uuid:user_id>/generate-admin-password', methods=['POST'])
@admin_required
def generate_admin_password_for_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    success, message = user_profile_service.generate_user_admin_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.FORBIDDEN
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK

@user_management_bp.route('/users/me', methods=['PUT'])
@admin_required
def update_my_profile(current_admin: User):
    if not request.is_json:
        return jsonify({"message": "Request body must be JSON."}), HTTPStatus.BAD_REQUEST

    try:
        update_data = AdminSelfProfileUpdateRequestSchema.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"message": "Invalid input.", "errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY

    try:
        if update_data.phone_number and update_data.phone_number != current_admin.phone_number:
            variations = get_phone_number_variations(update_data.phone_number)
            existing_user = db.session.execute(
                select(User).where(User.phone_number.in_(variations), User.id != current_admin.id)
            ).scalar_one_or_none()
            if existing_user:
                return jsonify({"message": "Nomor telepon sudah digunakan."}), HTTPStatus.CONFLICT

            current_admin.phone_number = update_data.phone_number

        current_admin.full_name = update_data.full_name
        db.session.commit()
        db.session.refresh(current_admin)
        return jsonify(UserResponseSchema.from_orm(current_admin).model_dump()), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating admin profile {current_admin.id}: {e}", exc_info=True)
        return jsonify({"message": "Kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR
    
@user_management_bp.route('/users', methods=['GET'])
@admin_required
def get_users_list(current_admin: User):
    try:
        page = request.args.get('page', 1, type=int)
        per_page_raw = request.args.get('itemsPerPage', 10, type=int)
        if per_page_raw == -1:
            per_page = None
        else:
            per_page = min(max(int(per_page_raw or 10), 1), 100)
        search_query, role_filter = request.args.get('search', ''), request.args.get('role')
        tamping_filter = request.args.get('tamping', None)

        # status filter(s): allow repeated ?status=x&status=y or comma separated.
        status_values = request.args.getlist('status')
        if len(status_values) == 1 and isinstance(status_values[0], str) and ',' in status_values[0]:
            status_values = [v.strip() for v in status_values[0].split(',') if v.strip()]
        status_values = [str(v).strip().lower() for v in (status_values or []) if str(v).strip()]
        sort_by, sort_order = request.args.get('sortBy', 'created_at'), request.args.get('sortOrder', 'desc')
        
        query = select(User)
        if not current_admin.is_super_admin_role:
            query = query.where(User.role != UserRole.SUPER_ADMIN)
        if role_filter:
            try:
                query = query.where(User.role == UserRole[role_filter.upper()])
            except KeyError:
                return jsonify({"message": "Role filter tidak valid."}), HTTPStatus.BAD_REQUEST
        if search_query:
            query = query.where(or_(User.full_name.ilike(f"%{search_query}%"), User.phone_number.in_(get_phone_number_variations(search_query))))

        # Tamping filter: '1' (only tamping), '0' (exclude tamping)
        if tamping_filter is not None and tamping_filter != '':
            tf = str(tamping_filter).strip().lower()
            if tf in {'1', 'true', 'yes', 'tamping'}:
                query = query.where(User.is_tamping.is_(True))
            elif tf in {'0', 'false', 'no', 'non', 'non-tamping', 'nontamping'}:
                query = query.where(User.is_tamping.is_(False))

        # Status filters (OR across selected values)
        if status_values:
            now_utc = datetime.now(dt_timezone.utc)
            fup_threshold = float(settings_service.get_setting_as_int('QUOTA_FUP_PERCENT', 20) or 20)

            purchased_num = sa.cast(User.total_quota_purchased_mb, sa.Numeric)
            used_num = sa.cast(User.total_quota_used_mb, sa.Numeric)
            remaining_num = purchased_num - used_num
            remaining_percent = (remaining_num / func.nullif(purchased_num, 0)) * 100
            auto_debt = sa.func.greatest(sa.cast(0, sa.Numeric), used_num - purchased_num)
            manual_debt_num = sa.cast(func.coalesce(User.manual_debt_mb, 0), sa.Numeric)
            total_debt = auto_debt + manual_debt_num

            conditions = []
            for status in status_values:
                if status in {'blocked', 'block'}:
                    conditions.append(User.is_blocked.is_(True))
                elif status in {'active', 'aktif'}:
                    conditions.append(User.is_active.is_(True))
                elif status in {'inactive', 'nonaktif', 'disabled'}:
                    conditions.append(User.is_active.is_(False))
                elif status in {'unlimited', 'unlimted'}:
                    conditions.append(User.is_unlimited_user.is_(True))
                elif status in {'debt', 'hutang'}:
                    conditions.append(total_debt > 0)
                elif status in {'expired', 'expiried'}:
                    conditions.append(sa.and_(User.quota_expiry_date.is_not(None), User.quota_expiry_date < now_utc))
                elif status in {'fup'}:
                    # Mirror hotspot sync: fup when not blocked, not unlimited, purchased>0, remaining>0,
                    # remaining_percent <= threshold, and not expired.
                    conditions.append(
                        sa.and_(
                            User.is_blocked.is_(False),
                            User.is_unlimited_user.is_(False),
                            User.is_active.is_(True),
                            User.total_quota_purchased_mb > 0,
                            remaining_num > 0,
                            remaining_percent <= fup_threshold,
                            sa.or_(User.quota_expiry_date.is_(None), User.quota_expiry_date >= now_utc),
                        )
                    )
                elif status in {'inactive_quota', 'quota_inactive', 'no_quota'}:
                    # "Inactive" quota state: user aktif, bukan unlimited, purchased<=0, dan tidak expired.
                    conditions.append(
                        sa.and_(
                            User.is_active.is_(True),
                            User.is_unlimited_user.is_(False),
                            User.total_quota_purchased_mb <= 0,
                            sa.or_(User.quota_expiry_date.is_(None), User.quota_expiry_date >= now_utc),
                        )
                    )

            if conditions:
                query = query.where(or_(*conditions))
        
        sort_col = getattr(User, sort_by, User.created_at)
        query = query.order_by(sort_col.desc() if sort_order == 'desc' else sort_col.asc())

        total = db.session.scalar(select(func.count()).select_from(query.subquery()))

        if per_page is None:
            users = db.session.scalars(query).all()
        else:
            users = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()
        
        return jsonify({"items": [UserResponseSchema.from_orm(u).model_dump() for u in users], "totalItems": total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user list: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route('/users/<uuid:user_id>/debts', methods=['GET'])
@admin_required
def get_user_manual_debts(current_admin: User, user_id: uuid.UUID):
    """Ambil ledger debt manual untuk user.

    Dipakai UI agar status lunas / belum lunas jelas.
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND

    # RBAC: admin non-super tidak boleh melihat data super admin.
    if not current_admin.is_super_admin_role and user.role == UserRole.SUPER_ADMIN:
        return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    try:
        debts = db.session.scalars(
            select(UserQuotaDebt)
            .where(UserQuotaDebt.user_id == user.id)
            .order_by(
                UserQuotaDebt.debt_date.desc().nulls_last(),
                UserQuotaDebt.created_at.desc(),
            )
        ).all()

        items = []
        open_count = 0
        paid_count = 0
        for d in debts:
            amount = int(getattr(d, 'amount_mb', 0) or 0)
            paid_mb = int(getattr(d, 'paid_mb', 0) or 0)
            remaining = max(0, amount - paid_mb)
            is_paid = bool(getattr(d, 'is_paid', False)) or remaining <= 0
            if is_paid:
                paid_count += 1
            else:
                open_count += 1

            payload = UserQuotaDebtItemResponseSchema.from_orm(d).model_dump()
            payload['remaining_mb'] = int(remaining)
            payload['is_paid'] = bool(is_paid)
            payload['paid_mb'] = int(paid_mb)
            payload['amount_mb'] = int(amount)
            items.append(payload)

        return jsonify(
            {
                'items': items,
                'summary': {
                    'manual_debt_mb': int(getattr(user, 'manual_debt_mb', 0) or 0),
                    'open_items': int(open_count),
                    'paid_items': int(paid_count),
                    'total_items': int(len(items)),
                },
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user debts {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data debt pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route('/users/<uuid:user_id>/debts/export', methods=['GET'])
@admin_required
def export_user_manual_debts_pdf(current_admin: User, user_id: uuid.UUID):
    """Export riwayat debt user ke PDF (untuk print/share)."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND

    # RBAC: admin non-super tidak boleh melihat data super admin.
    if not current_admin.is_super_admin_role and user.role == UserRole.SUPER_ADMIN:
        return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN

    fmt = (request.args.get('format') or 'pdf').strip().lower()
    if fmt != 'pdf':
        return jsonify({"message": "Format tidak didukung."}), HTTPStatus.BAD_REQUEST

    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        debts = db.session.scalars(
            select(UserQuotaDebt)
            .where(UserQuotaDebt.user_id == user.id)
            .order_by(
                UserQuotaDebt.debt_date.desc().nulls_last(),
                UserQuotaDebt.created_at.desc(),
            )
        ).all()

        items = []
        for d in debts:
            amount = int(getattr(d, 'amount_mb', 0) or 0)
            paid_mb = int(getattr(d, 'paid_mb', 0) or 0)
            remaining = max(0, amount - paid_mb)
            is_paid = bool(getattr(d, 'is_paid', False)) or remaining <= 0
            payload = UserQuotaDebtItemResponseSchema.from_orm(d).model_dump()
            payload['remaining_mb'] = int(remaining)
            payload['is_paid'] = bool(is_paid)
            payload['paid_mb'] = int(paid_mb)
            payload['amount_mb'] = int(amount)
            items.append(payload)

        debt_auto_mb = float(getattr(user, 'quota_debt_auto_mb', 0) or 0)
        debt_manual_mb = float(getattr(user, 'quota_debt_manual_mb', 0) or 0)
        debt_total_mb = float(getattr(user, 'quota_debt_total_mb', debt_auto_mb + debt_manual_mb) or 0)

        context = {
            'user': user,
            'user_phone_display': format_to_local_phone(getattr(user, 'phone_number', '') or '')
            or (getattr(user, 'phone_number', '') or ''),
            'generated_at': datetime.now(dt_timezone.utc).strftime('%d %b %Y %H:%M UTC'),
            'items': items,
            'debt_auto_mb': debt_auto_mb,
            'debt_manual_mb': debt_manual_mb,
            'debt_total_mb': debt_total_mb,
        }

        public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
        html_string = render_template('admin_user_debt_report.html', **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
        if not pdf_bytes:
            return jsonify({"message": "Gagal menghasilkan file PDF."}), HTTPStatus.INTERNAL_SERVER_ERROR

        safe_phone = (getattr(user, 'phone_number', '') or '').replace('+', '')
        filename = f'debt-{safe_phone or user.id}-ledger.pdf'
        resp = make_response(pdf_bytes)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error(f"Error export debt PDF for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route('/users/inactive-cleanup-preview', methods=['GET'])
@admin_required
def get_inactive_cleanup_preview(current_admin: User):
    try:
        now_utc = datetime.now(dt_timezone.utc)
        deactivate_days = settings_service.get_setting_as_int('INACTIVE_DEACTIVATE_DAYS', 45)
        delete_days = settings_service.get_setting_as_int('INACTIVE_DELETE_DAYS', 90)
        limit = min(request.args.get('limit', 50, type=int), 200)

        users = db.session.scalars(
            select(User).where(
                User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
                User.approval_status == ApprovalStatus.APPROVED,
            )
        ).all()

        deactivate_candidates = []
        delete_candidates = []

        for user in users:
            last_activity = user.last_login_at or user.created_at
            if not last_activity:
                continue

            days_inactive = (now_utc - last_activity).days
            payload = {
                "id": str(user.id),
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "role": user.role.value,
                "is_active": user.is_active,
                "last_activity_at": last_activity.isoformat(),
                "days_inactive": days_inactive,
            }

            if days_inactive >= delete_days:
                delete_candidates.append(payload)
            elif user.is_active and days_inactive >= deactivate_days:
                deactivate_candidates.append(payload)

        delete_candidates.sort(key=lambda item: item["days_inactive"], reverse=True)
        deactivate_candidates.sort(key=lambda item: item["days_inactive"], reverse=True)

        return jsonify({
            "thresholds": {
                "deactivate_days": deactivate_days,
                "delete_days": delete_days,
            },
            "summary": {
                "deactivate_candidates": len(deactivate_candidates),
                "delete_candidates": len(delete_candidates),
            },
            "items": {
                "deactivate_candidates": deactivate_candidates[:limit],
                "delete_candidates": delete_candidates[:limit],
            },
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error preview cleanup pengguna tidak aktif: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat preview cleanup pengguna tidak aktif."}), HTTPStatus.INTERNAL_SERVER_ERROR

@user_management_bp.route('/form-options/alamat', methods=['GET'])
@admin_required
def get_alamat_form_options(current_admin: User):
    return jsonify({
        "bloks": [e.value for e in UserBlok],
        "kamars": [e.value.replace('Kamar_', '') for e in UserKamar]
    }), HTTPStatus.OK

@user_management_bp.route('/form-options/mikrotik', methods=['GET'])
@admin_required
def get_mikrotik_form_options(current_admin: User):
    try:
        default_server = (
            settings_service.get_setting('MIKROTIK_DEFAULT_SERVER', None)
            or settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_USER', 'srv-user')
        )
        default_server_komandan = settings_service.get_setting('MIKROTIK_DEFAULT_SERVER_KOMANDAN', 'srv-komandan')
        active_profile = (
            settings_service.get_setting('MIKROTIK_ACTIVE_PROFILE', None)
            or settings_service.get_setting('MIKROTIK_USER_PROFILE', 'user')
            or settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default')
        )
        defaults = {
            "server_user": default_server,
            "server_komandan": default_server_komandan or default_server,
            "server_admin": default_server,
            "server_support": default_server,
            "profile_user": active_profile,
            "profile_komandan": active_profile,
            "profile_default": settings_service.get_setting('MIKROTIK_DEFAULT_PROFILE', 'default'),
            "profile_active": active_profile,
            "profile_fup": settings_service.get_setting('MIKROTIK_FUP_PROFILE', 'fup'),
            "profile_habis": settings_service.get_setting('MIKROTIK_HABIS_PROFILE', 'habis'),
            "profile_unlimited": settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited'),
            "profile_expired": settings_service.get_setting('MIKROTIK_EXPIRED_PROFILE', 'expired'),
            "profile_inactive": settings_service.get_setting('MIKROTIK_INACTIVE_PROFILE', 'inactive'),
        }

        server_candidates = [
            defaults.get("server_user"),
            defaults.get("server_komandan"),
            defaults.get("server_admin"),
            defaults.get("server_support"),
        ]
        profile_candidates = [
            defaults.get("profile_user"),
            defaults.get("profile_komandan"),
            defaults.get("profile_default"),
            defaults.get("profile_active"),
            defaults.get("profile_fup"),
            defaults.get("profile_habis"),
            defaults.get("profile_unlimited"),
            defaults.get("profile_expired"),
            defaults.get("profile_inactive"),
        ]

        def _unique(values):
            seen = set()
            result = []
            for value in values:
                if not value:
                    continue
                if value in seen:
                    continue
                seen.add(value)
                result.append(value)
            return result

        return jsonify({
            "serverOptions": _unique(server_candidates),
            "profileOptions": _unique(profile_candidates),
            "defaults": defaults,
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Gagal memuat opsi Mikrotik: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat opsi Mikrotik."}), HTTPStatus.INTERNAL_SERVER_ERROR

# ================================================================
# === [DIKEMBALIKAN] Logika Live Check ke MikroTik dengan Error Handling Lengkap ===
# ================================================================
@user_management_bp.route('/users/<uuid:user_id>/mikrotik-status', methods=['GET'])
@admin_required
def check_mikrotik_status(current_admin: User, user_id: uuid.UUID):
    """
    Mengecek status live seorang pengguna di Mikrotik dengan penanganan error yang aman.
    """
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"message": "Pengguna tidak ditemukan di database."}), HTTPStatus.NOT_FOUND

        mikrotik_username = format_to_local_phone(user.phone_number)
        if not mikrotik_username:
            return jsonify({
                "exists_on_mikrotik": False,
                "message": "Format nomor telepon pengguna tidak valid."
            }), HTTPStatus.OK

        operation_result = _handle_mikrotik_operation(
            get_hotspot_user_details,
            username=mikrotik_username,
        )

        success = False
        details = None
        mikrotik_message = ""

        if isinstance(operation_result, tuple):
            if len(operation_result) >= 3:
                success, details, mikrotik_message = operation_result[0], operation_result[1], operation_result[2]
            elif len(operation_result) == 2:
                success, details = operation_result
                mikrotik_message = str(details) if success is False else "Sukses"
            elif len(operation_result) == 1:
                success = bool(operation_result[0])
                mikrotik_message = "Hasil operasi Mikrotik tidak lengkap."

        if not success:
            current_app.logger.warning(
                "Live check Mikrotik tidak tersedia untuk user %s: %s",
                user_id,
                mikrotik_message,
            )
            return jsonify({
                "user_id": str(user.id),
                "exists_on_mikrotik": bool(user.mikrotik_user_exists),
                "details": None,
                "live_available": False,
                "message": "Live check MikroTik tidak tersedia. Menampilkan data lokal database.",
                "reason": mikrotik_message,
            }), HTTPStatus.OK

        user_exists = details is not None

        if user.mikrotik_user_exists != user_exists:
            user.mikrotik_user_exists = user_exists
            db.session.commit()

        return jsonify({
            "user_id": str(user.id),
            "exists_on_mikrotik": user_exists,
            "details": details,
            "live_available": True,
            "message": "Data live MikroTik berhasil dimuat." if user_exists else "Pengguna tidak ditemukan di MikroTik.",
        }), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal tak terduga pada server."}), HTTPStatus.INTERNAL_SERVER_ERROR