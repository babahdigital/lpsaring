# backend/app/infrastructure/http/admin/user_management_routes.py
import uuid
from datetime import datetime, timezone as dt_timezone
from flask import Blueprint, jsonify, request, current_app, make_response, render_template
from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError as SAOperationalError
from http import HTTPStatus
from pydantic import ValidationError
import sqlalchemy as sa

from app.extensions import db
from app.infrastructure.db.models import (
    User,
    UserRole,
    UserBlok,
    UserKamar,
    ApprovalStatus,
    AdminActionType,
    Package,
    PublicDatabaseUpdateSubmission,
    UserDevice,
)
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.http.schemas.user_schemas import (
    UserResponseSchema,
    AdminSelfProfileUpdateRequestSchema,
    UserQuotaDebtItemResponseSchema,
)
from app.services.user_management import user_debt as user_debt_service
from app.utils.formatters import get_phone_number_variations

from app.infrastructure.db.models import UserQuotaDebt


# [FIX] Menambahkan kembali impor yang hilang untuk endpoint /mikrotik-status
from app.utils.formatters import format_to_local_phone, get_app_local_datetime
from app.services.user_management.helpers import _handle_mikrotik_operation, _send_whatsapp_notification
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details

from app.services.user_management.helpers import _log_admin_action

from app.services import settings_service
from app.services.quota_history_service import get_user_quota_history_payload
from app.utils.block_reasons import is_debt_block_reason

from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package
from app.services.user_management import user_approval, user_deletion, user_profile as user_profile_service

user_management_bp = Blueprint("user_management_api", __name__)


