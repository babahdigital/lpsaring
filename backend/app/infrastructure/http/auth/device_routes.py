# backend/app/infrastructure/http/auth/device_routes.py
"""
Endpoint untuk manajemen perangkat dan otorisasi.

Alur otorisasi perangkat:
1. User harus login terlebih dahulu (JWT wajib untuk sebagian besar endpoint)
2. Sistem memeriksa apakah perangkat sudah diotorisasi
3. Jika belum diotorisasi, user diminta untuk melakukan otorisasi eksplisit
4. Perangkat yang belum diotorisasi tidak akan dimasukkan ke dalam daftar bypass

Alur perubahan perangkat dengan JWT valid:
1. Saat user dengan JWT valid mengakses dari perangkat berbeda (IP atau MAC berubah)
2. Sistem mendeteksi perubahan dan memeriksa status perangkat baru
3. Jika perangkat baru belum diotorisasi, user diminta otorisasi ulang
4. Perangkat lama dihapus dari daftar bypass jika MAC berubah
5. Jika perangkat berubah dan tidak diotorisasi, user akan logout otomatis

Otorisasi eksplisit bekerja seperti ini:
1. Perangkat default tidak memiliki status otorisasi
2. User harus mengonfirmasi (authorize-device) atau menolak (reject-device) perangkat
3. Hanya perangkat yang diotentikasi yang dapat mengakses jaringan
4. Perubahan perangkat memerlukan otorisasi ulang
"""

import logging
from http import HTTPStatus
import time
from typing import Optional

from flask import Blueprint, jsonify, current_app, request
from sqlalchemy import select
from flask_jwt_extended import jwt_required, get_current_user

from app.extensions import db, limiter
from app.infrastructure.db.models import UserDevice
from app.services.auth_session_service import AuthSessionService
from app.services.client_detection_service import ClientDetectionService
from app.utils.request_utils import get_client_ip, get_client_mac, is_captive_browser_request
from app.utils.formatters import format_to_local_phone
from app.infrastructure.gateways.mikrotik_client import (
    find_and_update_address_list_entry,
    add_ip_to_address_list,
    find_and_remove_static_lease_by_mac,
    create_static_lease,
    purge_user_from_hotspot,
    remove_ip_from_address_list
)

logger = logging.getLogger(__name__)

device_bp = Blueprint('device', __name__, url_prefix='/auth')

# Custom key function to rate-limit by authenticated user when available, else by client IP
def _limit_key_func():
    try:
        user = get_current_user()
        if user and getattr(user, 'id', None):
            return f"user:{user.id}"
    except Exception:
        pass
    try:
        from app.utils.request_utils import get_client_ip
        ip = get_client_ip()
        return f"ip:{ip}"
    except Exception:
        return request.remote_addr or 'anon'

@device_bp.route('/detect-client-info', methods=['GET'])
@limiter.limit("60 per minute;300 per hour", key_func=_limit_key_func)
def detect_client_info():
    """Mendeteksi IP dan MAC address klien."""
    force_refresh = request.headers.get('force-refresh', '').lower() == 'true'
    is_browser = not is_captive_browser_request()
    
    client_ip = get_client_ip()
    rate_limit_key = f"ratelimit:detect:{client_ip}"
    redis_client = getattr(current_app, 'redis_client_otp', None)
    # Fast-path: if localhost and configured to skip lookup, return minimal payload quickly
    try:
        if client_ip in {"127.0.0.1", "::1"} and current_app.config.get('SKIP_MAC_LOOKUP_FOR_LOCALHOST', True):
            payload = ClientDetectionService.get_client_info(
                frontend_ip=client_ip,
                force_refresh=False,
                use_cache=True,
                is_browser=is_browser
            )
            return jsonify(payload), 200
    except Exception:
        pass
    
    if redis_client:
        request_count = redis_client.incr(rate_limit_key)
        if request_count == 1:
            redis_client.expire(rate_limit_key, 60)
        if request_count > 30 and not force_refresh:
            return jsonify({"error": "Rate limited"}), 429
            
    client_info = ClientDetectionService.get_client_info(
        force_refresh=force_refresh, 
        is_browser=is_browser
    )
    return jsonify(client_info), 200


