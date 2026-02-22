# backend/app/infrastructure/http/user/profile_routes.py
# Berisi endpoint yang berhubungan dengan manajemen profil dan keamanan pengguna.

from flask import Blueprint, request, jsonify, abort, current_app
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus

from app.extensions import db
from app.services import settings_service
from app.services.notification_service import get_notification_message

# --- PERBAIKAN IMPORT DI SINI ---
# Impor fungsi dari lokasi yang benar di modul service, bukan dari file rute lain.
from app.services.transaction_service import generate_random_password
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, activate_or_update_hotspot_user
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.utils.formatters import format_to_local_phone
# -----------------------------

from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserLoginHistory, UserDevice
from ..schemas.user_schemas import UserProfileResponseSchema, UserProfileUpdateRequestSchema
from ..decorators import token_required
from app.services.device_management_service import apply_device_binding_for_login, revoke_device


profile_bp = Blueprint("user_profile_api", __name__, url_prefix="/api/users")


@profile_bp.route("/me/profile", methods=["GET", "PUT"])
@token_required
def handle_my_profile(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")
    if getattr(user, "is_blocked", False):
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda diblokir oleh Admin.")

    if request.method == "GET":
        profile_data = UserProfileResponseSchema.model_validate(user)
        return jsonify(profile_data.model_dump(mode="json")), HTTPStatus.OK

    elif request.method == "PUT":
        if user.role != UserRole.USER:
            abort(HTTPStatus.FORBIDDEN, description="Endpoint ini hanya untuk pengguna biasa (USER).")

        json_data = request.get_json(silent=True)
        if not json_data:
            return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

        try:
            update_data = UserProfileUpdateRequestSchema.model_validate(json_data)
            user_updated = False

            if update_data.full_name is not None and user.full_name != update_data.full_name:
                user.full_name, user_updated = update_data.full_name, True
            if update_data.is_tamping is not None and user.is_tamping != update_data.is_tamping:
                user.is_tamping, user_updated = update_data.is_tamping, True

            if user.is_tamping:
                if update_data.tamping_type is not None and user.tamping_type != update_data.tamping_type:
                    user.tamping_type, user_updated = update_data.tamping_type, True
                if user.blok is not None:
                    user.blok, user_updated = None, True
                if user.kamar is not None:
                    user.kamar, user_updated = None, True
            else:
                if update_data.blok is not None and user.blok != update_data.blok:
                    user.blok, user_updated = update_data.blok, True
                if update_data.kamar is not None and user.kamar != update_data.kamar:
                    user.kamar, user_updated = update_data.kamar, True

            if user_updated:
                db.session.commit()

            resp_data = UserProfileResponseSchema.model_validate(user)
            return jsonify(resp_data.model_dump(mode="json")), HTTPStatus.OK

        except ValidationError as e:
            return jsonify(
                {"message": "Data input tidak valid.", "details": e.errors()}
            ), HTTPStatus.UNPROCESSABLE_ENTITY
        except Exception as e:
            db.session.rollback()
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan internal: {str(e)}")

    abort(HTTPStatus.METHOD_NOT_ALLOWED, description="Metode tidak didukung.")


@profile_bp.route("/me/reset-hotspot-password", methods=["POST"])
@token_required
def reset_my_hotspot_password(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, "Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, "Akun Anda belum aktif atau disetujui.")

    if user.is_admin_role:
        abort(HTTPStatus.FORBIDDEN, "Fitur ini tidak untuk role Admin. Gunakan panel admin untuk mereset.")

    mikrotik_username = format_to_local_phone(user.phone_number)
    if not mikrotik_username:
        abort(HTTPStatus.BAD_REQUEST, "Format nomor telepon tidak valid.")

    # Perbaikan: Menyesuaikan pemanggilan fungsi dengan menghapus argumen 'numeric_only' yang tidak ada.
    new_password = generate_random_password(length=6)

    with get_mikrotik_connection() as api_conn:
        if not api_conn:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal koneksi ke sistem hotspot.")

        mikrotik_profile_name = str(getattr(user, "current_package_profile_name", "") or "").strip()
        if not mikrotik_profile_name:
            mikrotik_profile_name = settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
        mikrotik_profile_name = str(mikrotik_profile_name or "default")

        success, msg = activate_or_update_hotspot_user(
            api_connection=api_conn,
            user_mikrotik_username=mikrotik_username,
            mikrotik_profile_name=mikrotik_profile_name,
            hotspot_password=new_password,
            comment=f"Password Reset by User: {user.full_name}",
            force_update_profile=False,
        )
        if not success:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, f"Gagal update password di sistem hotspot: {msg}")

    try:
        user.mikrotik_password = new_password
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menyimpan password baru.")

    context = {"full_name": user.full_name, "username": mikrotik_username, "password": new_password}
    message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
    send_whatsapp_message(user.phone_number, message_body)

    return jsonify({"message": "Password hotspot berhasil direset dan dikirim via WhatsApp."}), HTTPStatus.OK


@profile_bp.route("/me/login-history", methods=["GET"])
@token_required
def get_my_login_history(current_user_id):
    try:
        limit = min(max(int(request.args.get("limit", "7")), 1), 20)
        login_records = (
            db.session.query(UserLoginHistory)
            .filter(UserLoginHistory.user_id == current_user_id)
            .order_by(UserLoginHistory.login_time.desc())
            .limit(limit)
            .all()
        )

        history_data = [
            {
                "login_time": r.login_time.isoformat() if r.login_time else None,
                "ip_address": r.ip_address,
                "user_agent_string": r.user_agent_string,
            }
            for r in login_records
        ]

        return jsonify(history_data), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error di get_my_login_history: {e}", exc_info=True)
        return jsonify({"message": f"Gagal mengambil riwayat: {e}"}), HTTPStatus.INTERNAL_SERVER_ERROR


@profile_bp.route("/me/devices", methods=["GET"])
@token_required
def get_my_devices(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")
    if getattr(user, "is_blocked", False):
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda diblokir oleh Admin.")

    devices = db.session.scalars(
        select(UserDevice).where(UserDevice.user_id == user.id).order_by(UserDevice.last_seen_at.desc())
    ).all()

    response = [
        {
            "id": str(d.id),
            "mac_address": d.mac_address,
            "ip_address": d.ip_address,
            "label": d.label,
            "is_authorized": d.is_authorized,
            "first_seen_at": d.first_seen_at.isoformat() if d.first_seen_at else None,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "authorized_at": d.authorized_at.isoformat() if d.authorized_at else None,
            "deauthorized_at": d.deauthorized_at.isoformat() if d.deauthorized_at else None,
        }
        for d in devices
    ]
    return jsonify({"devices": response}), HTTPStatus.OK


@profile_bp.route("/me/devices/bind-current", methods=["POST"])
@token_required
def bind_current_device(current_user_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")
    if getattr(user, "is_blocked", False):
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda diblokir oleh Admin.")

    user_agent = request.headers.get("User-Agent")

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}

    # Best-effort: terima input dari captive portal (query/body) bila tersedia.
    client_ip = (
        payload.get("client_ip")
        or payload.get("clientIp")
        or payload.get("ip")
        or payload.get("client-ip")
        or request.args.get("client_ip")
        or request.args.get("ip")
        or request.args.get("client-ip")
        or None
    )
    client_mac = (
        payload.get("client_mac")
        or payload.get("clientMac")
        or payload.get("mac")
        or payload.get("mac-address")
        or payload.get("client-mac")
        or request.args.get("client_mac")
        or request.args.get("mac")
        or request.args.get("mac-address")
        or request.args.get("client-mac")
        or None
    )

    # Jika tidak ada client_ip dari portal, jangan pakai get_client_ip() mentah-mentah karena
    # sering berupa IP publik/proxy. Biarkan service mencoba resolve IP dari MikroTik.
    if not client_ip:
        client_ip = None

    ok, msg, _resolved_ip = apply_device_binding_for_login(
        user,
        client_ip,
        user_agent,
        client_mac,
        bypass_explicit_auth=True,
    )
    if not ok:
        return jsonify({"message": msg}), HTTPStatus.FORBIDDEN

    db.session.commit()
    return jsonify({"message": "Perangkat berhasil diikat."}), HTTPStatus.OK


@profile_bp.route("/me/devices/<uuid:device_id>", methods=["DELETE"])
@token_required
def delete_my_device(current_user_id, device_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")

    device = db.session.scalar(select(UserDevice).where(UserDevice.id == device_id, UserDevice.user_id == user.id))
    if not device:
        abort(HTTPStatus.NOT_FOUND, description="Perangkat tidak ditemukan.")

    revoke_device(user, device)
    db.session.delete(device)
    db.session.commit()
    return jsonify({"message": "Perangkat berhasil dihapus."}), HTTPStatus.OK


@profile_bp.route("/me/devices/<uuid:device_id>/label", methods=["PUT"])
@token_required
def update_my_device_label(current_user_id, device_id):
    user = db.session.get(User, current_user_id)
    if not user:
        abort(HTTPStatus.NOT_FOUND, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau belum disetujui.")

    payload = request.get_json(silent=True) or {}
    label = payload.get("label")
    if label is not None:
        if not isinstance(label, str):
            abort(HTTPStatus.BAD_REQUEST, description="Label perangkat tidak valid.")
        label = label.strip()
        if len(label) > 100:
            abort(HTTPStatus.BAD_REQUEST, description="Label perangkat terlalu panjang.")

    device = db.session.scalar(select(UserDevice).where(UserDevice.id == device_id, UserDevice.user_id == user.id))
    if not device:
        abort(HTTPStatus.NOT_FOUND, description="Perangkat tidak ditemukan.")

    device.label = label or None
    db.session.commit()
    return jsonify({"message": "Label perangkat berhasil diperbarui."}), HTTPStatus.OK
