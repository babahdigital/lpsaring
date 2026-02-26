# backend/app/services/user_management/user_quota.py

from typing import Any, Tuple
from datetime import timedelta
from flask import current_app

from datetime import datetime, timezone as dt_timezone

from app.extensions import db
from app.infrastructure.db.models import User, UserRole, AdminActionType
from app.utils.formatters import format_to_local_phone, get_app_local_datetime
from app.services import settings_service

# [PERBAIKAN] Impor fungsi `_generate_password` yang hilang dari helper.
from .helpers import _log_admin_action, _generate_password, _handle_mikrotik_operation, _send_whatsapp_notification
from . import user_debt
from app.infrastructure.gateways.mikrotik_client import activate_or_update_hotspot_user
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, get_ip_by_mac, upsert_ip_binding
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.hotspot_sync_service import resolve_target_profile_for_user, sync_address_list_for_single_user
from app.utils.formatters import get_app_date_time_strings


def _sync_ip_binding_for_authorized_devices(user: User, api_conn: Any, source: str) -> None:
    if not api_conn or not getattr(user, "devices", None):
        return

    target_binding_type = resolve_allowed_binding_type_for_user(user)
    username_08 = format_to_local_phone(getattr(user, "phone_number", None) or "") or ""
    now_utc = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now_utc)
    server_name = getattr(user, "mikrotik_server_name", None)

    for device in user.devices:
        if not getattr(device, "is_authorized", False):
            continue

        mac_address = (getattr(device, "mac_address", None) or "").strip().upper()
        if not mac_address:
            continue

        ip_address = getattr(device, "ip_address", None)
        if not ip_address:
            ok_ip, ip_from_mac, _msg = get_ip_by_mac(api_conn, mac_address)
            if ok_ip and ip_from_mac:
                ip_address = ip_from_mac

        ok, msg = upsert_ip_binding(
            api_connection=api_conn,
            mac_address=mac_address,
            address=ip_address,
            server=server_name,
            binding_type=target_binding_type,
            comment=(
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source={source}|date={date_str}|time={time_str}"
            ),
        )
        if not ok:
            current_app.logger.warning(
                "Gagal sync ip-binding untuk user %s mac %s: %s",
                user.id,
                mac_address,
                msg,
            )