@device_bp.route('/sync-device', methods=['POST'])
@jwt_required()  # ✅ Endpoint ini mewajibkan login terlebih dahulu
@limiter.limit("30 per minute;200 per hour", key_func=_limit_key_func)
def sync_device():
    """
    Sinkronisasi perangkat dengan server.
    User harus login terlebih dahulu (JWT wajib).
    Jika perangkat belum disetujui, user harus melakukan otorisasi eksplisit atau logout.
    
    Jika terdeteksi perubahan IP atau MAC saat token masih valid:
    1. Periksa apakah perangkat baru sudah diotorisasi
    2. Jika belum, minta otorisasi ulang atau logout
    """

    # Dapatkan user yang terautentikasi
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User tidak ditemukan"}), 404

    data = request.get_json(silent=True) or {}
    detection_result = ClientDetectionService.get_client_info(
        frontend_ip=(data.get('ip') or data.get('client_ip')),
        frontend_mac=(data.get('mac') or data.get('client_mac')),
    )
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')
    if client_mac:
        client_mac = client_mac.upper()

    if not client_ip or not client_mac:
        # Kembalikan status non-error agar frontend dapat melakukan retry tanpa memicu error handling
        return jsonify({"status": "DEVICE_NOT_FOUND", "message": "IP/MAC tidak terdeteksi"}), 200

    # LOGIKA DISERDERHANAKAN & LEBIH KUAT
    from app.infrastructure.db.models import DeviceStatus

    # 1) Perangkat APPROVED untuk user saat ini dengan MAC ini => VALID
    approved_device = db.session.execute(
        select(UserDevice).filter_by(user_id=current_user.id, mac_address=client_mac, status=DeviceStatus.APPROVED)
    ).scalar_one_or_none()

    if approved_device:
        ip_updated = False
        old_ip = approved_device.ip_address if approved_device.ip_address and approved_device.ip_address != client_ip else None
        if approved_device.ip_address != client_ip:
            approved_device.ip_address = client_ip
            approved_device.last_seen_at = db.func.now()
            ip_updated = True
            db.session.commit()
            logger.info(f"Updated device IP for user {current_user.id} to {client_ip}")

        try:
            list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
            comment = format_to_local_phone(current_user.phone_number) or ''
            # Cleanup old entries when IP changes
            try:
                find_and_remove_static_lease_by_mac(client_mac)
            except Exception as _:
                pass
            if list_name and old_ip:
                try:
                    remove_ip_from_address_list(list_name, old_ip)
                except Exception as _:
                    pass

            if list_name and comment:
                find_and_update_address_list_entry(list_name, client_ip, comment)
                create_static_lease(client_ip, client_mac, comment)

            current_user.last_login_ip = client_ip
            db.session.commit()

            AuthSessionService.update_session(
                client_ip=client_ip,
                client_mac=client_mac,
                updates={
                    "sync_status": "success",
                    "registered": True,
                    "ip_updated": ip_updated,
                    "device_known": True,
                    "mac_validated": True,
                },
                activity="device_sync_success_existing_device",
            )

            return jsonify({
                "status": "DEVICE_VALID",
                "message": "Perangkat berhasil tersinkronisasi",
                "registered": True,
                "ip_updated": ip_updated,
            }), 200
        except Exception as e:
            logger.error(f"Error saat sinkronisasi perangkat yang sudah ada: {str(e)}")
            return jsonify({"status": "ERROR", "message": "Terjadi kesalahan saat sinkronisasi perangkat"}), 500

    # 2) Jika user punya perangkat APPROVED lain tapi MAC saat ini berbeda => DEVICE_CHANGED
    any_other_approved = db.session.execute(
        select(UserDevice).filter_by(user_id=current_user.id, status=DeviceStatus.APPROVED).limit(1)
    ).scalar_one_or_none()

    # Pastikan ada (atau buat) entri pending untuk MAC saat ini
    existing_for_user = db.session.execute(
        select(UserDevice).filter_by(user_id=current_user.id, mac_address=client_mac)
    ).scalar_one_or_none()
    if not existing_for_user:
        pending = UserDevice()
        pending.user_id = current_user.id
        pending.mac_address = client_mac.upper()
        pending.ip_address = client_ip
        pending.status = DeviceStatus.PENDING
        pending.device_name = detection_result.get('user_agent', 'Perangkat Tidak Dikenal')
        db.session.add(pending)
        db.session.commit()
        device_id = str(pending.id)
    else:
        device_id = str(existing_for_user.id)

    if any_other_approved:
        AuthSessionService.update_session(
            client_ip=client_ip,
            client_mac=client_mac,
            updates={"sync_status": "requires_authorization", "registered": False, "device_changed": True},
            activity="device_sync_device_changed",
        )
        return jsonify({
            "status": "DEVICE_CHANGED",
            "message": "Perubahan perangkat terdeteksi. Otorisasi ulang diperlukan.",
            "registered": False,
            "requires_explicit_authorization": True,
            "data": {"device_info": {"mac": client_mac, "ip": client_ip, "id": device_id}},
        }), 200

    # 3) Tidak ada perangkat APPROVED untuk user ini => perlu otorisasi eksplisit
    AuthSessionService.update_session(
        client_ip=client_ip,
        client_mac=client_mac,
        updates={"sync_status": "requires_authorization", "registered": False},
        activity="device_sync_requires_explicit_auth",
    )

    return jsonify({
        "status": "DEVICE_AUTHORIZATION_REQUIRED",
        "registered": False,
        "requires_explicit_authorization": True,
        "message": "Perangkat memerlukan otorisasi eksplisit",
        "data": {"device_info": {"mac": client_mac, "ip": client_ip, "id": device_id}},
    }), 200