def _serialize_public_update_submission(item: PublicDatabaseUpdateSubmission) -> dict:
    return {
        "id": str(item.id),
        "full_name": item.full_name,
        "role": item.role,
        "blok": item.blok,
        "kamar": item.kamar,
        "tamping_type": item.tamping_type,
        "phone_number": item.phone_number,
        "source_ip": item.source_ip,
        "approval_status": item.approval_status,
        "processed_by_user_id": str(item.processed_by_user_id) if item.processed_by_user_id else None,
        "processed_at": item.processed_at.isoformat() if item.processed_at else None,
        "rejection_reason": item.rejection_reason,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _collect_demo_phone_variations_from_env() -> set[str]:
    """Kumpulkan variasi nomor demo dari ENV untuk kebutuhan filter list user admin."""
    raw_values = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(raw_values, list):
        return set()

    values: set[str] = set()
    for raw in raw_values:
        try:
            variations = get_phone_number_variations(str(raw))
            for item in variations:
                normalized = str(item or "").strip()
                if normalized:
                    values.add(normalized)
        except Exception:
            continue

    return values


def _is_demo_user(user: User | None) -> bool:
    if not user:
        return False

    phone = str(getattr(user, "phone_number", "") or "").strip()
    if phone:
        demo_phone_variations = _collect_demo_phone_variations_from_env()
        if demo_phone_variations and phone in demo_phone_variations:
            return True

    full_name = str(getattr(user, "full_name", "") or "").strip()
    return bool(full_name and full_name.lower().startswith("demo user"))


def _deny_non_super_admin_target_access(current_admin: User, target_user: User):
    if current_admin.is_super_admin_role:
        return None
    if target_user.role == UserRole.SUPER_ADMIN or _is_demo_user(target_user):
        return jsonify({"message": "Akses ditolak."}), HTTPStatus.FORBIDDEN
    return None


@user_management_bp.route("/update-submissions", methods=["GET"])
@admin_required
def list_public_update_submissions(current_admin: User):
    try:
        page = max(1, request.args.get("page", 1, type=int) or 1)
        items_per_page = min(max(request.args.get("itemsPerPage", 10, type=int) or 10, 1), 100)
        search = str(request.args.get("search", "") or "").strip()
        status = str(request.args.get("status", "PENDING") or "PENDING").strip().upper()

        allowed_status = {"PENDING", "APPROVED", "REJECTED"}
        if status not in allowed_status:
            return jsonify({"message": "Status filter tidak valid."}), HTTPStatus.BAD_REQUEST

        query = db.session.query(PublicDatabaseUpdateSubmission).filter(
            PublicDatabaseUpdateSubmission.approval_status == status,
            PublicDatabaseUpdateSubmission.source_ip != "system:populate_task",
        )

        if search:
            phone_variations = get_phone_number_variations(search)
            query = query.filter(
                or_(
                    PublicDatabaseUpdateSubmission.full_name.ilike(f"%{search}%"),
                    PublicDatabaseUpdateSubmission.phone_number.in_(phone_variations),
                )
            )

        query = query.order_by(PublicDatabaseUpdateSubmission.created_at.desc())
        total_items = query.count()
        items = query.offset((page - 1) * items_per_page).limit(items_per_page).all()

        return (
            jsonify(
                {
                    "items": [_serialize_public_update_submission(item) for item in items],
                    "totalItems": total_items,
                }
            ),
            HTTPStatus.OK,
        )
    except Exception as e:
        current_app.logger.error("Gagal mengambil update submissions: %s", e, exc_info=True)
        return jsonify({"message": "Gagal memuat data pengajuan pembaruan."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/update-submissions/<uuid:submission_id>/approve", methods=["POST"])
@admin_required
def approve_public_update_submission(current_admin: User, submission_id):
    submission = db.session.get(PublicDatabaseUpdateSubmission, submission_id)
    if not submission:
        return jsonify({"message": "Pengajuan tidak ditemukan."}), HTTPStatus.NOT_FOUND

    if str(submission.approval_status or "").upper() != "PENDING":
        return jsonify({"message": "Pengajuan sudah diproses sebelumnya."}), HTTPStatus.BAD_REQUEST

    if not submission.phone_number:
        return jsonify({"message": "Pengajuan ini tidak memiliki nomor telepon untuk diverifikasi."}), HTTPStatus.BAD_REQUEST

    variations = get_phone_number_variations(str(submission.phone_number))
    user = db.session.execute(select(User).where(User.phone_number.in_(variations))).scalar_one_or_none()
    if not user:
        return jsonify({"message": "User dengan nomor telepon tersebut tidak ditemukan."}), HTTPStatus.BAD_REQUEST

    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    role_upper = str(submission.role or "").strip().upper()
    if role_upper in {"KLIEN", "CLIENT"}:
        role_upper = "USER"

    submitted_full_name = str(submission.full_name or "").strip()
    if submitted_full_name:
        user.full_name = submitted_full_name

    if role_upper == "KOMANDAN":
        user.role = UserRole.KOMANDAN
        user.is_tamping = False
        user.tamping_type = None
    elif role_upper == "TAMPING":
        if not submission.tamping_type:
            return jsonify({"message": "Jenis tamping wajib tersedia untuk role TAMPING."}), HTTPStatus.BAD_REQUEST
        user.role = UserRole.USER
        user.is_tamping = True
        user.tamping_type = submission.tamping_type
        user.blok = None
        user.kamar = None
    elif role_upper == "USER":
        if not submission.blok or not submission.kamar:
            return jsonify({"message": "Blok dan kamar wajib tersedia untuk role USER."}), HTTPStatus.BAD_REQUEST
        user.role = UserRole.USER
        user.is_tamping = False
        user.tamping_type = None
        user.blok = submission.blok
        user.kamar = submission.kamar
    else:
        return jsonify({"message": "Role pengajuan tidak valid."}), HTTPStatus.BAD_REQUEST

    if role_upper == "KOMANDAN":
        user.blok = submission.blok or user.blok
        user.kamar = submission.kamar or user.kamar

    submission.approval_status = "APPROVED"
    submission.rejection_reason = None
    submission.processed_by_user_id = current_admin.id
    submission.processed_at = datetime.now(dt_timezone.utc)

    try:
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Pengajuan berhasil disetujui.",
                    "submission": _serialize_public_update_submission(submission),
                    "user": UserResponseSchema.from_orm(user).model_dump(),
                }
            ),
            HTTPStatus.OK,
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Gagal approve pengajuan %s: %s", submission_id, e, exc_info=True)
        return jsonify({"message": "Gagal menyetujui pengajuan."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/update-submissions/<uuid:submission_id>/reject", methods=["POST"])
@admin_required
def reject_public_update_submission(current_admin: User, submission_id):
    submission = db.session.get(PublicDatabaseUpdateSubmission, submission_id)
    if not submission:
        return jsonify({"message": "Pengajuan tidak ditemukan."}), HTTPStatus.NOT_FOUND

    if str(submission.approval_status or "").upper() != "PENDING":
        return jsonify({"message": "Pengajuan sudah diproses sebelumnya."}), HTTPStatus.BAD_REQUEST

    payload = request.get_json(silent=True) or {}
    rejection_reason = str(payload.get("rejection_reason") or "").strip() or None

    submission.approval_status = "REJECTED"
    submission.rejection_reason = rejection_reason
    submission.processed_by_user_id = current_admin.id
    submission.processed_at = datetime.now(dt_timezone.utc)

    try:
        db.session.commit()
        return (
            jsonify(
                {
                    "message": "Pengajuan berhasil ditolak.",
                    "submission": _serialize_public_update_submission(submission),
                }
            ),
            HTTPStatus.OK,
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Gagal reject pengajuan %s: %s", submission_id, e, exc_info=True)
        return jsonify({"message": "Gagal menolak pengajuan."}), HTTPStatus.INTERNAL_SERVER_ERROR

# --- SEMUA ROUTE LAINNYA DI ATAS INI TIDAK BERUBAH ---
# (create_user, update_user, approve_user, dll. tetap sama)


@user_management_bp.route("/users", methods=["POST"])
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


@user_management_bp.route("/users/<uuid:user_id>", methods=["PUT"])
@admin_required
def update_user_by_admin(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
    data = request.get_json()
    if not data:
        return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
    try:
        success, message, updated_user = user_profile_service.update_user_by_admin_comprehensive(
            user, current_admin, data
        )
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


@user_management_bp.route("/users/<uuid:user_id>/approve", methods=["PATCH"])
@admin_required
def approve_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
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


@user_management_bp.route("/users/<uuid:user_id>/reject", methods=["POST"])
@admin_required
def reject_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
    success, message = user_approval.reject_user_account(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK


@user_management_bp.route("/users/<uuid:user_id>", methods=["DELETE"])
@admin_required
def delete_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

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


@user_management_bp.route("/users/<uuid:user_id>/reset-hotspot-password", methods=["POST"])
@admin_required
def admin_reset_hotspot_password(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
    success, message = user_profile_service.reset_user_hotspot_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
    db.session.commit()
    db.session.refresh(user)
    return jsonify({"message": message}), HTTPStatus.OK


@user_management_bp.route("/users/<uuid:user_id>/generate-admin-password", methods=["POST"])
@admin_required
def generate_admin_password_for_user(current_admin: User, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan"}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
    success, message = user_profile_service.generate_user_admin_password(user, current_admin)
    if not success:
        db.session.rollback()
        return jsonify({"message": message}), HTTPStatus.FORBIDDEN
    db.session.commit()
    return jsonify({"message": message}), HTTPStatus.OK


@user_management_bp.route("/users/<uuid:user_id>/reset-login", methods=["POST"])
@admin_required
def admin_reset_user_login(current_admin: User, user_id: uuid.UUID):
    """Force user to login fresh without changing quota/status fields in DB.

    - DB: delete all refresh tokens for the user.
        - MikroTik (best-effort): clear ip-binding, DHCP lease, ARP,
      and managed address-lists for IPs found in user_devices.
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    cleanup_summary = user_deletion.run_user_auth_cleanup(user, include_comment_scan=False)
    router_summary = cleanup_summary["router"]

    try:
        _log_admin_action(
            admin=current_admin,
            target_user=user,
            action_type=AdminActionType.RESET_USER_LOGIN,
            details={
                "tokens_deleted": int(cleanup_summary["tokens_deleted"]),
                "devices_deleted": int(cleanup_summary["devices_deleted"]),
                "device_count_before": int(cleanup_summary["device_count_before"]),
                "macs": cleanup_summary["macs"],
                "ips": cleanup_summary["ips"],
                "username_08": cleanup_summary["username_08"],
                "router": router_summary,
            },
        )
    except Exception:
        # Logging must never block the main action.
        pass

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing reset-login for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal menyimpan perubahan (token reset)."}), HTTPStatus.INTERNAL_SERVER_ERROR

    msg = (
        f"Reset login berhasil. Token dibersihkan: {int(cleanup_summary['tokens_deleted'])}. "
        f"Device dibersihkan: {int(cleanup_summary['devices_deleted'])}."
    )
    if router_summary.get("mikrotik_connected") is not True:
        msg += " (Catatan: MikroTik tidak terhubung, cleanup router dilewati.)"

    return jsonify(
        {
            "message": msg,
            "summary": {
                "tokens_deleted": int(cleanup_summary["tokens_deleted"]),
                "devices_deleted": int(cleanup_summary["devices_deleted"]),
                "device_count_before": int(cleanup_summary["device_count_before"]),
                "mac_count": int(cleanup_summary["mac_count"]),
                "ip_count": int(cleanup_summary["ip_count"]),
                "username_08": cleanup_summary["username_08"],
                "router": router_summary,
            },
        }
    ), HTTPStatus.OK


@user_management_bp.route("/users/me", methods=["PUT"])
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


@user_management_bp.route("/users", methods=["GET"])
@admin_required
def get_users_list(current_admin: User):
    try:
        page = request.args.get("page", 1, type=int)
        per_page_raw = request.args.get("itemsPerPage", 10, type=int)
        if per_page_raw == -1:
            per_page = None
        else:
            per_page = min(max(int(per_page_raw or 10), 1), 100)
        search_query, role_filter = request.args.get("search", ""), request.args.get("role")
        tamping_filter = request.args.get("tamping", None)

        # status filter(s): allow repeated ?status=x&status=y or comma separated.
        status_values = request.args.getlist("status")
        if len(status_values) == 1 and isinstance(status_values[0], str) and "," in status_values[0]:
            status_values = [v.strip() for v in status_values[0].split(",") if v.strip()]
        status_values = [str(v).strip().lower() for v in (status_values or []) if str(v).strip()]
        sort_by, sort_order = request.args.get("sortBy", "created_at"), request.args.get("sortOrder", "desc")

        query = select(User)
        if not current_admin.is_super_admin_role:
            query = query.where(User.role != UserRole.SUPER_ADMIN)

            demo_phone_variations = _collect_demo_phone_variations_from_env()
            if demo_phone_variations:
                query = query.where(~User.phone_number.in_(demo_phone_variations))

            # Fallback untuk akun demo auto-provision (contoh nama: "Demo User 7890").
            query = query.where(~User.full_name.ilike("Demo User%"))

        if role_filter:
            try:
                query = query.where(User.role == UserRole[role_filter.upper()])
            except KeyError:
                return jsonify({"message": "Role filter tidak valid."}), HTTPStatus.BAD_REQUEST
        if search_query:
            query = query.where(
                or_(
                    User.full_name.ilike(f"%{search_query}%"),
                    User.phone_number.in_(get_phone_number_variations(search_query)),
                )
            )

        # Tamping filter: '1' (only tamping), '0' (exclude tamping)
        if tamping_filter is not None and tamping_filter != "":
            tf = str(tamping_filter).strip().lower()
            if tf in {"1", "true", "yes", "tamping"}:
                query = query.where(User.is_tamping.is_(True))
            elif tf in {"0", "false", "no", "non", "non-tamping", "nontamping"}:
                query = query.where(User.is_tamping.is_(False))

        # Status filters (OR across selected values)
        if status_values:
            now_utc = datetime.now(dt_timezone.utc)
            fup_threshold_mb = float(settings_service.get_setting_as_int("QUOTA_FUP_THRESHOLD_MB", 3072) or 3072)

            purchased_num = sa.cast(User.total_quota_purchased_mb, sa.Numeric)
            used_num = sa.cast(User.total_quota_used_mb, sa.Numeric)
            remaining_num = purchased_num - used_num
            auto_debt = sa.func.greatest(sa.cast(0, sa.Numeric), used_num - purchased_num)
            manual_debt_num = sa.cast(func.coalesce(User.manual_debt_mb, 0), sa.Numeric)
            total_debt = auto_debt + manual_debt_num

            conditions = []
            for status in status_values:
                if status in {"blocked", "block"}:
                    conditions.append(User.is_blocked.is_(True))
                elif status in {"active", "aktif"}:
                    conditions.append(User.is_active.is_(True))
                elif status in {"inactive", "nonaktif", "disabled"}:
                    conditions.append(User.is_active.is_(False))
                elif status in {"unlimited", "unlimted"}:
                    conditions.append(User.is_unlimited_user.is_(True))
                elif status in {"debt", "hutang"}:
                    conditions.append(sa.and_(User.is_unlimited_user.is_(False), total_debt > 0))
                elif status in {"expired", "expiried"}:
                    conditions.append(sa.and_(User.quota_expiry_date.is_not(None), User.quota_expiry_date < now_utc))
                elif status in {"fup"}:
                    # Mirror hotspot sync: fup when not blocked, not unlimited, purchased>0, remaining>0,
                    # remaining_mb <= threshold, and not expired.
                    conditions.append(
                        sa.and_(
                            User.is_blocked.is_(False),
                            User.is_unlimited_user.is_(False),
                            User.is_active.is_(True),
                            User.total_quota_purchased_mb > fup_threshold_mb,
                            remaining_num > 0,
                            remaining_num <= fup_threshold_mb,
                            sa.or_(User.quota_expiry_date.is_(None), User.quota_expiry_date >= now_utc),
                        )
                    )
                elif status in {"habis", "quota_habis", "exhausted"}:
                    # Mirror hotspot sync: habis when not blocked, not unlimited, purchased>0, remaining<=0,
                    # and not expired.
                    conditions.append(
                        sa.and_(
                            User.is_blocked.is_(False),
                            User.is_unlimited_user.is_(False),
                            User.is_active.is_(True),
                            User.total_quota_purchased_mb > 0,
                            remaining_num <= 0,
                            sa.or_(User.quota_expiry_date.is_(None), User.quota_expiry_date >= now_utc),
                        )
                    )
                elif status in {"inactive_quota", "quota_inactive", "no_quota"}:
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
        query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

        total = db.session.scalar(select(func.count()).select_from(query.subquery()))

        if per_page is None:
            users = db.session.scalars(query).all()
        else:
            users = db.session.scalars(query.limit(per_page).offset((page - 1) * per_page)).all()

        user_ids = [u.id for u in users]
        device_counts: dict = {}
        if user_ids:
            rows = db.session.execute(
                select(UserDevice.user_id, func.count(UserDevice.id).label("cnt"))
                .where(UserDevice.user_id.in_(user_ids))
                .where(UserDevice.is_authorized.is_(True))
                .group_by(UserDevice.user_id)
            ).all()
            device_counts = {row.user_id: row.cnt for row in rows}

        return jsonify(
            {
                "items": [
                    {**UserResponseSchema.from_orm(u).model_dump(), "device_count": device_counts.get(u.id, 0)}
                    for u in users
                ],
                "totalItems": total,
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user list: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/debts", methods=["GET"])
@admin_required
def get_user_manual_debts(current_admin: User, user_id: uuid.UUID):
    """Ambil ledger debt manual untuk user.

    Dipakai UI agar status lunas / belum lunas jelas.
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

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
            amount = int(getattr(d, "amount_mb", 0) or 0)
            paid_mb = int(getattr(d, "paid_mb", 0) or 0)
            remaining = max(0, amount - paid_mb)
            is_paid = bool(getattr(d, "is_paid", False)) or remaining <= 0
            if is_paid:
                paid_count += 1
            else:
                open_count += 1

            payload = UserQuotaDebtItemResponseSchema.from_orm(d).model_dump()
            payload["remaining_mb"] = int(remaining)
            payload["is_paid"] = bool(is_paid)
            payload["paid_mb"] = int(paid_mb)
            payload["amount_mb"] = int(amount)
            items.append(payload)

        return jsonify(
            {
                "items": items,
                "summary": {
                    "manual_debt_mb": int(getattr(user, "quota_debt_manual_mb", 0) or 0),
                    "open_items": int(open_count),
                    "paid_items": int(paid_count),
                    "total_items": int(len(items)),
                },
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error getting user debts {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data debt pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/debts/<uuid:debt_id>/settle", methods=["POST"])
@admin_required
def settle_single_manual_debt(current_admin: User, user_id: uuid.UUID, debt_id: uuid.UUID):
    """Lunasi satu item debt manual (one-by-one), tanpa clear semua debt."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    debt = db.session.get(UserQuotaDebt, debt_id)
    if not debt or getattr(debt, "user_id", None) != user.id:
        return jsonify({"message": "Item debt tidak ditemukan."}), HTTPStatus.NOT_FOUND

    try:
        paid_mb = user_debt_service.settle_manual_debt_item_to_zero(
            user=user,
            admin_actor=current_admin,
            debt=debt,
            source="admin_settle_item",
        )
        db.session.commit()
        return jsonify({"message": "Debt berhasil dilunasi.", "paid_mb": int(paid_mb)}), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error settling debt {debt_id} for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal melunasi debt."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/debts/settle-all", methods=["POST"])
@admin_required
def settle_all_debts(current_admin: User, user_id: uuid.UUID):
    """Lunasi semua tunggakan user (auto + manual) sekaligus.

    - Manual: melunasi semua item ledger (oldest-first).
    - Otomatis: menambah purchased_mb sampai debt otomatis menjadi 0.

    Mengirim 1 notifikasi WhatsApp ke user (jika diaktifkan).
    """
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    try:
        # Snapshot for response / notification.
        debt_auto_before = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
        debt_manual_before = int(getattr(user, "quota_debt_manual_mb", 0) or 0)
        was_blocked = bool(getattr(user, "is_blocked", False))
        blocked_reason = str(getattr(user, "blocked_reason", "") or "")

        paid_auto_mb, paid_manual_mb = user_debt_service.clear_all_debts_to_zero(
            user=user,
            admin_actor=current_admin,
            source="admin_settle_all",
        )

        unblocked = False
        # Auto-unblock if user was blocked due to debt (limit or end-of-month) and all debts are fully cleared.
        if was_blocked and is_debt_block_reason(blocked_reason):
            if float(getattr(user, "quota_debt_total_mb", 0) or 0) <= 0:
                user.is_blocked = False
                user.blocked_reason = None
                user.blocked_at = None
                user.blocked_by_id = None
                unblocked = True

        db.session.commit()

        # Notify user via WhatsApp (best-effort).
        try:
            purchased_now = float(getattr(user, "total_quota_purchased_mb", 0) or 0)
            used_now = float(getattr(user, "total_quota_used_mb", 0) or 0)
            remaining_mb = max(0.0, purchased_now - used_now)

            paid_total_mb = int(paid_auto_mb) + int(paid_manual_mb)
            # Avoid sending a confusing message when nothing was actually paid.
            if paid_total_mb > 0:
                template_key = "user_debt_cleared_unblock" if unblocked else "user_debt_cleared"
                _send_whatsapp_notification(
                    user.phone_number,
                    template_key,
                    {
                        "full_name": user.full_name,
                        "paid_auto_debt_mb": int(paid_auto_mb),
                        "paid_manual_debt_mb": int(paid_manual_mb),
                        "paid_total_debt_mb": int(paid_total_mb),
                        "remaining_mb": float(remaining_mb),
                    },
                )
        except Exception as e:
            current_app.logger.warning("Gagal mengirim notifikasi lunas tunggakan untuk user %s: %s", user.id, e)

        return jsonify(
            {
                "message": "Tunggakan berhasil dilunasi.",
                "paid_auto_mb": int(paid_auto_mb),
                "paid_manual_mb": int(paid_manual_mb),
                "debt_auto_before_mb": float(debt_auto_before),
                "debt_manual_before_mb": int(debt_manual_before),
                "unblocked": bool(unblocked),
            }
        ), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error settling all debts for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal melunasi tunggakan."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/debts/export", methods=["GET"])
@admin_required
def export_user_manual_debts_pdf(current_admin: User, user_id: uuid.UUID):
    """Export riwayat debt user ke PDF (untuk print/share)."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    fmt = (request.args.get("format") or "pdf").strip().lower()
    if fmt != "pdf":
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
            amount = int(getattr(d, "amount_mb", 0) or 0)
            paid_mb = int(getattr(d, "paid_mb", 0) or 0)
            remaining = max(0, amount - paid_mb)
            is_paid = bool(getattr(d, "is_paid", False)) or remaining <= 0
            payload = UserQuotaDebtItemResponseSchema.from_orm(d).model_dump()
            try:
                if payload.get("debt_date"):
                    # debt_date from schema is typically YYYY-MM-DD
                    raw = str(payload.get("debt_date"))
                    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
                        payload["debt_date_display"] = f"{raw[8:10]}-{raw[5:7]}-{raw[0:4]}"
            except Exception:
                pass
            payload["remaining_mb"] = int(remaining)
            payload["is_paid"] = bool(is_paid)
            payload["paid_mb"] = int(paid_mb)
            payload["amount_mb"] = int(amount)
            items.append(payload)

        debt_auto_mb = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
        debt_manual_mb = float(getattr(user, "quota_debt_manual_mb", 0) or 0)
        debt_total_mb = float(getattr(user, "quota_debt_total_mb", debt_auto_mb + debt_manual_mb) or 0)

        def _pick_ref_pkg_for_debt_mb(value_mb: float) -> Package | None:
            try:
                mb = float(value_mb or 0)
            except Exception:
                mb = 0.0
            if mb <= 0:
                return None
            debt_gb = mb / 1024.0

            base_q = (
                select(Package)
                .where(Package.is_active.is_(True))
                .where(Package.data_quota_gb.is_not(None))
                .where(Package.data_quota_gb > 0)
                .where(Package.price.is_not(None))
                .where(Package.price > 0)
            )
            ref = db.session.execute(
                base_q.where(Package.data_quota_gb >= debt_gb)
                .order_by(Package.data_quota_gb.asc(), Package.price.asc())
                .limit(1)
            ).scalar_one_or_none()
            if ref is None:
                ref = db.session.execute(
                    base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).limit(1)
                ).scalar_one_or_none()
            return ref

        def _estimate_for_mb(value_mb: float):
            pkg = _pick_ref_pkg_for_debt_mb(value_mb)
            return estimate_debt_rp_from_cheapest_package(
                debt_mb=float(value_mb or 0),
                cheapest_package_price_rp=int(pkg.price) if pkg and pkg.price is not None else None,
                cheapest_package_quota_gb=float(pkg.data_quota_gb) if pkg and pkg.data_quota_gb is not None else None,
                cheapest_package_name=str(pkg.name) if pkg and pkg.name else None,
            )

        est_auto = _estimate_for_mb(debt_auto_mb)
        est_manual = _estimate_for_mb(debt_manual_mb)
        est_total = _estimate_for_mb(debt_total_mb)

        now_utc = datetime.now(dt_timezone.utc)
        generated_local = get_app_local_datetime(now_utc).strftime("%d-%m-%Y %H:%M")

        context = {
            "user": user,
            "user_phone_display": format_to_local_phone(getattr(user, "phone_number", "") or "")
            or (getattr(user, "phone_number", "") or ""),
            "generated_at": generated_local,
            "items": items,
            "debt_auto_mb": debt_auto_mb,
            "debt_manual_mb": debt_manual_mb,
            "debt_total_mb": debt_total_mb,
            "debt_auto_estimated_rp": est_auto.estimated_rp_rounded or 0,
            "debt_manual_estimated_rp": est_manual.estimated_rp_rounded or 0,
            "debt_total_estimated_rp": est_total.estimated_rp_rounded or 0,
            "estimate_base_package_name": est_total.package_name,
        }

        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("admin_user_debt_report.html", **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
        if not pdf_bytes:
            return jsonify({"message": "Gagal menghasilkan file PDF."}), HTTPStatus.INTERNAL_SERVER_ERROR

        safe_phone = (getattr(user, "phone_number", "") or "").replace("+", "")
        filename = f"debt-{safe_phone or user.id}-ledger.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error(f"Error export debt PDF for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/quota-history", methods=["GET"])
@admin_required
def get_user_quota_history(current_admin: User, user_id: uuid.UUID):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    try:
        page = max(1, request.args.get("page", 1, type=int) or 1)
        items_per_page = min(max(request.args.get("itemsPerPage", 25, type=int) or 25, 1), 100)
        payload = get_user_quota_history_payload(
            user=user,
            page=page,
            items_per_page=items_per_page,
            start_date=request.args.get("startDate"),
            end_date=request.args.get("endDate"),
            search=request.args.get("search"),
        )
        return (
            jsonify(
                {
                    "items": payload["items"],
                    "summary": payload["summary"],
                    "filters": payload["filters"],
                    "totalItems": payload["total_items"],
                    "page": payload["page"],
                    "itemsPerPage": payload["items_per_page"],
                }
            ),
            HTTPStatus.OK,
        )
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error getting quota history for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil riwayat mutasi kuota."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/quota-history/export", methods=["GET"])
@admin_required
def export_user_quota_history_pdf(current_admin: User, user_id: uuid.UUID):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    fmt = (request.args.get("format") or "pdf").strip().lower()
    if fmt != "pdf":
        return jsonify({"message": "Format tidak didukung."}), HTTPStatus.BAD_REQUEST

    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        payload = get_user_quota_history_payload(
            user=user,
            include_all=True,
            items_per_page=200,
            start_date=request.args.get("startDate"),
            end_date=request.args.get("endDate"),
            search=request.args.get("search"),
        )
        generated_local = get_app_local_datetime(datetime.now(dt_timezone.utc)).strftime("%d-%m-%Y %H:%M")
        context = {
            "user": user,
            "user_phone_display": format_to_local_phone(getattr(user, "phone_number", "") or "")
            or (getattr(user, "phone_number", "") or ""),
            "generated_at": generated_local,
            "items": payload["items"],
            "summary": payload["summary"],
            "filters": payload["filters"],
        }

        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        html_string = render_template("quota_history_report.html", **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
        if not pdf_bytes:
            return jsonify({"message": "Gagal menghasilkan file PDF."}), HTTPStatus.INTERNAL_SERVER_ERROR

        safe_phone = (getattr(user, "phone_number", "") or "").replace("+", "")
        filename = f"quota-history-{safe_phone or user.id}.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except ValueError as e:
        return jsonify({"message": str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f"Error export quota history PDF for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/inactive-cleanup-preview", methods=["GET"])
@admin_required
def get_inactive_cleanup_preview(current_admin: User):
    try:
        now_utc = datetime.now(dt_timezone.utc)
        deactivate_days = settings_service.get_setting_as_int("INACTIVE_DEACTIVATE_DAYS", 45)
        delete_days = settings_service.get_setting_as_int("INACTIVE_DELETE_DAYS", 90)
        delete_enabled = settings_service.get_setting_as_bool("INACTIVE_AUTO_DELETE_ENABLED", False)
        delete_max_per_run = settings_service.get_setting_as_int("INACTIVE_DELETE_MAX_PER_RUN", 0)
        limit = min(request.args.get("limit", 50, type=int), 200)

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

        return jsonify(
            {
                "thresholds": {
                    "deactivate_days": deactivate_days,
                    "delete_days": delete_days,
                    "delete_enabled": delete_enabled,
                    "delete_max_per_run": delete_max_per_run,
                },
                "summary": {
                    "deactivate_candidates": len(deactivate_candidates),
                    "delete_candidates": len(delete_candidates),
                },
                "items": {
                    "deactivate_candidates": deactivate_candidates[:limit],
                    "delete_candidates": delete_candidates[:limit],
                },
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error preview cleanup pengguna tidak aktif: {e}", exc_info=True)
        return jsonify(
            {"message": "Gagal memuat preview cleanup pengguna tidak aktif."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/form-options/alamat", methods=["GET"])
@admin_required
def get_alamat_form_options(current_admin: User):
    return jsonify(
        {"bloks": [e.value for e in UserBlok], "kamars": [e.value.replace("Kamar_", "") for e in UserKamar]}
    ), HTTPStatus.OK


@user_management_bp.route("/form-options/mikrotik", methods=["GET"])
@admin_required
def get_mikrotik_form_options(current_admin: User):
    try:
        default_server = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER", None) or settings_service.get_setting(
            "MIKROTIK_DEFAULT_SERVER_USER", "srv-user"
        )
        default_server_komandan = settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_KOMANDAN", "srv-komandan")
        active_profile = (
            settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE", None)
            or settings_service.get_setting("MIKROTIK_USER_PROFILE", "user")
            or settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
        )
        komandan_profile = settings_service.get_setting("MIKROTIK_KOMANDAN_PROFILE", None) or "komandan"
        defaults = {
            "server_user": default_server,
            "server_komandan": default_server_komandan or default_server,
            "server_admin": default_server,
            "server_support": default_server,
            "profile_user": active_profile,
            "profile_komandan": komandan_profile or active_profile,
            "profile_default": settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default"),
            "profile_active": active_profile,
            "profile_fup": settings_service.get_setting("MIKROTIK_FUP_PROFILE", "fup"),
            "profile_habis": settings_service.get_setting("MIKROTIK_HABIS_PROFILE", "habis"),
            "profile_unlimited": settings_service.get_setting("MIKROTIK_UNLIMITED_PROFILE", "unlimited"),
            "profile_expired": settings_service.get_setting("MIKROTIK_EXPIRED_PROFILE", "expired"),
            "profile_blocked": settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive"),
            "profile_inactive": settings_service.get_setting("MIKROTIK_INACTIVE_PROFILE", "inactive"),
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
            defaults.get("profile_blocked"),
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

        return jsonify(
            {
                "serverOptions": _unique(server_candidates),
                "profileOptions": _unique(profile_candidates),
                "defaults": defaults,
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Gagal memuat opsi Mikrotik: {e}", exc_info=True)
        return jsonify({"message": "Gagal memuat opsi Mikrotik."}), HTTPStatus.INTERNAL_SERVER_ERROR


# ================================================================
# === [DIKEMBALIKAN] Logika Live Check ke MikroTik dengan Error Handling Lengkap ===
# ================================================================
@user_management_bp.route("/users/<uuid:user_id>/mikrotik-status", methods=["GET"])
@admin_required
def check_mikrotik_status(current_admin: User, user_id: uuid.UUID):
    """
    Mengecek status live seorang pengguna di Mikrotik dengan penanganan error yang aman.
    """
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"message": "Pengguna tidak ditemukan di database."}), HTTPStatus.NOT_FOUND
        denied_response = _deny_non_super_admin_target_access(current_admin, user)
        if denied_response:
            return denied_response

        mikrotik_username = format_to_local_phone(user.phone_number)
        if not mikrotik_username:
            return jsonify(
                {"exists_on_mikrotik": False, "message": "Format nomor telepon pengguna tidak valid."}
            ), HTTPStatus.OK

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

        purchased_mb = float(user.total_quota_purchased_mb or 0)
        used_mb = float(user.total_quota_used_mb or 0)
        remaining_mb = max(0.0, purchased_mb - used_mb)
        db_quota = {
            "db_quota_purchased_mb": purchased_mb,
            "db_quota_used_mb": used_mb,
            "db_quota_remaining_mb": remaining_mb,
        }

        if not success:
            current_app.logger.warning(
                "Live check Mikrotik tidak tersedia untuk user %s: %s",
                user_id,
                mikrotik_message,
            )
            return jsonify(
                {
                    "user_id": str(user.id),
                    "exists_on_mikrotik": bool(user.mikrotik_user_exists),
                    "details": None,
                    "live_available": False,
                    "message": "Live check MikroTik tidak tersedia. Menampilkan data lokal database.",
                    "reason": mikrotik_message,
                    **db_quota,
                }
            ), HTTPStatus.OK

        user_exists = details is not None

        if user.mikrotik_user_exists != user_exists:
            user.mikrotik_user_exists = user_exists
            db.session.commit()

        return jsonify(
            {
                "user_id": str(user.id),
                "exists_on_mikrotik": user_exists,
                "details": details,
                "live_available": True,
                "message": "Data live MikroTik berhasil dimuat."
                if user_exists
                else "Pengguna tidak ditemukan di MikroTik.",
                **db_quota,
            }
        ), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(
            f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True
        )
        return jsonify(
            {"message": "Terjadi kesalahan internal tak terduga pada server."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


# ================================================================
# === Koreksi Kuota Langsung — Khusus Super Admin ===
# ================================================================
@user_management_bp.route("/users/<uuid:user_id>/quota-adjust", methods=["POST"])
@admin_required
def adjust_user_quota_direct(current_admin: User, user_id: uuid.UUID):
    """Koreksi langsung total_quota_purchased_mb dan/atau total_quota_used_mb.

    Hanya bisa dipanggil oleh Super Admin. Direkam di quota_mutation_ledger
    dengan source 'quota.adjust_direct' untuk audit trail.

    Body JSON:
    - set_purchased_mb: int (opsional) — nilai baru untuk total_quota_purchased_mb
    - set_used_mb: int (opsional) — nilai baru untuk total_quota_used_mb
    - reason: str (wajib) — alasan koreksi untuk audit trail
    """
    if not bool(getattr(current_admin, "is_super_admin_role", False)):
        return jsonify({"message": "Akses ditolak. Fitur ini hanya untuk Super Admin."}), HTTPStatus.FORBIDDEN

    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND

        data = request.get_json(silent=True) or {}
        raw_purchased = data.get("set_purchased_mb")
        raw_used = data.get("set_used_mb")
        reason = str(data.get("reason") or "").strip()

        if raw_purchased is None and raw_used is None:
            return jsonify(
                {"message": "Setidaknya satu dari set_purchased_mb atau set_used_mb harus diisi."}
            ), HTTPStatus.UNPROCESSABLE_ENTITY

        if not reason:
            return jsonify(
                {"message": "Field 'reason' wajib diisi untuk audit trail."}
            ), HTTPStatus.UNPROCESSABLE_ENTITY

        set_purchased_mb: int | None = None
        if raw_purchased is not None:
            try:
                set_purchased_mb = int(raw_purchased)
                if set_purchased_mb < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"message": "set_purchased_mb harus bilangan bulat >= 0."}), HTTPStatus.UNPROCESSABLE_ENTITY

        set_used_mb: int | None = None
        if raw_used is not None:
            try:
                set_used_mb = int(raw_used)
                if set_used_mb < 0:
                    raise ValueError
            except (ValueError, TypeError):
                return jsonify({"message": "set_used_mb harus bilangan bulat >= 0."}), HTTPStatus.UNPROCESSABLE_ENTITY

        from app.services.quota_mutation_ledger_service import (
            append_quota_mutation_event,
            lock_user_quota_row,
            snapshot_user_quota_state,
        )

        lock_user_quota_row(user, nowait=True)
        before_state = snapshot_user_quota_state(user)
        changes: dict = {"reason": reason}

        if set_purchased_mb is not None:
            user.total_quota_purchased_mb = set_purchased_mb
            changes["set_purchased_mb"] = set_purchased_mb

        if set_used_mb is not None:
            user.total_quota_used_mb = float(set_used_mb)
            changes["set_used_mb"] = set_used_mb
            # Untuk unlimited user: sync auto_debt_offset_mb agar raw_debt tidak stale.
            # Misal: admin set used=0 → offset harus juga 0, bukan sisa nilai lama.
            if bool(getattr(user, "is_unlimited_user", False)):
                _new_purchased = int(user.total_quota_purchased_mb or 0)
                _new_offset = max(0, set_used_mb - _new_purchased)
                if _new_offset != int(user.auto_debt_offset_mb or 0):
                    user.auto_debt_offset_mb = _new_offset
                    changes["auto_debt_offset_mb"] = _new_offset

        append_quota_mutation_event(
            user=user,
            source="quota.adjust_direct",
            before_state=before_state,
            after_state=snapshot_user_quota_state(user),
            actor_user_id=current_admin.id,
            event_details=changes,
        )

        db.session.commit()

        current_app.logger.info(
            "SuperAdmin %s quota-adjust untuk user %s: %s",
            current_admin.id,
            user_id,
            changes,
        )

        purchased = float(user.total_quota_purchased_mb or 0)
        used = float(user.total_quota_used_mb or 0)
        return jsonify(
            {
                "message": "Kuota berhasil disesuaikan.",
                "total_quota_purchased_mb": purchased,
                "total_quota_used_mb": used,
                "remaining_mb": max(0.0, purchased - used),
            }
        ), HTTPStatus.OK

    except SAOperationalError:
        db.session.rollback()
        return jsonify(
            {"message": "Sistem sedang memproses data pengguna ini (sinkronisasi aktif). Coba lagi dalam beberapa detik."}
        ), HTTPStatus.CONFLICT

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal quota-adjust untuk user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/seed-imported-update-submissions", methods=["POST"])
@admin_required
def seed_imported_update_submissions(current_admin: User):
    """Buat PublicDatabaseUpdateSubmission untuk semua user bermama 'Imported ...' yang belum dinotifikasi WA.

    Body JSON opsional:
    - test_phone: string  -> hanya seed untuk nomor ini (mode uji coba)
    - dry_run: bool       -> hitung saja tanpa membuat record (default False)
    """
    body = request.get_json(silent=True) or {}
    test_phone = str(body.get("test_phone") or "").strip()
    dry_run = bool(body.get("dry_run", False))

    try:
        query = db.session.query(User).filter(
            User.role.in_([UserRole.USER]),
            User.approval_status == ApprovalStatus.APPROVED,
            User.is_active == True,  # noqa: E712
            User.full_name.ilike("Imported %"),
        )
        if test_phone:
            phone_variations = get_phone_number_variations(test_phone)
            query = query.filter(User.phone_number.in_(phone_variations))

        imported_users = query.all()

        seeded = []
        skipped = []

        for user in imported_users:
            # Cek apakah sudah ada submission pending dan belum dinotifikasi
            existing = (
                db.session.query(PublicDatabaseUpdateSubmission)
                .filter(
                    PublicDatabaseUpdateSubmission.phone_number.in_(
                        get_phone_number_variations(user.phone_number or "")
                    ),
                    PublicDatabaseUpdateSubmission.whatsapp_notified_at == None,  # noqa: E711
                )
                .first()
            )

            if existing:
                skipped.append(user.phone_number)
                continue

            if not dry_run:
                record = PublicDatabaseUpdateSubmission()
                record.full_name = user.full_name or f"Imported {user.phone_number}"
                record.role = user.role.value if hasattr(user.role, "value") else str(user.role)
                record.blok = getattr(user, "blok", None)
                record.kamar = getattr(user, "kamar", None)
                record.phone_number = user.phone_number
                record.approval_status = "PENDING"
                record.source_ip = "admin_seed"
                db.session.add(record)

            seeded.append(user.phone_number)

        if not dry_run and seeded:
            db.session.commit()

        current_app.logger.info(
            "seed_imported_update_submissions: seeded=%d skipped=%d dry_run=%s by admin=%s",
            len(seeded), len(skipped), dry_run, current_admin.phone_number,
        )

        return jsonify({
            "success": True,
            "dry_run": dry_run,
            "seeded_count": len(seeded),
            "skipped_count": len(skipped),
            "seeded_phones": seeded,
            "skipped_phones": skipped,
            "message": (
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"{len(seeded)} submission dibuat untuk user Imported"
                f"{f' (test: {test_phone})' if test_phone else ''}."
                f" {len(skipped)} sudah ada / sudah dinotifikasi."
            ),
        }), HTTPStatus.OK

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"seed_imported_update_submissions error: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal seed submission."}), HTTPStatus.INTERNAL_SERVER_ERROR