def inject_user_quota(user: User, admin_actor: User, mb_to_add: int, days_to_add: int) -> Tuple[bool, str]:
    """
    [PEROMBAKAN TOTAL] Logika injeksi kuota dan masa aktif yang baru.
    - Menerapkan hak akses baru untuk Admin.
    - Menangani kasus injeksi masa aktif untuk pengguna unlimited.
    """
    # Langkah 1: Validasi Hak Akses
    if not admin_actor.is_super_admin_role:
        if user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            return False, "Admin tidak dapat melakukan injeksi untuk akun Admin atau Super Admin."

    if mb_to_add < 0 or days_to_add < 0:
        return False, "Jumlah MB atau Hari tidak boleh negatif."
    if mb_to_add == 0 and days_to_add == 0:
        return False, "Tidak ada yang ditambahkan."

    now = get_app_local_datetime()

    # Langkah 2: Logika untuk Pengguna UNLIMITED
    if user.is_unlimited_user:
        if mb_to_add > 0:
            return False, "Tidak dapat menambah kuota (GB) untuk pengguna unlimited. Hanya bisa menambah masa aktif."
        if days_to_add <= 0:
            return False, "Anda hanya bisa menambah masa aktif untuk pengguna unlimited."

        current_expiry = user.quota_expiry_date
        user.quota_expiry_date = (current_expiry if current_expiry and current_expiry > now else now) + timedelta(
            days=days_to_add
        )
        normalized_expiry = user.quota_expiry_date or now

        # Untuk unlimited, kita hanya perlu update session timeout di Mikrotik (jika ada)
        timeout_seconds = int((normalized_expiry - now).total_seconds())
        limit_bytes_total = 0  # Unlimited tidak punya batasan kuota
        comment = f"Extend unlimited {days_to_add}d by {admin_actor.full_name}"
        action_details = {
            "added_days_for_unlimited": int(days_to_add),
            # Keys used by admin log UI formatter.
            "added_mb": 0,
            "added_days": int(days_to_add),
        }

    # Langkah 3: Logika untuk Pengguna TERBATAS
    else:
        # Requirement: injection is disabled only when there is MANUAL debt.
        manual_debt_mb = int(getattr(user, "manual_debt_mb", 0) or 0)
        if manual_debt_mb > 0:
            return (
                False,
                "Tidak bisa inject kuota karena pengguna masih memiliki tunggakan. "
                "Silakan lunasi/clear tunggakan terlebih dahulu, atau gunakan fitur 'Tambah Tunggakan (Pilih Paket)'.",
            )

        # Potong debt (otomatis + manual) terlebih dahulu dari quota inject.
        purchased_before = int(user.total_quota_purchased_mb or 0)
        used_before = float(user.total_quota_used_mb or 0.0)
        manual_debt_before = int(getattr(user, "manual_debt_mb", 0) or 0)

        paid_auto_mb, paid_manual_mb, remaining_injected_mb = user_debt.consume_injected_mb_for_debt(
            user=user,
            admin_actor=admin_actor,
            injected_mb=int(mb_to_add),
            source="inject_quota",
        )

        # Sisa inject setelah debt lunas benar-benar menambah kuota.
        if remaining_injected_mb > 0:
            user.total_quota_purchased_mb = int(user.total_quota_purchased_mb or 0) + int(remaining_injected_mb)

        current_expiry = user.quota_expiry_date
        if days_to_add > 0:
            user.quota_expiry_date = (current_expiry if current_expiry and current_expiry > now else now) + timedelta(
                days=days_to_add
            )

        purchased_mb = user.total_quota_purchased_mb or 0
        limit_bytes_total = int(purchased_mb * 1024 * 1024)
        normalized_expiry = user.quota_expiry_date or now
        timeout_seconds = int((normalized_expiry - now).total_seconds())
        comment = f"Inject {mb_to_add}MB/{days_to_add}d by {admin_actor.full_name}"
        action_details = {
            "requested_inject_mb": int(mb_to_add),
            "requested_inject_days": int(days_to_add),
            # Keys used by admin log UI formatter.
            "added_mb": int(mb_to_add),
            "added_days": int(days_to_add),
            "paid_auto_debt_mb": int(paid_auto_mb),
            "paid_manual_debt_mb": int(paid_manual_mb),
            "net_added_mb": int(remaining_injected_mb),
            "manual_debt_before_mb": int(manual_debt_before),
            "manual_debt_after_mb": int(getattr(user, "manual_debt_mb", 0) or 0),
            "purchased_before_mb": int(purchased_before),
            "used_before_mb": float(used_before),
            "purchased_after_mb": int(user.total_quota_purchased_mb or 0),
        }

    # Langkah 4: Sinkronisasi ke Mikrotik
    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    target_profile = resolve_target_profile_for_user(user)
    current_profile = (getattr(user, "mikrotik_profile_name", None) or "").strip()
    should_force_profile_update = (not current_profile) or (target_profile != current_profile)

    action_details["target_profile"] = target_profile
    action_details["force_profile_update"] = bool(should_force_profile_update)

    mikrotik_success, mikrotik_msg = _handle_mikrotik_operation(
        activate_or_update_hotspot_user,
        user_mikrotik_username=format_to_local_phone(user.phone_number),
        hotspot_password=user.mikrotik_password,
        mikrotik_profile_name=target_profile,
        comment=comment,
        limit_bytes_total=max(0, limit_bytes_total),
        session_timeout_seconds=max(0, timeout_seconds),
        server=user.mikrotik_server_name,
        force_update_profile=should_force_profile_update,
    )

    if not mikrotik_success:
        # Rollback perubahan jika sinkronisasi gagal
        db.session.rollback()
        current_app.logger.error(f"Gagal sinkronisasi injeksi kuota untuk {user.id}: {mikrotik_msg}")
        return False, f"Gagal sinkronisasi dengan Mikrotik: {mikrotik_msg}"

    user.mikrotik_user_exists = True
    user.mikrotik_profile_name = target_profile

    # Sinkronisasi akses (address-list + ip-binding type) agar efek inject langsung terasa.
    try:
        sync_address_list_for_single_user(user)
    except Exception as e:
        current_app.logger.warning(
            "Gagal sync address-list setelah inject untuk user %s: %s",
            user.id,
            e,
        )

    try:
        with get_mikrotik_connection() as api_conn:
            if api_conn:
                _sync_ip_binding_for_authorized_devices(user, api_conn, source="inject_quota")
    except Exception as e:
        current_app.logger.warning(
            "Gagal sync ip-binding setelah inject untuk user %s: %s",
            user.id,
            e,
        )

    # Langkah 5: Catat Log dan Kirim Notifikasi
    _log_admin_action(
        admin_actor, user, AdminActionType.INJECT_QUOTA, {**action_details, "mikrotik_sync_success": mikrotik_success}
    )

    # Notifikasi WhatsApp untuk inject quota (termasuk potongan debt).
    try:
        if not user.is_unlimited_user:
            purchased_now = float(user.total_quota_purchased_mb or 0.0)
            used_now = float(user.total_quota_used_mb or 0.0)
            remaining_mb = max(0.0, purchased_now - used_now)

            paid_auto_mb = int(action_details.get("paid_auto_debt_mb") or 0)
            paid_manual_mb = int(action_details.get("paid_manual_debt_mb") or 0)
            paid_total_mb = paid_auto_mb + paid_manual_mb

            _send_whatsapp_notification(
                user.phone_number,
                "user_quota_injected",
                {
                    "full_name": user.full_name,
                    "injected_mb": int(mb_to_add),
                    "injected_gb": user_debt.mb_to_gb_str(int(mb_to_add)),
                    "paid_debt_mb": int(paid_total_mb),
                    "paid_debt_gb": user_debt.mb_to_gb_str(int(paid_total_mb)),
                    "paid_debt_auto_mb": int(paid_auto_mb),
                    "paid_debt_manual_mb": int(paid_manual_mb),
                    "net_added_mb": int(action_details.get("net_added_mb") or 0),
                    "net_added_gb": user_debt.mb_to_gb_str(int(action_details.get("net_added_mb") or 0)),
                    "effective_quota_mb": int(action_details.get("net_added_mb") or 0),
                    "effective_quota_gb": user_debt.mb_to_gb_str(int(action_details.get("net_added_mb") or 0)),
                    "added_days": int(days_to_add),
                    "remaining_mb": float(remaining_mb),
                },
            )
    except Exception as e:
        current_app.logger.warning("Gagal mengirim notifikasi inject quota untuk user %s: %s", user.id, e)

    return True, f"Berhasil memperbarui kuota/masa aktif untuk {user.full_name}."