@device_bp.route('/authorize-device', methods=['POST'])
@jwt_required()
@limiter.limit("20 per minute;100 per hour", key_func=_limit_key_func)
def authorize_device():
    """Otorisasi perangkat baru secara eksplisit."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User tidak ditemukan"}), 404

    data = request.get_json() or {}
    
    # Gunakan data dari request jika tersedia, jika tidak deteksi dari request
    detection_result = ClientDetectionService.get_client_info(
        frontend_ip=(data.get('client_ip') or data.get('ip')),
        frontend_mac=(data.get('client_mac') or data.get('mac'))
    )
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')
    device_id = data.get('device_id')
    
    if not client_ip or not client_mac:
        return jsonify({"status": "ERROR", "message": "IP/MAC tidak terdeteksi"}), 400

    # Penegakan batas perangkat per user (hanya berlaku untuk perangkat baru)
    try:
        from app.infrastructure.db.models import DeviceStatus
        from sqlalchemy import func
        max_devices = int(current_app.config.get('MAX_DEVICES_PER_USER', 3))
        approved_count = db.session.execute(
            select(func.count()).select_from(UserDevice).filter_by(user_id=current_user.id, status=DeviceStatus.APPROVED)
        ).scalar_one()
    except Exception:
        max_devices = 3
        approved_count = 0

    # Coba temukan perangkat berdasarkan ID jika diberikan
    device = None
    if device_id:
        try:
            from uuid import UUID
            device = db.session.get(UserDevice, UUID(device_id))
        except (ValueError, TypeError):
            pass
    
    # Jika tidak ditemukan berdasarkan ID, coba cari berdasarkan MAC
    if not device:
        device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
    
    # Jika masih tidak ditemukan, ini perangkat baru: cek limit terlebih dahulu
    if not device:
        if approved_count >= max_devices:
            logger.warning(f"[AUTHORIZE-DEVICE] User {current_user.id} reached device limit ({approved_count}/{max_devices}) for MAC {client_mac}")
            return jsonify({
                "status": "DEVICE_LIMIT_REACHED",
                "message": f"Batas maksimal {max_devices} perangkat terotorisasi telah tercapai. Hapus perangkat lama terlebih dahulu.",
            }), 403
        device = UserDevice()
        device.user = current_user
        device.mac_address = client_mac.upper() 
        device.ip_address = client_ip
        device.status = DeviceStatus.APPROVED
        device.last_seen_at = db.func.now()
        db.session.add(device)
    else:
        from app.infrastructure.db.models import DeviceStatus
        device.status = DeviceStatus.APPROVED
        device.user = current_user
        device.ip_address = client_ip
        device.last_seen_at = db.func.now()
    
    db.session.commit()

    list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
    comment = format_to_local_phone(current_user.phone_number) or ''
    
    # Update di MikroTik
    try:
        # Remove any existing static lease for this MAC to avoid duplicates
        try:
            find_and_remove_static_lease_by_mac(client_mac)
        except Exception as _:
            pass
        if list_name and comment:
            find_and_update_address_list_entry(list_name, client_ip, comment)
            create_static_lease(client_ip, client_mac, comment)
            purge_user_from_hotspot(comment)
    except Exception as e:
        logger.error(f"[AUTHORIZE-DEVICE] MikroTik update failed: {e}")

    # Jika user tidak aktif, pastikan IP langsung dipindahkan ke inactive_client
    try:
        from app.infrastructure.gateways.mikrotik_client import move_user_to_inactive_list
        # Refresh minimal status dari DB
        db.session.refresh(current_user)
        if not current_user.is_active:
            logger.info(f"[AUTHORIZE-DEVICE] User non-aktif, memindahkan {client_ip} ke inactive_client")
            move_user_to_inactive_list(client_ip, comment)
    except Exception as e:
        logger.warning(f"[AUTHORIZE-DEVICE] Gagal memindahkan IP ke inactive_client: {e}")

    return jsonify({
        "status": "SUCCESS", 
        "message": "Perangkat berhasil diotorisasi",
        "device_id": str(device.id)
    }), 200

@device_bp.route('/invalidate-device', methods=['POST'])
@jwt_required()
def invalidate_device():
    """
    Menghapus akses untuk perangkat tertentu dan menghapusnya dari bypass address list.
    Digunakan saat terjadi perubahan perangkat atau user logout.
    """
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User tidak ditemukan"}), 404

    data = request.get_json() or {}
    device_id = data.get('device_id')
    client_mac = data.get('mac') or data.get('client_mac')
    client_ip = data.get('ip') or data.get('client_ip')
    force = data.get('force', False)
    
    device = None
    
    # Cari perangkat berdasarkan ID, MAC, atau IP
    if device_id:
        try:
            from uuid import UUID
            device = db.session.get(UserDevice, UUID(device_id))
        except (ValueError, TypeError):
            pass
            
    if not device and client_mac:
        device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
        
    if not device and client_ip:
        device = db.session.execute(select(UserDevice).filter_by(ip_address=client_ip)).scalar_one_or_none()
    
    if not device:
        return jsonify({
            "status": "ERROR", 
            "message": "Perangkat tidak ditemukan"
        }), 404
    
    # Pastikan hanya pemilik yang bisa menghapus perangkatnya (atau admin)
    if not force and device.user_id != current_user.id:
        return jsonify({
            "status": "ERROR", 
            "message": "Tidak memiliki izin untuk menghapus perangkat ini"
        }), 403
        
    try:
        # Hapus dari bypass address list
        list_name = current_app.config.get('MIKROTIK_BYPASS_ADDRESS_LIST')
        if list_name and device.ip_address:
            remove_ip_from_address_list(list_name, device.ip_address)
            
        # Hapus DHCP lease jika ada
        if device.mac_address:
            find_and_remove_static_lease_by_mac(device.mac_address)
            
        # Hapus dari database
        db.session.delete(device)
        db.session.commit()
        
        logger.info(f"Device {device_id or client_mac or client_ip} invalidated and removed from access lists")
        
        return jsonify({
            "status": "SUCCESS",
            "message": "Perangkat berhasil dihapus dari daftar akses"
        }), 200
    except Exception as e:
        logger.error(f"Error invalidating device: {str(e)}")
        return jsonify({
            "status": "ERROR",
            "message": f"Gagal menghapus perangkat: {str(e)}"
        }), 500


@device_bp.route('/reject-device', methods=['POST'])
@jwt_required()
def reject_device():
    """Menolak otorisasi perangkat baru."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "ERROR", "message": "User tidak ditemukan"}), 404

    data = request.get_json() or {}
    
    # Gunakan data dari request jika tersedia, jika tidak deteksi dari request
    detection_result = ClientDetectionService.get_client_info(
        frontend_ip=(data.get('client_ip') or data.get('ip')),
        frontend_mac=(data.get('client_mac') or data.get('mac'))
    )
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')
    device_id = data.get('device_id')
    reason = data.get('reason', 'user_rejected')
    
    logger.warning(f"[REJECT-DEVICE] User {current_user.id} menolak otorisasi perangkat: MAC={client_mac}, IP={client_ip}, reason={reason}")
    
    # Update status perangkat jika ada
    if client_mac or device_id:
        # Coba temukan perangkat berdasarkan ID jika diberikan
        device = None
        if device_id:
            try:
                from uuid import UUID
                device = db.session.get(UserDevice, UUID(device_id))
            except (ValueError, TypeError):
                pass
        
        # Jika tidak ditemukan berdasarkan ID, coba cari berdasarkan MAC
        if not device and client_mac:
            device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
        
        if device:
            # Catat penolakan perangkat di log saja karena model belum mendukung status REJECTED
            logger.info(f"[DEVICE-REJECTED] Device {device.id} rejected by user {current_user.id}, reason: {reason}")
            # Hapus perangkat dari database
            db.session.delete(device)
            db.session.commit()
    
    return jsonify({"status": "SUCCESS", "message": "Penolakan perangkat tercatat."}), 200


