# backend/app/infrastructure/http/user/profile_routes.py
# PENYEMPURNAAN: Beralih ke Flask-JWT-Extended untuk autentikasi.
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportInvalidTypeForm=false

import uuid
from flask import Blueprint, request, jsonify, abort, current_app
from pydantic import ValidationError, constr, BaseModel
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus
from typing import Optional
from flask_jwt_extended import jwt_required, get_current_user # [PERBAIKAN] Impor baru

from app.extensions import db
from app.services import settings_service
from app.services.notification_service import get_notification_message

from app.services.transaction_service import generate_random_password
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user
from app.infrastructure.gateways.mikrotik_client import (
    purge_client_traces,
    remove_ip_from_address_list,
)
from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
from app.utils.formatters import format_to_local_phone
from app.utils.mikrotik_helpers import determine_target_profile

from app.infrastructure.db.models import User, UserRole, UserLoginHistory, UserDevice
from ..schemas.user_schemas import UserProfileResponseSchema, UserProfileUpdateRequestSchema
# [DIHAPUS] Impor decorator lama tidak diperlukan lagi.
# from ..decorators import token_required

profile_bp = Blueprint('user_profile_api', __name__)

@profile_bp.route('/me/profile', methods=['GET', 'PUT'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def handle_my_profile():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    if request.method == 'GET':
        profile_data = UserProfileResponseSchema.model_validate(current_user)
        return jsonify(profile_data.model_dump(mode='json')), HTTPStatus.OK

    elif request.method == 'PUT':
        if current_user.role != UserRole.USER:
            abort(HTTPStatus.FORBIDDEN, description="Endpoint ini hanya untuk pengguna biasa (USER).")

        json_data = request.get_json(silent=True)
        if not json_data:
            return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

        try:
            update_data = UserProfileUpdateRequestSchema.model_validate(json_data)
            user_updated = False

            if update_data.full_name is not None and current_user.full_name != update_data.full_name:
                current_user.full_name, user_updated = update_data.full_name, True
            if hasattr(update_data, 'blok') and current_user.blok != (update_data.blok.value if update_data.blok else None):
                current_user.blok, user_updated = (update_data.blok.value if update_data.blok else None), True
            if hasattr(update_data, 'kamar') and current_user.kamar != (update_data.kamar.value if update_data.kamar else None):
                current_user.kamar, user_updated = (update_data.kamar.value if update_data.kamar else None), True

            if user_updated:
                db.session.commit()
            
            resp_data = UserProfileResponseSchema.model_validate(current_user)
            return jsonify(resp_data.model_dump(mode='json')), HTTPStatus.OK

        except ValidationError as e:
            return jsonify({"message": "Data input tidak valid.", "details": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
        except Exception as e:
            db.session.rollback()
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Kesalahan internal: {str(e)}")

@profile_bp.route('/me/reset-hotspot-password', methods=['POST'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def reset_my_hotspot_password():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    if current_user.is_admin_role:
        abort(HTTPStatus.FORBIDDEN, "Fitur ini tidak untuk role Admin. Gunakan panel admin untuk mereset.")

    mikrotik_username = format_to_local_phone(current_user.phone_number)
    if not mikrotik_username:
        abort(HTTPStatus.BAD_REQUEST, "Format nomor telepon tidak valid.")

    new_password = generate_random_password(length=6)
    
    try:
        mikrotik_profile_name = determine_target_profile(current_user)

        success, msg = activate_or_update_hotspot_user(
            user_mikrotik_username=mikrotik_username,
            mikrotik_profile_name=mikrotik_profile_name, 
            hotspot_password=new_password,
            comment=f"Password Reset by User: {current_user.full_name}", 
            force_update_profile=True
        )
        if not success:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, f"Gagal update password di sistem hotspot: {msg}")

        current_user.mikrotik_password = new_password
        db.session.commit()
        
    except SQLAlchemyError:
        db.session.rollback()
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal menyimpan password baru.")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat reset hotspot password: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, "Gagal mereset password hotspot karena kesalahan sistem.")

    context = {"full_name": current_user.full_name, "username": mikrotik_username, "password": new_password}
    message_body = get_notification_message("user_hotspot_password_reset_by_user", context)
    send_whatsapp_message(current_user.phone_number, message_body)

    return jsonify({"message": "Password hotspot berhasil direset dan dikirim via WhatsApp."}), HTTPStatus.OK

@profile_bp.route('/me/login-history', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_login_history():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        limit = min(max(int(request.args.get('limit', '7')), 1), 20)
        
        login_records = db.session.query(UserLoginHistory)\
            .filter(UserLoginHistory.user_id == current_user.id)\
            .order_by(UserLoginHistory.login_time.desc())\
            .limit(limit).all()
            
        history_data = [
            {
                "login_time": r.login_time.isoformat() if r.login_time else None, 
                "ip_address": r.ip_address, 
                "mac_address": r.mac_address,
                "user_agent_string": r.user_agent_string
            } for r in login_records
        ]
        
        return jsonify(history_data), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error di get_my_login_history: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=f"Gagal mengambil riwayat: {e}")

class DeviceUpdateRequest(BaseModel):
    device_name: constr(strip_whitespace=True, min_length=1, max_length=100)

@profile_bp.route('/me/devices', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_devices():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        devices_data = [
            {
                "id": str(device.id),
                "mac_address": device.mac_address,
                "ip_address": getattr(device, 'ip_address', None),
                "device_name": device.device_name,
                "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                "status": str(getattr(device, 'status').value) if getattr(device, 'status', None) else None,
            }
            for device in current_user.devices
        ]
        return jsonify(devices_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error di get_my_devices: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil daftar perangkat.")

@profile_bp.route('/me/devices/<uuid:device_id>', methods=['DELETE'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def delete_my_device(device_id):
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    device_to_delete = db.session.get(UserDevice, device_id)

    if not device_to_delete:
        return jsonify({"message": "Perangkat tidak ditemukan"}), HTTPStatus.NOT_FOUND

    if device_to_delete.user_id != current_user.id:
        return jsonify({"message": "Akses ditolak. Anda hanya dapat menghapus perangkat sendiri."}), HTTPStatus.FORBIDDEN

    # Lakukan pembersihan jejak di MikroTik (best-effort)
    try:
        list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST', '')
        ip_addr = getattr(device_to_delete, 'ip_address', None)
        mac_addr = device_to_delete.mac_address

        if list_name and ip_addr:
            try:
                remove_ip_from_address_list(list_name, ip_addr)
            except Exception as e:
                current_app.logger.warning(f"Gagal menghapus IP {ip_addr} dari address-list {list_name}: {e}")

        # Purge host, DHCP lease, dan ARP (dynamic) untuk IP/MAC tersebut
        try:
            purge_result = purge_client_traces(ip_addr or '', mac_addr or None, include_binding=False)
            current_app.logger.info(f"Purge client traces result for device {device_id}: {purge_result}")
        except Exception as e:
            current_app.logger.warning(f"Gagal purge client traces untuk perangkat {device_id}: {e}")
    except Exception as e:
        current_app.logger.warning(f"Kesalahan saat pembersihan MikroTik untuk perangkat {device_id}: {e}")

    # Hapus dari database setelah upaya pembersihan
    db.session.delete(device_to_delete)
    db.session.commit()

    current_app.logger.info(f"User {current_user.id} berhasil menghapus perangkat {device_id} (MAC: {device_to_delete.mac_address}).")
    return '', HTTPStatus.NO_CONTENT


@profile_bp.route('/me/devices/<uuid:device_id>', methods=['PUT'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def update_my_device_name(device_id):
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        data = DeviceUpdateRequest.model_validate(request.get_json())
    except ValidationError as e:
        return jsonify({"message": "Payload tidak valid", "details": e.errors()}), HTTPStatus.BAD_REQUEST

    device_to_update = db.session.get(UserDevice, device_id)

    if not device_to_update:
        return jsonify({"message": "Perangkat tidak ditemukan"}), HTTPStatus.NOT_FOUND

    if device_to_update.user_id != current_user.id:
        return jsonify({"message": "Akses ditolak. Anda hanya dapat mengubah perangkat sendiri."}), HTTPStatus.FORBIDDEN

    device_to_update.device_name = data.device_name
    db.session.commit()

    current_app.logger.info(f"User {current_user.id} berhasil mengubah nama perangkat {device_id} menjadi '{data.device_name}'.")
    return jsonify({"message": "Nama perangkat berhasil diperbarui"}), HTTPStatus.OK