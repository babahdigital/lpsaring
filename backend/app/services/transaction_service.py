# backend/app/services/transaction_service.py
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.infrastructure.db.models import Transaction, TransactionStatus
from app.services import settings_service
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_ip_by_mac,
    upsert_ip_binding,
)
from app.services.hotspot_sync_service import sync_address_list_for_single_user
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.utils.formatters import format_to_local_phone, get_app_date_time_strings

logger = logging.getLogger(__name__)


def _sync_ip_binding_for_authorized_devices(user, mikrotik_api: Any, date_str: str, time_str: str) -> None:
    if not mikrotik_api or not getattr(user, 'devices', None):
        return

    target_binding_type = resolve_allowed_binding_type_for_user(user)
    username_08 = format_to_local_phone(getattr(user, 'phone_number', None) or '') or ''
    server_name = getattr(user, 'mikrotik_server_name', None)
    synced_count = 0

    for device in user.devices:
        if not getattr(device, 'is_authorized', False):
            continue

        mac_address = (getattr(device, 'mac_address', None) or '').strip().upper()
        if not mac_address:
            continue

        ip_address = getattr(device, 'ip_address', None)
        ok, message = upsert_ip_binding(
            api_connection=mikrotik_api,
            mac_address=mac_address,
            address=ip_address,
            server=server_name,
            binding_type=target_binding_type,
            comment=(
                f"authorized|user={username_08}|uid={user.id}|role={user.role.value}"
                f"|source=transaction|date={date_str}|time={time_str}"
            ),
        )
        if ok:
            synced_count += 1
        else:
            logger.warning(
                "Gagal update ip-binding setelah transaksi untuk user %s mac %s: %s",
                user.id,
                mac_address,
                message,
            )

    logger.info(
        "Sinkronisasi ip-binding pasca transaksi untuk user %s: type=%s, synced=%s",
        user.id,
        target_binding_type,
        synced_count,
    )


def _add_candidate_ip(candidates: list[str], seen: set[str], ip_value: Any) -> None:
    if not ip_value:
        return
    ip_str = str(ip_value).strip()
    if not ip_str or ip_str in seen:
        return
    seen.add(ip_str)
    candidates.append(ip_str)


def _resolve_candidate_ips(user, mikrotik_api: Any) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    if mikrotik_api:
        ok_binding, binding_map, _msg = get_hotspot_ip_binding_user_map(mikrotik_api)
        if ok_binding and binding_map:
            user_id_str = str(getattr(user, 'id', ''))
            for entry in binding_map.values():
                if str(entry.get('user_id')) != user_id_str:
                    continue
                _add_candidate_ip(candidates, seen, entry.get('address'))

        ok_host, host_usage_map, _msg = get_hotspot_host_usage_map(mikrotik_api)
        if ok_host and host_usage_map and getattr(user, 'devices', None):
            for device in user.devices:
                mac = (device.mac_address or '').upper()
                if not mac:
                    continue
                host_entry = host_usage_map.get(mac)
                if host_entry:
                    _add_candidate_ip(candidates, seen, host_entry.get('address'))

    if getattr(user, 'devices', None):
        for device in user.devices:
            _add_candidate_ip(candidates, seen, device.ip_address)

        if mikrotik_api:
            for device in user.devices:
                mac = (device.mac_address or '').upper()
                if not mac:
                    continue
                ok_ip, ip_from_mac, _msg = get_ip_by_mac(mikrotik_api, mac)
                if ok_ip and ip_from_mac:
                    _add_candidate_ip(candidates, seen, ip_from_mac)

    return candidates