@device_bp.route('/check-token-device', methods=['GET', 'POST'])
@jwt_required(optional=True)
@limiter.limit("60 per minute;300 per hour", key_func=_limit_key_func)
def check_token_device():
    """
    Memeriksa status token dan perangkat saat ini.
    Endpoint ini dapat diakses dengan atau tanpa autentikasi.
    Mengembalikan informasi tentang:
    - Status autentikasi token
    - Status otorisasi perangkat
    - Apakah terjadi perubahan perangkat sejak login
    """
    # Dapatkan user dari token jika ada
    current_user = get_current_user()
    
    # Deteksi informasi perangkat
    data = request.get_json(silent=True) or {}
    detection_result = ClientDetectionService.get_client_info(
        frontend_ip=(data.get('ip') or data.get('client_ip')),
        frontend_mac=(data.get('mac') or data.get('client_mac'))
    )
    
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')
    
    result = {
        "detected_ip": client_ip,
        "detected_mac": client_mac,
        "authenticated": current_user is not None,
    }
    
    # Jika user terautentikasi, periksa perubahan perangkat
    if current_user:
        result["user_id"] = str(current_user.id)
        result["phone_number"] = current_user.phone_number
        
        # Cek perubahan IP
        ip_changed = False
        if current_user.last_login_ip and current_user.last_login_ip != client_ip:
            ip_changed = True
            result["ip_changed"] = True
            result["previous_ip"] = current_user.last_login_ip
        
        # Cek perangkat yang sudah diotorisasi
        devices = db.session.execute(
            select(UserDevice)
            .filter_by(user_id=current_user.id)
            .filter_by(status='APPROVED')
        ).scalars().all()
        
        # Cek apakah perangkat saat ini ada di daftar yang disetujui
        device_found = False
        for device in devices:
            if device.mac_address == client_mac:
                device_found = True
                result["device_id"] = str(device.id)
                result["device_authorized"] = True
                break
        
        if not device_found and len(devices) > 0:
            # MAC tidak dikenal tapi user memiliki perangkat yang disetujui
            result["device_changed"] = True
            result["device_authorized"] = False
            result["action_required"] = "authorize_device"
    
    # Tambahkan informasi perangkat saat ini
    device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
    if device:
        result["current_device"] = {
            "id": str(device.id),
            "status": device.status if hasattr(device, 'status') else None,
            "user_id": str(device.user_id) if device.user_id else None,
            "is_approved": device.status == 'APPROVED' if hasattr(device, 'status') else False,
        }
    
    return jsonify(result), 200