def set_user_unlimited(user: User, admin_actor: User, make_unlimited: bool) -> Tuple[bool, str]:
    """
    Versi yang disederhanakan dan lebih aman untuk mengatur status unlimited.
    """
    if user.is_unlimited_user == make_unlimited:
        return True, "Pengguna sudah dalam status yang diminta."

    # Panggilan `_generate_password` di sini yang sebelumnya menyebabkan error.
    if not user.mikrotik_password:
        user.mikrotik_password = _generate_password()

    user.is_unlimited_user = make_unlimited

    if make_unlimited:
        action_type = AdminActionType.SET_UNLIMITED_STATUS
        user.mikrotik_profile_name = settings_service.get_setting("MIKROTIK_UNLIMITED_PROFILE", "unlimited")
        limit_bytes_total = 0
        session_timeout_seconds = 0
        status_text = "dijadikan"
    else:  # Revoke unlimited
        action_type = AdminActionType.REVOKE_UNLIMITED_STATUS
        if getattr(user, "role", None) == UserRole.KOMANDAN:
            user.mikrotik_profile_name = settings_service.get_setting("MIKROTIK_KOMANDAN_PROFILE", "komandan")
        else:
            user.mikrotik_profile_name = (
                settings_service.get_setting("MIKROTIK_ACTIVE_PROFILE", None)
                or settings_service.get_setting("MIKROTIK_USER_PROFILE", "user")
                or settings_service.get_setting("MIKROTIK_DEFAULT_PROFILE", "default")
            )
        limit_bytes_total = 1
        session_timeout_seconds = 0
        status_text = "dikembalikan dari"

    mikrotik_success, mikrotik_msg = _handle_mikrotik_operation(
        activate_or_update_hotspot_user,
        user_mikrotik_username=format_to_local_phone(user.phone_number),
        hotspot_password=user.mikrotik_password,
        mikrotik_profile_name=user.mikrotik_profile_name,
        limit_bytes_total=limit_bytes_total,
        session_timeout_seconds=session_timeout_seconds,
        server=user.mikrotik_server_name,
        force_update_profile=True,
        comment=f"Set unlimited to {make_unlimited} by {admin_actor.full_name}",
    )

    if not mikrotik_success:
        return False, f"Gagal sinkronisasi Mikrotik: {mikrotik_msg}"

    user.mikrotik_user_exists = True

    if make_unlimited:
        try:
            user_debt.clear_all_debts_to_zero(
                user=user,
                admin_actor=admin_actor,
                source="set_unlimited",
            )
        except Exception as e:
            current_app.logger.warning(
                "Gagal clear debt saat set unlimited untuk user %s: %s",
                user.id,
                e,
            )

        blocked_reason = str(getattr(user, "blocked_reason", "") or "")
        if bool(getattr(user, "is_blocked", False)) and (
            blocked_reason.startswith("quota_auto_debt_limit|")
            or blocked_reason.startswith("quota_manual_debt_end_of_month|")
        ):
            user.is_blocked = False
            user.blocked_reason = None
            user.blocked_at = None
            user.blocked_by_id = None

    # Sinkronisasi akses (address-list + ip-binding type) agar perubahan unlimited langsung terasa.
    # Catatan: kalau user masih diblokir manual, address-list akan tetap mengikuti status blocked.
    try:
        sync_address_list_for_single_user(user)
    except Exception as e:
        current_app.logger.warning(
            "Gagal sync address-list setelah set unlimited untuk user %s: %s",
            user.id,
            e,
        )

    try:
        with get_mikrotik_connection() as api_conn:
            if api_conn:
                _sync_ip_binding_for_authorized_devices(
                    user,
                    api_conn,
                    source="set_unlimited",
                )
    except Exception as e:
        current_app.logger.warning(
            "Gagal sync ip-binding setelah set unlimited untuk user %s: %s",
            user.id,
            e,
        )

    if not admin_actor.is_super_admin_role:
        _log_admin_action(
            admin_actor, user, action_type, {"status": make_unlimited, "profile": user.mikrotik_profile_name}
        )

    return True, f"Status unlimited untuk {user.full_name} berhasil {status_text} unlimited."