def generate_random_password(length: int = 6) -> str:
    """Menghasilkan password numerik acak dengan panjang yang ditentukan."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def apply_package_and_sync_to_mikrotik(
    transaction: Transaction, mikrotik_api: Any
) -> tuple[bool, str]:
    """
    Logika inti yang disempurnakan.
    1. Menerapkan manfaat paket ke objek User.
    2. Melakukan sinkronisasi langsung ke Mikrotik.
    3. Mengembalikan status keberhasilan untuk di-commit atau di-rollback oleh pemanggil.
    """
    if not transaction or transaction.status != TransactionStatus.SUCCESS:
        msg = f"Mencoba menerapkan paket dari transaksi yang tidak valid atau belum sukses: ID {transaction.id if transaction else 'N/A'}"
        logger.warning(msg)
        return False, msg

    user = transaction.user
    package = transaction.package

    if not user or not package or not package.profile:
        msg = f"Transaksi {transaction.id} tidak memiliki user, paket, atau profil paket yang valid."
        logger.error(msg)
        return False, msg

    logger.info(
        f"Menerapkan paket '{package.name}' ke pengguna '{user.full_name}' dari transaksi {transaction.id}."
    )

    is_unlimited_package = Decimal(str(package.data_quota_gb)) == Decimal("0")
    user.is_unlimited_user = is_unlimited_package

    if is_unlimited_package:
        user.total_quota_purchased_mb = 0
        logger.info(f"User ID {user.id} diproses sebagai PENGGUNA UNLIMITED.")
    else:
        user.is_unlimited_user = False
        added_quota_mb = int(float(package.data_quota_gb) * 1024)
        user.total_quota_purchased_mb = (
            user.total_quota_purchased_mb or 0
        ) + added_quota_mb
        logger.info(
            f"User ID {user.id} diproses sebagai PENGGUNA BERKUOTA dengan tambahan {added_quota_mb} MB."
        )

    duration_to_add = timedelta(days=package.duration_days)
    now_utc = datetime.now(dt_timezone.utc)
    date_str, time_str = get_app_date_time_strings(now_utc)

    if user.quota_expiry_date and user.quota_expiry_date > now_utc:
        user.quota_expiry_date += duration_to_add
    else:
        user.quota_expiry_date = now_utc + duration_to_add

    if not user.mikrotik_password or not (
        len(user.mikrotik_password) == 6 and user.mikrotik_password.isdigit()
    ):
        user.mikrotik_password = generate_random_password()
    transaction.hotspot_password = user.mikrotik_password

    if not mikrotik_api:
        msg = "Koneksi Mikrotik tidak tersedia, sinkronisasi dilewati."
        logger.warning(msg)
        return True, msg

    hotspot_username = format_to_local_phone(user.phone_number)
    if not hotspot_username:
        msg = f"Format nomor telepon user {user.id} tidak valid untuk Mikrotik."
        logger.error(msg)
        return False, msg

    mikrotik_profile_to_set = package.profile.profile_name
    if user.is_unlimited_user:
        unlimited_profile_name = settings_service.get_setting('MIKROTIK_UNLIMITED_PROFILE', 'unlimited')
        logger.info(
            f"User ID {user.id} adalah UNLIMITED. Mengganti profil dari '{mikrotik_profile_to_set}' menjadi '{unlimited_profile_name}'."
        )
        mikrotik_profile_to_set = unlimited_profile_name

    limit_bytes_total = (
        0
        if user.is_unlimited_user
        else int((user.total_quota_purchased_mb or 0) * 1024 * 1024)
    )
    expiry_date = user.quota_expiry_date or now_utc
    session_timeout_seconds = max(0, int((expiry_date - now_utc).total_seconds()))

    # --- PENYEMPURNAAN: Menyiapkan parameter server secara dinamis ---
    params_for_mt = {
        'api_connection': mikrotik_api,
        'user_mikrotik_username': hotspot_username,
        'mikrotik_profile_name': mikrotik_profile_to_set,
        'hotspot_password': user.mikrotik_password,
        'comment': f"Order:{transaction.midtrans_order_id}|package={package.name}|date={date_str}|time={time_str}",
        'limit_bytes_total': limit_bytes_total,
        'session_timeout_seconds': session_timeout_seconds,
        'force_update_profile': True,
    }

    # Tambahkan parameter 'server' hanya jika ada nilainya di data user
    if hasattr(user, 'mikrotik_server_name') and user.mikrotik_server_name:
        params_for_mt['server'] = user.mikrotik_server_name
        logger.info(
            f"Sinkronisasi ke Mikrotik untuk user '{hotspot_username}' pada SERVER: '{user.mikrotik_server_name}', PROFIL: '{mikrotik_profile_to_set}'."
        )
    else:
        logger.info(
            f"Sinkronisasi ke Mikrotik untuk user '{hotspot_username}' pada SEMUA SERVER (default), PROFIL: '{mikrotik_profile_to_set}'."
        )
    # -----------------------------------------------------------------

    # Memanggil fungsi dengan parameter yang sudah lengkap
    success_mt, msg_mt = activate_or_update_hotspot_user(**params_for_mt)

    if not success_mt:
        logger.error(
            f"SINKRONISASI MIKROTIK GAGAL untuk user '{hotspot_username}'. Pesan: {msg_mt}."
        )
        return False, f"Gagal sinkronisasi ke Mikrotik: {msg_mt}"

    _sync_ip_binding_for_authorized_devices(user, mikrotik_api, date_str, time_str)

    user.mikrotik_profile_name = mikrotik_profile_to_set

    address_synced = False
    try:
        address_synced = sync_address_list_for_single_user(user)
    except Exception as sync_error:
        logger.warning(
            "Gagal sync address-list setelah transaksi sukses untuk user %s: %s",
            user.id,
            sync_error,
        )

    if not address_synced:
        for candidate_ip in _resolve_candidate_ips(user, mikrotik_api):
            try:
                if sync_address_list_for_single_user(user, client_ip=candidate_ip):
                    address_synced = True
                    break
            except Exception as sync_error:
                logger.warning(
                    "Gagal sync address-list dengan IP %s untuk user %s: %s",
                    candidate_ip,
                    user.id,
                    sync_error,
                )

    if not address_synced:
        logger.info(
            "Sync address-list tertunda untuk user %s: belum menemukan IP valid.",
            user.id,
        )

    try:
        db.session.add(user)
        db.session.add(transaction)
        logger.info(
            f"Sinkronisasi Mikrotik BERHASIL untuk user '{hotspot_username}'. Perubahan siap di-commit."
        )
        return True, "Paket berhasil diterapkan dan disinkronkan ke Mikrotik."
    except SQLAlchemyError as e:
        logger.error(
            f"Gagal saat menambahkan perubahan user {user.id} ke sesi DB: {e}",
            exc_info=True,
        )
        return False, "Gagal memproses data di sesi database."