@device_bp.route('/check-device-status', methods=['GET', 'POST'])
@limiter.limit("60 per minute;300 per hour", key_func=_limit_key_func)
def check_device_status():
    """
    Memeriksa status otorisasi perangkat saat ini.
    Endpoint ini dapat diakses tanpa autentikasi untuk memudahkan pengecekan awal.
    """
    # Jika POST, ambil data dari body, jika GET gunakan auto-deteksi
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        detection_result = ClientDetectionService.get_client_info(
            frontend_ip=(data.get('ip') or data.get('client_ip')),
            frontend_mac=(data.get('mac') or data.get('client_mac'))
        )
    else:
        detection_result = ClientDetectionService.get_client_info()
    
    client_ip = detection_result.get('detected_ip')
    client_mac = detection_result.get('detected_mac')

    if not client_ip or not client_mac:
        return jsonify({
            "status": "ERROR", 
            "message": "IP/MAC tidak terdeteksi",
            "device_info": detection_result
        }), 400
    
    # Cek status perangkat di database
    device = db.session.execute(select(UserDevice).filter_by(mac_address=client_mac)).scalar_one_or_none()
    requires_auth = current_app.config.get("REQUIRE_EXPLICIT_DEVICE_AUTH", False)
    
    result = {
        "detected_ip": client_ip,
        "detected_mac": client_mac,
        "device_found": device is not None,
        "requires_authorization": requires_auth,
    }
    
    # Tambahkan detail perangkat jika ditemukan
    if device:
        result.update({
            "device_id": str(device.id),
            "status": device.status if hasattr(device, 'status') else None,
            "is_approved": device.status == 'APPROVED' if hasattr(device, 'status') else False,
            "user_id": str(device.user_id) if device.user_id else None,
            "last_seen": device.last_seen_at.isoformat() if device.last_seen_at else None,
        })
        
        # Tambahkan informasi user jika ada
        if device.user:
            result["user"] = {
                "phone_number": device.user.phone_number,
                "full_name": device.user.full_name
            }
    
    return jsonify(result), 200
