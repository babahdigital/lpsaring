# backend/app/infrastructure/http/auth/public_auth_routes.py

import logging
import random
from http import HTTPStatus

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from app.extensions import db, limiter
from app.infrastructure.db.models import ApprovalStatus, User, UserKamar, UserRole
from app.infrastructure.gateways.whatsapp_client import send_otp_whatsapp
from app.infrastructure.http.schemas.auth_schemas import (
    AuthErrorResponseSchema, UserRegisterRequestSchema)
from app.services.auth_session_service import AuthSessionService
from app.services.client_detection_service import ClientDetectionService
from flask_jwt_extended import create_access_token, create_refresh_token, set_refresh_cookies
from werkzeug.security import check_password_hash
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

public_auth_bp = Blueprint('public_auth', __name__, url_prefix='/auth')

@public_auth_bp.route('/register', methods=['POST'])
def register_user():
    """
    Endpoint untuk registrasi user baru.
    ---
    tags:
      - Otentikasi
    summary: Mendaftarkan pengguna baru ke sistem
    description: Menerima data pendaftaran dan membuat akun pengguna baru dengan status menunggu persetujuan admin.
    requestBody:
      required: true
      content:
        application/json:
          schema: UserRegisterRequestSchema
    responses:
      200:
        description: Pendaftaran berhasil diterima dan sedang menunggu persetujuan
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                  example: "Pendaftaran berhasil diterima! Kami akan memproses permintaan Anda."
                phone_number:
                  type: string
                  example: "+6281234567890"
      400:
        description: Format permintaan tidak valid
        content:
          application/json:
            schema: AuthErrorResponseSchema
      409:
        description: Nomor telepon sudah terdaftar
        content:
          application/json:
            schema: AuthErrorResponseSchema
      422:
        description: Validasi data gagal
        content:
          application/json:
            schema: AuthErrorResponseSchema
      500:
        description: Kesalahan server
        content:
          application/json:
            schema: AuthErrorResponseSchema
    """
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST
    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        normalized_phone_number = data_input.phone_number
        if db.session.execute(select(User.id).filter_by(phone_number=normalized_phone_number)).scalar_one_or_none():
            return jsonify(AuthErrorResponseSchema(error="Nomor telepon sudah terdaftar.").model_dump()), HTTPStatus.CONFLICT

        from user_agents import parse as parse_user_agent
        ua_string = request.headers.get('User-Agent')
        device_brand, device_model, raw_ua = None, None, None
        if ua_string:
            raw_ua, ua_info = ua_string[:1024], parse_user_agent(ua_string)
            device_brand, device_model = getattr(ua_info.device, 'brand', None), getattr(ua_info.device, 'model', None)

        new_user_obj = User()
        new_user_obj.phone_number = normalized_phone_number
        new_user_obj.full_name = data_input.full_name
        new_user_obj.approval_status = ApprovalStatus.PENDING_APPROVAL
        new_user_obj.is_active = False
        new_user_obj.device_brand = device_brand
        new_user_obj.device_model = device_model
        new_user_obj.raw_user_agent = raw_ua
        new_user_obj.is_unlimited_user = False
        new_user_obj.role = UserRole.KOMANDAN if data_input.register_as_komandan else UserRole.USER

        from app.utils.mikrotik_helpers import get_server_for_user
        new_user_obj.mikrotik_server_name = get_server_for_user(new_user_obj)

        if data_input.blok:
            setattr(new_user_obj, 'blok', data_input.blok)
        if data_input.kamar:
            setattr(new_user_obj, 'kamar', f"Kamar_{data_input.kamar}")

        db.session.add(new_user_obj)
        db.session.commit()

        from app.services.user_management.helpers import _send_whatsapp_notification
        context = {"full_name": data_input.full_name, "link_user_app": current_app.config.get('APP_LINK_USER')}
        _send_whatsapp_notification(normalized_phone_number, "user_self_register_pending", context)

        if current_app.config.get('ENABLE_ADMIN_NOTIFICATIONS', 'True') == 'True':
            admin_phones = db.session.scalars(select(User.phone_number).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))).all()
            admin_context = {
                "full_name": data_input.full_name,
                "phone_number": normalized_phone_number,
                "role": "KOMANDAN" if data_input.register_as_komandan else "USER",
                "blok": data_input.blok or "-",
                "kamar": data_input.kamar or "-"
            }
            for admin_phone in admin_phones:
                _send_whatsapp_notification(admin_phone, "new_user_registration_to_admin", admin_context)

        return jsonify({
            "message": "Pendaftaran berhasil diterima! Kami akan memproses permintaan Anda.",
            "phone_number": normalized_phone_number
        }), HTTPStatus.OK

    except ValueError as e:
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=str(e)).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        logger.error(f"[Register] Error: {str(e)}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tak terduga.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR


@public_auth_bp.route('/request-otp', methods=['POST'])
@limiter.limit("3 per minute; 10 per hour")
def request_otp():
    """
    Meminta kode OTP untuk login.
    ---
    tags:
      - Otentikasi
    summary: Meminta kode OTP untuk proses login
    description: >
      Mengirim kode OTP ke nomor WhatsApp pengguna untuk verifikasi.
      Permintaan dibatasi hingga 3 per menit dan 10 per jam per IP.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - phone_number
            properties:
              phone_number:
                type: string
                description: Nomor telepon pengguna
                example: "+6281234567890"
    responses:
      200:
        description: OTP berhasil dikirim
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [SUCCESS]
                message:
                  type: string
                  example: "Kode OTP telah dikirim via WhatsApp"
      400:
        description: Data tidak lengkap
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ERROR]
                message:
                  type: string
      403:
        description: Akun belum disetujui
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ERROR]
                message:
                  type: string
      404:
        description: Pengguna tidak ditemukan
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ERROR]
                message:
                  type: string
      429:
        description: Rate limit tercapai
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ERROR]
                message:
                  type: string
      500:
        description: Kesalahan server
        content:
          application/json:
            schema:
              type: object
              properties:
                status:
                  type: string
                  enum: [ERROR]
                message:
                  type: string
    """
    data = request.get_json() or {}
    phone_number = data.get('phone_number')
    if not phone_number:
        return jsonify({"status": "ERROR", "message": "Nomor telepon wajib diisi"}), 400

    user = db.session.execute(select(User).filter_by(phone_number=phone_number)).scalar_one_or_none()
    if not user:
        return jsonify({"status": "ERROR", "message": "Nomor telepon belum terdaftar"}), 404
    if user.approval_status != ApprovalStatus.APPROVED:
        return jsonify({"status": "ERROR", "message": "Akun belum disetujui admin"}), 403

    redis_client = getattr(current_app, 'redis_client_otp', None)
    if not redis_client:
        return jsonify({"status": "ERROR", "message": "Service tidak tersedia"}), 500

    otp_code = str(random.randint(100000, 999999))
    otp_key = f"otp:{phone_number}"
    redis_client.setex(otp_key, 300, otp_code)

    message = f"Kode OTP Anda: {otp_code}\nBerlaku 5 menit."
    try:
        send_otp_whatsapp(phone_number, message)
        return jsonify({"status": "SUCCESS", "message": "Kode OTP telah dikirim via WhatsApp"}), 200
    except Exception as e:
        logger.error(f"[REQUEST-OTP] WhatsApp send error: {e}")
        return jsonify({"status": "ERROR", "message": "Gagal mengirim OTP via WhatsApp"}), 500

@public_auth_bp.route('/verify-otp', methods=['POST'])
@limiter.limit("5 per minute; 30 per hour")
def verify_otp():
  """Verifikasi OTP dan login pengguna."""
  from app.infrastructure.db.models import UserDevice
  from app.infrastructure.gateways.mikrotik_client import (
    find_and_update_address_list_entry,
    add_ip_to_address_list,
    create_static_lease,
  )
  from app.utils.formatters import format_to_local_phone

  data = request.get_json() or {}
  phone = data.get('phone') or data.get('phone_number')
  otp_raw = data.get('otp') or data.get('code')
  otp_code = str(otp_raw) if otp_raw is not None else None

  detection_result = ClientDetectionService.get_client_info(
    frontend_ip=(data.get('ip') or data.get('client_ip')),
    frontend_mac=(data.get('mac') or data.get('client_mac')),
  )
  client_ip = detection_result.get('detected_ip')
  client_mac = detection_result.get('detected_mac')

  if not phone or not otp_code:
    return jsonify({"status": "ERROR", "message": "Phone dan OTP wajib diisi"}), 400

  redis_client = getattr(current_app, 'redis_client_otp', None)
  if not redis_client:
    return jsonify({"status": "ERROR", "message": "Service tidak tersedia"}), 500

  otp_key = f"otp:{phone}"
  stored_otp = redis_client.get(otp_key)
  # Robustly handle bytes or str
  if isinstance(stored_otp, bytes):
    try:
      decoded_otp = stored_otp.decode('utf-8')
    except Exception:
      decoded_otp = None
  else:
    decoded_otp = stored_otp if stored_otp is None else str(stored_otp)

  if not decoded_otp or decoded_otp != otp_code:
    if client_ip:
      AuthSessionService.track_consecutive_failures(client_ip, "verify_otp", "invalid_otp")
    return jsonify({"status": "ERROR", "message": "OTP tidak valid atau sudah expired"}), 400

  # OTP valid – consume it
  try:
    redis_client.delete(otp_key)
  except Exception:
    pass

  user = db.session.execute(select(User).filter_by(phone_number=phone)).scalar_one_or_none()
  if not user:
    return jsonify({"status": "ERROR", "message": "User tidak ditemukan"}), 404

  device_authorized = False
  device = None
  if client_mac:
    device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
    if device and getattr(device, 'status', None) == 'APPROVED':
      device_authorized = True
      device.last_seen_at = db.func.now()
      device.ip_address = client_ip
      db.session.commit()

  token = create_access_token(identity=str(user.id))
  refresh_token = create_refresh_token(identity=str(user.id))

  if client_ip:
    AuthSessionService.reset_failure_counter(client_ip, "verify_otp")
    AuthSessionService.reset_failure_counter(client_ip, "sync_device")

  if not device_authorized and current_app.config.get('REQUIRE_EXPLICIT_DEVICE_AUTH', False):
    response_data = {
      "status": "DEVICE_AUTHORIZATION_REQUIRED",
      "message": "Perangkat baru terdeteksi. Otorisasi diperlukan.",
      "token": token,
      "user": {"id": str(user.id), "full_name": user.full_name, "role": user.role.value},
      "data": {"device_info": {"mac": client_mac, "ip": client_ip, "user_agent": request.user_agent.string}},
    }
    resp = jsonify(response_data)
    set_refresh_cookies(resp, refresh_token)
    return resp, 200

  # Lanjutkan jika perangkat sudah diotorisasi
  user.last_login_ip = client_ip
  user.last_login_mac = client_mac
  user.last_login_at = db.func.now()
  db.session.commit()

  # Best-effort update ke MikroTik
  try:
    if client_ip:
      list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
      comment = format_to_local_phone(user.phone_number) or ''
      if list_name and comment and client_ip:
        ok, _ = find_and_update_address_list_entry(list_name, client_ip, comment)
        if not ok:
          add_ip_to_address_list(list_name, client_ip, comment)
        if client_mac:
          create_static_lease(client_ip, client_mac, comment)
  except Exception as e:
    logger.warning(f"[VERIFY-OTP] MikroTik update failed: {e}")

  response_data = {
    "status": "SUCCESS",
    "message": "OTP verified successfully",
    "token": token,
    "user_id": str(user.id),
    "user_name": user.full_name,
    "phone": user.phone_number,
    "action": "proceed_to_dashboard",
    "ip": client_ip,
    "mac": client_mac,
    "user": {"id": str(user.id), "full_name": user.full_name, "role": user.role.value},
  }
  resp = jsonify(response_data)
  set_refresh_cookies(resp, refresh_token)
  return resp, 200
