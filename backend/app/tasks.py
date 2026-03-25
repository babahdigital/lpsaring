# backend/app/tasks.py
import ipaddress
import logging
import json
import calendar
import secrets
import subprocess
import sys
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from sqlalchemy import text
from sqlalchemy.orm import selectinload

from app.infrastructure.gateways.whatsapp_client import send_whatsapp_with_pdf, send_whatsapp_message
from app.infrastructure.http.transactions.events import log_transaction_event
from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles, cleanup_inactive_users, sync_address_list_for_single_user
from app.services import settings_service
from app.services.access_parity_service import collect_access_parity_report
from app.services.walled_garden_service import sync_walled_garden
from app.extensions import db
from app.infrastructure.db.models import (
    AdminActionLog,
    AdminActionType,
    ApprovalStatus,
    NotificationRecipient,
    NotificationType,
    Package,
    PublicDatabaseUpdateSubmission,
    QuotaMutationLedger,
    RefreshToken,
    Transaction,
    TransactionEventSource,
    TransactionStatus,
    User,
    UserDevice,
    UserQuotaDebt,
    UserRole,
)
from app.infrastructure.gateways.mikrotik_client import (
    activate_or_update_hotspot_user,
    delete_hotspot_user,
    get_firewall_address_list_entries,
    get_hotspot_host_usage_map,
    get_hotspot_ip_binding_user_map,
    get_mikrotik_connection,
    remove_address_list_entry,
    remove_dhcp_lease,
    remove_hotspot_host_entries,
    remove_hotspot_host_entries_best_effort,
    remove_ip_binding,
    upsert_address_list_entry,
    upsert_dhcp_static_lease,
    upsert_ip_binding,
)
from app.services.notification_service import generate_temp_debt_report_token, get_notification_message
from app.services.manual_debt_report_service import (
    build_due_debt_reminder_context,
    build_user_manual_debt_pdf_filename,
    build_user_manual_debt_report_context,
    resolve_public_base_url,
)
from app.services.access_policy_service import resolve_allowed_binding_type_for_user
from app.services.quota_mutation_ledger_service import append_quota_mutation_event, lock_user_quota_row, snapshot_user_quota_state
from app.services.user_management.helpers import _handle_mikrotik_operation
from app.services.user_management.user_deletion import run_user_auth_cleanup
from app.commands.sync_unauthorized_hosts_command import sync_unauthorized_hosts_command
from app.utils.block_reasons import build_manual_debt_eom_reason
from app.utils.formatters import build_ip_binding_comment, format_mb_to_gb, format_to_local_phone, get_app_local_datetime, get_phone_number_variations
from app.utils.metrics_utils import increment_metric
from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package, format_rupiah


def _load_quota_sync_interval_seconds() -> int:
    try:
        return settings_service.get_setting_as_int("QUOTA_SYNC_INTERVAL_SECONDS", 300)
    finally:
        db.session.remove()


def _has_other_active_celery_task(task_name: str, current_task_id: str | None = None) -> bool | None:
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        active_tasks = inspector.active() or {}
    except Exception:
        logger.warning(
            "Celery Task: Gagal inspeksi active task untuk validasi stale lock %s.",
            task_name,
            exc_info=True,
        )
        return None

    for worker_tasks in active_tasks.values():
        for task_info in worker_tasks or []:
            if str(task_info.get("name") or "") != task_name:
                continue
            active_task_id = str(task_info.get("id") or "")
            if current_task_id and active_task_id == current_task_id:
                continue
            return True
    return False


def _acquire_quota_sync_run_lock(redis_client: Any, current_task_id: str | None = None) -> bool:
    lock_value = str(current_task_id or "sync_hotspot_usage_task")
    lock_acquired = bool(
        redis_client.set(
            _QUOTA_SYNC_LOCK_KEY,
            lock_value,
            nx=True,
            ex=_QUOTA_SYNC_LOCK_TTL_SECONDS,
        )
    )
    if lock_acquired:
        return True

    other_task_active = _has_other_active_celery_task(
        "sync_hotspot_usage_task",
        current_task_id=current_task_id,
    )
    if other_task_active is not False:
        return False

    logger.warning(
        "Celery Task: Stale quota sync lock terdeteksi tanpa task aktif lain; mencoba reclaim lock."
    )
    redis_client.delete(_QUOTA_SYNC_LOCK_KEY)
    return bool(
        redis_client.set(
            _QUOTA_SYNC_LOCK_KEY,
            lock_value,
            nx=True,
            ex=_QUOTA_SYNC_LOCK_TTL_SECONDS,
        )
    )


@dataclass(frozen=True)
class CleanupWaitingDhcpArpConfig:
    mikrotik_operations_enabled: bool
    feature_enabled: bool
    keyword: str
    min_last_seen_seconds: int


@dataclass(frozen=True)
class PolicyParityAutoRemediationConfig:
    enabled: bool
    max_users: int
    run_unauthorized_sync: bool


def _load_cleanup_waiting_dhcp_arp_config() -> CleanupWaitingDhcpArpConfig:
    try:
        return CleanupWaitingDhcpArpConfig(
            mikrotik_operations_enabled=(
                settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") == "True"
            ),
            feature_enabled=(
                settings_service.get_setting("AUTO_CLEANUP_WAITING_DHCP_ARP_ENABLED", "False") == "True"
            ),
            keyword=(
                settings_service.get_setting("AUTO_CLEANUP_WAITING_DHCP_ARP_COMMENT_KEYWORD", "lpsaring|static-dhcp")
                or "lpsaring|static-dhcp"
            )
            .strip()
            .lower(),
            min_last_seen_seconds=max(
                0,
                settings_service.get_setting_as_int(
                    "AUTO_CLEANUP_WAITING_DHCP_ARP_MIN_LAST_SEEN_SECONDS",
                    6 * 60 * 60,
                ),
            ),
        )
    finally:
        db.session.remove()


def _load_policy_parity_auto_remediation_config(app: Any) -> PolicyParityAutoRemediationConfig:
    try:
        max_users_raw = int(app.config.get("POLICY_PARITY_AUTO_REMEDIATION_MAX_USERS", 10) or 10)
    except Exception:
        max_users_raw = 10

    return PolicyParityAutoRemediationConfig(
        enabled=bool(app.config.get("ENABLE_POLICY_PARITY_AUTO_REMEDIATION", True)),
        max_users=max(1, max_users_raw),
        run_unauthorized_sync=bool(app.config.get("POLICY_PARITY_AUTO_REMEDIATION_RUN_UNAUTHORIZED_SYNC", True)),
    )

# Import create_app dari app/__init__.py
from app import create_app as _flask_create_app

# Kita akan menggunakan celery_app dari extensions.py sebagai decorator
# Pastikan ini sesuai dengan cara Anda mengimpor celery_app di docker-compose.yml
# `celery -A app.extensions.celery_app worker`
from app.extensions import celery_app

logger = logging.getLogger(__name__)

_TASK_APP_CACHE: dict[str | None, Any] = {}

_MIKROTIK_DURATION_PART = re.compile(r"(\d+)([wdhms])", re.IGNORECASE)
_QUOTA_SYNC_LOCK_KEY = "quota_sync:run_lock"
_QUOTA_SYNC_LAST_RUN_KEY = "quota_sync:last_run_ts"
_QUOTA_SYNC_LOCK_TTL_SECONDS = 3600

_NON_RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS = (
    "gagal konek mikrotik",
    "gagal ambil hotspot host",
    "kegagalan operasi router",
    "routerosapiconnectionerror",
)

_RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS = (
    "timed out",
    "timeout",
    "bad file descriptor",
    "connection reset",
    "broken pipe",
)

_POLICY_PARITY_AUTO_REMEDIATION_MISMATCH_KEYS = {
    "missing_ip_binding",
    "binding_type",
    "address_list",
    "address_list_multi_status",
    "dhcp_lease_missing",
}

_POLICY_PARITY_AUTO_REMEDIATION_NON_PARITY_KEYS = {
    "dhcp_lease_missing",
}


def create_app(config_name: str | None = None) -> Any:
    """Cache Flask app per worker process to avoid rebuilding SQLAlchemy engines every task run."""
    cache_key = str(config_name) if config_name is not None else None
    app = _TASK_APP_CACHE.get(cache_key)
    if app is None:
        app = _flask_create_app(config_name)
        _TASK_APP_CACHE[cache_key] = app
    return app


def _should_skip_public_update_whatsapp_for_phone(phone_number: str) -> str | None:
    """Return skip-reason string jika nomor tidak layak menerima WA update, None jika harus dikirim.

    Skip permanen (whatsapp_notified_at boleh di-set → stop retry):
    - "no_phone"        : nomor kosong
    - "already_updated" : user sudah update data (nama tidak lagi diawali 'Imported ')

    Skip sementara (jangan set whatsapp_notified_at → coba lagi nanti):
    - "inactive_or_unapproved" : user Imported tapi belum aktif/disetujui
    """
    normalized_phone = str(phone_number or "").strip()
    if not normalized_phone:
        return "no_phone"

    try:
        variations = get_phone_number_variations(normalized_phone)
        user = db.session.query(User).filter(User.phone_number.in_(variations)).order_by(User.created_at.desc()).first()

        # Nomor tidak ada di DB → bukan user kita, jangan kirim WA
        if user is None:
            return "already_updated"

        # Hanya kirim ke user yang namanya diawali "Imported " (hasil import, belum update data)
        user_name = str(getattr(user, "full_name", "") or "").strip()
        if not user_name.startswith("Imported "):
            return "already_updated"  # user sudah update nama lewat form, skip permanen

        is_approved = getattr(user, "approval_status", None) == ApprovalStatus.APPROVED
        is_active = bool(getattr(user, "is_active", False))
        if not (is_approved and is_active):
            return "inactive_or_unapproved"  # skip sementara, jangan tandai sebagai terkirim

        return None  # kirim WA
    except Exception:
        # Best effort guard; never block message processing on lookup errors.
        return None


def _collect_policy_parity_auto_remediation_candidates(
    report: dict[str, Any], *, max_users: int
) -> list[dict[str, Any]]:
    candidates_by_user_id: dict[str, dict[str, Any]] = {}
    ordered_user_ids: list[str] = []

    for item in report.get("items", []) or []:
        user_id = str(item.get("user_id") or "").strip()
        if not user_id:
            continue
        if not bool(item.get("auto_fixable")):
            continue

        mismatch_set = {
            str(mismatch or "").strip()
            for mismatch in (item.get("mismatches") or [])
            if str(mismatch or "").strip()
        }
        remediable_mismatches = mismatch_set.intersection(_POLICY_PARITY_AUTO_REMEDIATION_MISMATCH_KEYS)
        if not remediable_mismatches:
            continue
        if not bool(item.get("parity_relevant")) and not remediable_mismatches.issubset(
            _POLICY_PARITY_AUTO_REMEDIATION_NON_PARITY_KEYS
        ):
            continue

        candidate = candidates_by_user_id.get(user_id)
        if candidate is None:
            if len(ordered_user_ids) >= max_users:
                continue
            candidate = {
                "user_id": user_id,
                "phone_number": str(item.get("phone_number") or "").strip(),
                "ips": [],
                "macs": [],
                "mismatches": set(),
            }
            candidates_by_user_id[user_id] = candidate
            ordered_user_ids.append(user_id)

        phone_number = str(item.get("phone_number") or "").strip()
        if phone_number and not candidate["phone_number"]:
            candidate["phone_number"] = phone_number

        ip_address = str(item.get("ip") or "").strip()
        if ip_address and ip_address not in candidate["ips"]:
            candidate["ips"].append(ip_address)

        mac_address = str(item.get("mac") or "").strip().upper()
        if mac_address and mac_address not in candidate["macs"]:
            candidate["macs"].append(mac_address)

        candidate["mismatches"].update(mismatch_set)

    return [
        {
            "user_id": user_id,
            "phone_number": str(candidates_by_user_id[user_id].get("phone_number") or "").strip(),
            "ips": list(candidates_by_user_id[user_id].get("ips") or []),
            "macs": list(candidates_by_user_id[user_id].get("macs") or []),
            "mismatches": sorted(candidates_by_user_id[user_id].get("mismatches") or set()),
        }
        for user_id in ordered_user_ids
    ]


def _normalize_policy_parity_ip(value: Any) -> str | None:
    ip_text = str(value or "").strip()
    if not ip_text or ip_text in {"0.0.0.0", "0.0.0.0/0"}:
        return None
    try:
        ipaddress.ip_address(ip_text)
    except ValueError:
        return None
    return ip_text


def _resolve_policy_parity_auto_remediation_client_ip(
    user: User,
    *,
    candidate_ips: list[str],
    host_usage_map: dict[str, dict[str, Any]],
    ip_binding_map: dict[str, dict[str, Any]],
) -> str | None:
    normalized_candidates = []
    for ip_value in candidate_ips:
        normalized_ip = _normalize_policy_parity_ip(ip_value)
        if normalized_ip and normalized_ip not in normalized_candidates:
            normalized_candidates.append(normalized_ip)

    if not normalized_candidates:
        return None

    trusted_live_ips: set[str] = set()
    for device in user.devices or []:
        if not bool(getattr(device, "is_authorized", False)):
            continue

        mac_address = str(getattr(device, "mac_address", "") or "").strip().upper()
        if not mac_address:
            continue

        host_ip = _normalize_policy_parity_ip((host_usage_map.get(mac_address) or {}).get("address"))
        if host_ip:
            trusted_live_ips.add(host_ip)

        binding_ip = _normalize_policy_parity_ip((ip_binding_map.get(mac_address) or {}).get("address"))
        if binding_ip:
            trusted_live_ips.add(binding_ip)

    for candidate_ip in normalized_candidates:
        if candidate_ip in trusted_live_ips:
            return candidate_ip

    return None


def _run_policy_parity_auto_remediation(app: Any, report: dict[str, Any]) -> dict[str, Any]:
    config = _load_policy_parity_auto_remediation_config(app)
    result: dict[str, Any] = {
        "enabled": config.enabled,
        "max_users": config.max_users,
        "run_unauthorized_sync": config.run_unauthorized_sync,
        "candidate_users": 0,
        "attempted_users": 0,
        "remediated_users": 0,
        "failed_users": 0,
        "skipped_missing_user": 0,
        "failure_samples": [],
        "unauthorized_sync_triggered": False,
        "unauthorized_sync_failed": False,
    }
    if not config.enabled:
        return result

    candidates = _collect_policy_parity_auto_remediation_candidates(report, max_users=config.max_users)
    result["candidate_users"] = len(candidates)
    if not candidates:
        return result

    def _append_failure_sample(text: str) -> None:
        samples = result["failure_samples"]
        if len(samples) < 5:
            samples.append(text)

    try:
        users = (
            db.session.query(User)
            .options(selectinload(User.devices))
            .filter(
                User.id.in_([candidate["user_id"] for candidate in candidates]),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
            )
            .all()
        )
        users_by_id = {str(user.id): user for user in users}

        with get_mikrotik_connection() as api:
            if not api:
                result["reason"] = "mikrotik_unavailable"
                return result

            ok_host_map, host_usage_map, _host_msg = get_hotspot_host_usage_map(api)
            if not ok_host_map:
                host_usage_map = {}

            ok_binding_map, ip_binding_map, _binding_msg = get_hotspot_ip_binding_user_map(api)
            if not ok_binding_map:
                ip_binding_map = {}

            for candidate in candidates:
                result["attempted_users"] += 1

                user = users_by_id.get(candidate["user_id"])
                if user is None:
                    result["skipped_missing_user"] += 1
                    continue

                trusted_client_ip = _resolve_policy_parity_auto_remediation_client_ip(
                    user,
                    candidate_ips=list(candidate.get("ips") or []),
                    host_usage_map=host_usage_map,
                    ip_binding_map=ip_binding_map,
                )

                # Fallback: untuk bypassed ip-binding tanpa address field, ip_binding_map["address"]
                # kosong → trusted_live_ips kosong → resolve_client_ip returns None → sync
                # dipanggil tanpa client_ip → prune dengan keep_ips=[] → klient_aktif dibersihkan.
                # Candidate ips dari report berasal dari live MikroTik scan (via parity service),
                # sehingga aman dipakai langsung untuk address-list sync jika trusted_client_ip None.
                if not trusted_client_ip:
                    for _report_ip in candidate.get("ips") or []:
                        _normalized_report_ip = _normalize_policy_parity_ip(_report_ip)
                        if _normalized_report_ip:
                            trusted_client_ip = _normalized_report_ip
                            break

                try:
                    candidate_mismatches = set(candidate.get("mismatches") or [])
                    needs_binding_fix = bool(candidate_mismatches.intersection({"binding_type", "missing_ip_binding"}))
                    needs_dhcp_fix = "dhcp_lease_missing" in candidate_mismatches

                    # --- Step 1: Fix ip-binding per MAC (binding_type / missing_ip_binding) ---
                    if needs_binding_fix and candidate.get("macs"):
                        expected_binding_type = str(resolve_allowed_binding_type_for_user(user) or "regular").lower()
                        for mac_to_fix in candidate.get("macs") or []:
                            mac_ip = _normalize_policy_parity_ip(
                                (ip_binding_map.get(mac_to_fix) or {}).get("address")
                                or (host_usage_map.get(mac_to_fix) or {}).get("address")
                            )
                            ok_bind, bind_msg = upsert_ip_binding(
                                api_connection=api,
                                mac_address=mac_to_fix,
                                address=mac_ip,
                                server=getattr(user, "mikrotik_server_name", None),
                                binding_type=expected_binding_type,
                                comment=build_ip_binding_comment(
                                    binding_type=expected_binding_type,
                                    phone_number=getattr(user, "phone_number", None),
                                    user_id=str(user.id),
                                    role=getattr(user.role, "value", "USER"),
                                    source="parity-guard",
                                ),
                            )
                            if not ok_bind:
                                logger.warning(
                                    "Policy parity auto-remediation: gagal upsert ip-binding user=%s mac=%s: %s",
                                    candidate["user_id"], mac_to_fix, bind_msg,
                                )

                    # --- Step 2: Sync address-list ---
                    ok = sync_address_list_for_single_user(
                        user,
                        client_ip=trusted_client_ip,
                        api_connection=api,
                    )

                    # --- Step 3: Fix DHCP static lease per MAC (dhcp_lease_missing, best-effort) ---
                    if needs_dhcp_fix and candidate.get("macs"):
                        dhcp_enabled = settings_service.get_setting("MIKROTIK_DHCP_STATIC_LEASE_ENABLED", "False") == "True"
                        dhcp_server_name = (settings_service.get_setting("MIKROTIK_DHCP_LEASE_SERVER_NAME", "") or "").strip() or None
                        if dhcp_enabled and dhcp_server_name:
                            for mac_to_fix in candidate.get("macs") or []:
                                mac_ip = _normalize_policy_parity_ip(
                                    (ip_binding_map.get(mac_to_fix) or {}).get("address")
                                    or (host_usage_map.get(mac_to_fix) or {}).get("address")
                                )
                                if not mac_ip:
                                    continue
                                ok_dhcp, dhcp_msg = upsert_dhcp_static_lease(
                                    api_connection=api,
                                    mac_address=mac_to_fix,
                                    address=mac_ip,
                                    server=dhcp_server_name,
                                    comment=f"lpsaring|static-dhcp|source=parity-guard|uid={user.id}",
                                )
                                if not ok_dhcp:
                                    logger.warning(
                                        "Policy parity auto-remediation: gagal upsert DHCP lease user=%s mac=%s ip=%s: %s",
                                        candidate["user_id"], mac_to_fix, mac_ip, dhcp_msg,
                                    )

                except Exception as exc:
                    result["failed_users"] += 1
                    _append_failure_sample(f"{candidate['user_id']} => {exc}")
                    logger.warning(
                        "Policy parity auto-remediation gagal: user=%s trusted_ip=%s candidate_ips=%s mismatches=%s error=%s",
                        candidate["user_id"],
                        trusted_client_ip,
                        candidate.get("ips"),
                        candidate["mismatches"],
                        exc,
                    )
                    continue

                if ok:
                    result["remediated_users"] += 1
                else:
                    result["failed_users"] += 1
                    _append_failure_sample(f"{candidate['user_id']} => sync_returned_false")

            if config.run_unauthorized_sync and result["remediated_users"] > 0:
                result["unauthorized_sync_triggered"] = True
                try:
                    sync_unauthorized_hosts_command.main(args=["--apply"], standalone_mode=False)
                except SystemExit as exc:
                    exit_code = int(getattr(exc, "code", 0) or 0)
                    if exit_code != 0:
                        result["unauthorized_sync_failed"] = True
                        _append_failure_sample(f"sync_unauthorized_hosts => exit_code_{exit_code}")
                        logger.warning(
                            "Policy parity auto-remediation unauthorized sync keluar dengan exit code %s",
                            exit_code,
                        )
                except Exception as exc:
                    result["unauthorized_sync_failed"] = True
                    _append_failure_sample(f"sync_unauthorized_hosts => {exc}")
                    logger.warning("Policy parity auto-remediation unauthorized sync gagal: %s", exc)
    finally:
        db.session.remove()

    if result["remediated_users"] > 0:
        increment_metric("policy.parity.guard.auto_remediation.remediated_users", result["remediated_users"])
    if result["failed_users"] > 0:
        increment_metric("policy.parity.guard.auto_remediation.failed_users", result["failed_users"])

    return result


def _is_non_retryable_unauthorized_sync_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    if any(marker in message for marker in _RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS):
        return False
    return any(marker in message for marker in _NON_RETRYABLE_UNAUTHORIZED_SYNC_ERROR_MARKERS)


def _coerce_utc_datetime(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _get_user_device_last_activity(device: UserDevice):
    candidates = []
    for field_name in ("last_bytes_updated_at", "last_seen_at", "authorized_at", "first_seen_at"):
        field_value = _coerce_utc_datetime(getattr(device, field_name, None))
        if field_value is not None:
            candidates.append((field_value, field_name))

    if not candidates:
        return None, "none"

    activity_at, activity_source = max(candidates, key=lambda item: item[0])
    return activity_at, activity_source


def _remove_managed_address_lists_for_device(api_connection, ip_address: str | None) -> None:
    if not ip_address:
        return

    keys = [
        ("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked"),
        ("MIKROTIK_ADDRESS_LIST_ACTIVE", "active"),
        ("MIKROTIK_ADDRESS_LIST_FUP", "fup"),
        ("MIKROTIK_ADDRESS_LIST_HABIS", "habis"),
        ("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired"),
        ("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive"),
    ]
    seen_list_names: set[str] = set()

    for setting_key, default_name in keys:
        list_name = str(settings_service.get_setting(setting_key, default_name) or default_name).strip()
        if not list_name or list_name in seen_list_names:
            continue
        seen_list_names.add(list_name)
        ok, msg = remove_address_list_entry(api_connection=api_connection, address=ip_address, list_name=list_name)
        if not ok:
            logger.info(
                "Celery Task: Gagal cleanup address-list stale device ip=%s list=%s msg=%s",
                ip_address,
                list_name,
                msg,
            )


def _cleanup_stale_user_device_router_state(api_connection, device: UserDevice) -> None:
    user = getattr(device, "user", None)
    mac_address = str(getattr(device, "mac_address", "") or "").strip().upper()
    ip_address = str(getattr(device, "ip_address", "") or "").strip()
    server_name = str(
        getattr(user, "mikrotik_server_name", None)
        or settings_service.get_setting("MIKROTIK_DEFAULT_SERVER_USER", "all")
        or "all"
    ).strip() or "all"
    dhcp_server_name = str(settings_service.get_setting("MIKROTIK_DHCP_LEASE_SERVER_NAME", "") or "").strip() or None
    username_08 = format_to_local_phone(getattr(user, "phone_number", None)) if user is not None else None

    if mac_address:
        ok_binding, binding_msg = remove_ip_binding(
            api_connection=api_connection,
            mac_address=mac_address,
            server=server_name,
        )
        if not ok_binding:
            logger.info(
                "Celery Task: Gagal cleanup ip-binding stale device mac=%s server=%s msg=%s",
                mac_address,
                server_name,
                binding_msg,
            )

    _remove_managed_address_lists_for_device(api_connection, ip_address or None)

    if settings_service.get_setting("MIKROTIK_DHCP_STATIC_LEASE_ENABLED", "False") == "True" and mac_address:
        ok_dhcp, dhcp_msg = remove_dhcp_lease(
            api_connection=api_connection,
            mac_address=mac_address,
            server=dhcp_server_name,
        )
        if not ok_dhcp:
            logger.info(
                "Celery Task: Gagal cleanup DHCP stale device mac=%s server=%s msg=%s",
                mac_address,
                dhcp_server_name,
                dhcp_msg,
            )

    if mac_address or ip_address or username_08:
        ok_host, host_msg, removed_hosts = remove_hotspot_host_entries_best_effort(
            api_connection=api_connection,
            mac_address=mac_address or None,
            address=ip_address or None,
            username=username_08 or None,
            allow_username_only_fallback=False,
        )
        if not ok_host:
            logger.info(
                "Celery Task: Gagal cleanup hotspot host stale device mac=%s ip=%s user=%s msg=%s",
                mac_address,
                ip_address,
                username_08,
                host_msg,
            )
        elif int(removed_hosts or 0) > 0:
            logger.info(
                "Celery Task: Cleanup hotspot host stale device mac=%s ip=%s user=%s removed=%s",
                mac_address,
                ip_address,
                username_08,
                int(removed_hosts or 0),
            )


def _parse_ip_networks(cidr_values):
    networks = []
    for cidr in list(cidr_values or []):
        try:
            networks.append(ipaddress.ip_network(str(cidr), strict=False))
        except Exception:
            continue
    return networks


def _ip_in_networks(ip_value: str | None, networks) -> bool:
    ip_text = str(ip_value or "").strip()
    if not ip_text:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except Exception:
        return False
    return any(ip_obj in network for network in networks)


def _collect_local_hotspot_ips_by_mac(api_connection, networks):
    ips_by_mac: dict[str, set[str]] = {}

    def _remember(mac_value, ip_value):
        mac_text = str(mac_value or "").strip().upper()
        ip_text = str(ip_value or "").strip()
        if not mac_text or not _ip_in_networks(ip_text, networks):
            return
        ips_by_mac.setdefault(mac_text, set()).add(ip_text)

    arp_rows = api_connection.get_resource("/ip/arp").get() or []
    for row in arp_rows:
        _remember(row.get("mac-address"), row.get("address"))

    lease_rows = api_connection.get_resource("/ip/dhcp-server/lease").get() or []
    for row in lease_rows:
        _remember(row.get("mac-address"), row.get("address"))

    return ips_by_mac


def _collect_local_hotspot_host_ips_by_mac(host_rows, networks):
    ips_by_mac: dict[str, set[str]] = {}
    for row in host_rows or []:
        mac_text = str(row.get("mac-address") or "").strip().upper()
        address_text = str(row.get("address") or "").strip()
        if not mac_text or not _ip_in_networks(address_text, networks):
            continue
        ips_by_mac.setdefault(mac_text, set()).add(address_text)
    return ips_by_mac


@celery_app.task(
    name="clear_total_if_no_update_submission_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def clear_total_if_no_update_submission_task(self):
    """Dangerous operation: clear all users from DB and MikroTik when update sync mode is enabled and stale."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Update sync auto-clear skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if not bool(app.config.get("UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR", False)):
            logger.warning(
                "Update sync auto-clear skipped: UPDATE_ALLOW_DESTRUCTIVE_AUTO_CLEAR is disabled. "
                "This guard prevents accidental full user wipe."
            )
            return {"success": True, "skipped": True, "reason": "destructive_guard_disabled"}

        try:
            stale_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            stale_days = 3
        if stale_days < 1:
            stale_days = 1

        now_utc = datetime.now(dt_timezone.utc)
        cutoff = now_utc - timedelta(days=stale_days)

        latest_submission = (
            db.session.query(PublicDatabaseUpdateSubmission)
            .order_by(PublicDatabaseUpdateSubmission.created_at.desc())
            .first()
        )

        if latest_submission and latest_submission.created_at and latest_submission.created_at >= cutoff:
            logger.info(
                "Update sync auto-clear skipped: latest submission is still within %s days.",
                stale_days,
            )
            return {"success": True, "skipped": True, "reason": "fresh_submission"}

        users = db.session.query(User).all()
        mikrotik_failed = []

        if app.config.get("ENABLE_MIKROTIK_OPERATIONS", True):
            try:
                with get_mikrotik_connection() as api_connection:
                    if api_connection is not None:
                        for user in users:
                            username = format_to_local_phone(user.phone_number) or str(user.phone_number or "").strip()
                            if not username:
                                continue
                            ok, msg = delete_hotspot_user(api_connection, username)
                            if not ok and "tidak ditemukan" not in str(msg).lower():
                                mikrotik_failed.append({"username": username, "error": str(msg)})
            except Exception as mikrotik_error:
                logger.error("Update sync auto-clear: gagal koneksi/hapus MikroTik: %s", mikrotik_error, exc_info=True)
                mikrotik_failed.append({"error": str(mikrotik_error)})

        if mikrotik_failed:
            logger.warning("Update sync auto-clear dibatalkan karena kegagalan cleanup MikroTik.")
            return {
                "success": False,
                "skipped": True,
                "reason": "mikrotik_cleanup_failed",
                "errors": mikrotik_failed,
            }

        # Clear total user-related data from DB.
        # Use get_bind() first because scoped sessions may have bind=None even on PostgreSQL.
        session_bind = None
        try:
            session_bind = db.session.get_bind()
        except Exception:
            session_bind = getattr(db.session, "bind", None)

        dialect_name = str(getattr(getattr(session_bind, "dialect", None), "name", "") or "").lower()
        if dialect_name.startswith("postgresql"):
            db.session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
        else:
            # Fallback for non-postgres test/dev cases. Use set-based statements to avoid
            # row-by-row ORM delete ordering/autoflush issues on self-referenced FKs.
            db.session.execute(
                text(
                    "UPDATE users "
                    "SET approved_by_id = NULL, rejected_by_id = NULL, blocked_by_id = NULL "
                    "WHERE approved_by_id IS NOT NULL OR rejected_by_id IS NOT NULL OR blocked_by_id IS NOT NULL"
                )
            )
            db.session.query(User).delete(synchronize_session=False)
        db.session.commit()

        logger.warning(
            "Update sync auto-clear executed: no submissions for %s days, total users cleared=%s",
            stale_days,
            len(users),
        )
        return {"success": True, "cleared_users": len(users), "stale_days": stale_days}


@celery_app.task(
    name="send_public_update_submission_whatsapp_batch_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def send_public_update_submission_whatsapp_batch_task(self):
    """Kirim WA bertahap untuk data public update (maks 3 nomor unik per siklus secara default)."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Update sync WA batch skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") != "True":
            logger.info("Update sync WA batch skipped: WhatsApp notifications disabled.")
            return {"success": True, "skipped": True, "reason": "whatsapp_disabled"}

        try:
            batch_size = int(app.config.get("UPDATE_WHATSAPP_BATCH_SIZE", 3))
        except Exception:
            batch_size = 3
        batch_size = max(1, min(batch_size, 20))

        try:
            deadline_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            deadline_days = 3
        deadline_days = max(1, deadline_days)

        message_template = (
            app.config.get("UPDATE_WHATSAPP_IMPORT_MESSAGE_TEMPLATE")
            or (
                "Halo *{full_name}*,\n\n"
                "Kami mendeteksi data Anda di jaringan LPSaring perlu dilengkapi.\n\n"
                "Silakan perbarui data melalui link berikut *dalam {deadline_days} hari*:\n"
                "{update_link}\n\n"
                "\u26a0\ufe0f *Peringatan:* Jika tidak diperbarui, akun Anda akan *dihapus otomatis* dari sistem.\n\n"
                "Terima kasih,\nTim LPSaring"
            )
        )
        base_public_url = str(app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")

        fetch_limit = max(batch_size * 10, 30)
        all_rows = db.session.query(PublicDatabaseUpdateSubmission).all()
        pending_rows = [
            row
            for row in all_rows
            if getattr(row, "whatsapp_notified_at", None) is None and str(getattr(row, "phone_number", "") or "").strip()
        ]
        pending_rows.sort(key=lambda item: getattr(item, "created_at", datetime.min.replace(tzinfo=dt_timezone.utc)))
        pending_rows = pending_rows[:fetch_limit]

        def _normalize_phone_key(phone_number: str) -> str:
            digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
            if not digits:
                return ""
            if digits.startswith("0"):
                return f"62{digits[1:]}"
            if digits.startswith("8"):
                return f"62{digits}"
            return digits

        phone_groups = {}
        for row in pending_rows:
            key = _normalize_phone_key(getattr(row, "phone_number", ""))
            if not key:
                continue
            phone_groups.setdefault(key, []).append(row)
            if len(phone_groups) >= batch_size:
                break

        if not phone_groups:
            logger.info("Update sync WA batch: no pending submissions with valid phone numbers.")
            return {"success": True, "skipped": True, "reason": "no_pending_phone"}

        sent_numbers = 0
        failed_numbers = 0
        now_utc = datetime.now(dt_timezone.utc)

        for _phone_key, grouped_rows in phone_groups.items():
            representative = grouped_rows[0]
            context = {
                "full_name": getattr(representative, "full_name", "Pengguna"),
                "role": getattr(representative, "role", ""),
                "blok": getattr(representative, "blok", ""),
                "kamar": getattr(representative, "kamar", ""),
                "tamping_type": getattr(representative, "tamping_type", "") or "",
                "deadline_days": deadline_days,
            }

            phone_for_link = str(getattr(representative, "phone_number", "") or "").strip()
            encoded_phone = quote_plus(phone_for_link)
            encoded_name = quote_plus(str(context.get("full_name") or ""))
            if base_public_url:
                update_link = f"{base_public_url}/update?phone={encoded_phone}&name={encoded_name}"
            else:
                update_link = f"/update?phone={encoded_phone}&name={encoded_name}"
            context["update_link"] = update_link

            try:
                message = str(message_template).format(**context)
            except Exception:
                message = (
                    f"Halo {context['full_name']}, silakan perbarui data melalui link ini "
                    f"*dalam {deadline_days} hari*: {update_link}\n\n"
                    f"\u26a0\ufe0f Jika tidak diperbarui, akun Anda akan dihapus otomatis dari sistem."
                )

            skip_reason = _should_skip_public_update_whatsapp_for_phone(getattr(representative, "phone_number", ""))
            if skip_reason is not None:
                # Skip permanen (already_updated / no_phone): tandai sebagai selesai agar tidak diproses ulang
                # Skip sementara (inactive_or_unapproved): JANGAN set whatsapp_notified_at, coba lagi nanti
                is_permanent_skip = skip_reason != "inactive_or_unapproved"
                if is_permanent_skip:
                    for row in grouped_rows:
                        row.whatsapp_notified_at = now_utc
                        row.whatsapp_notify_last_error = skip_reason
                else:
                    for row in grouped_rows:
                        row.whatsapp_notify_last_error = skip_reason
                logger.info(
                    "Update sync WA batch: skip phone reason=%s permanent=%s (phone=%s)",
                    skip_reason,
                    is_permanent_skip,
                    getattr(representative, "phone_number", ""),
                )
                continue

            sent_ok = bool(send_whatsapp_message(getattr(representative, "phone_number", ""), message))
            for row in grouped_rows:
                row.whatsapp_notify_attempts = int(getattr(row, "whatsapp_notify_attempts", 0) or 0) + 1
                if sent_ok:
                    row.whatsapp_notified_at = now_utc
                    row.whatsapp_notify_last_error = None
                else:
                    row.whatsapp_notify_last_error = "send_failed"

            if sent_ok:
                sent_numbers += 1
            else:
                failed_numbers += 1

        db.session.commit()

        logger.info(
            "Update sync WA batch processed: sent_numbers=%s failed_numbers=%s batch_size=%s",
            sent_numbers,
            failed_numbers,
            batch_size,
        )
        return {
            "success": True,
            "sent_numbers": sent_numbers,
            "failed_numbers": failed_numbers,
            "batch_size": batch_size,
        }


@celery_app.task(
    name="auto_delete_unresponsive_imported_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def auto_delete_unresponsive_imported_users_task(self):
    """Hapus user Imported yang tidak mengisi form update setelah X hari."""

    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("Auto-delete unresponsive skipped: UPDATE_ENABLE_SYNC is disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        if not bool(app.config.get("UPDATE_AUTO_DELETE_UNRESPONSIVE", False)):
            logger.info("Auto-delete unresponsive skipped: UPDATE_AUTO_DELETE_UNRESPONSIVE is disabled.")
            return {"success": True, "skipped": True, "reason": "auto_delete_disabled"}

        try:
            deadline_days = int(app.config.get("UPDATE_CLEAR_TOTAL_AFTER_DAYS", 3))
        except Exception:
            deadline_days = 3
        deadline_days = max(1, deadline_days)

        try:
            max_per_run = int(app.config.get("UPDATE_AUTO_DELETE_MAX_PER_RUN", 5))
        except Exception:
            max_per_run = 5
        max_per_run = max(1, max_per_run)

        now_utc = datetime.now(dt_timezone.utc)
        cutoff = now_utc - timedelta(days=deadline_days)

        all_overdue = (
            db.session.query(PublicDatabaseUpdateSubmission)
            .filter(
                PublicDatabaseUpdateSubmission.whatsapp_notified_at.isnot(None),
                PublicDatabaseUpdateSubmission.whatsapp_notified_at < cutoff,
                PublicDatabaseUpdateSubmission.approval_status == "PENDING",
            )
            .order_by(PublicDatabaseUpdateSubmission.whatsapp_notified_at.asc())
            .all()
        )

        def _normalize_phone_key(phone_number: str) -> str:
            digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
            if not digits:
                return ""
            if digits.startswith("0"):
                return f"62{digits[1:]}"
            if digits.startswith("8"):
                return f"62{digits}"
            return digits

        phone_groups: dict = {}
        for row in all_overdue:
            key = _normalize_phone_key(getattr(row, "phone_number", ""))
            if not key:
                continue
            phone_groups.setdefault(key, []).append(row)
            if len(phone_groups) >= max_per_run:
                break

        if not phone_groups:
            logger.info("Auto-delete unresponsive: no overdue PENDING submissions.")
            return {"success": True, "skipped": True, "reason": "no_overdue_pending"}

        deleted_count = 0
        skipped_count = 0

        with get_mikrotik_connection() as api:
            for _phone_key, submissions in phone_groups.items():
                representative = submissions[0]
                raw_phone = str(getattr(representative, "phone_number", "") or "").strip()
                if not raw_phone:
                    skipped_count += 1
                    continue

                variations = get_phone_number_variations(raw_phone)
                user = (
                    db.session.query(User)
                    .filter(User.phone_number.in_(variations))
                    .order_by(User.created_at.desc())
                    .first()
                )
                if user is None:
                    logger.info(
                        "Auto-delete unresponsive: user not found for phone=%s, marking submissions.", raw_phone
                    )
                    for sub in submissions:
                        sub.approval_status = "DELETED_AUTO"
                        sub.rejection_reason = (
                            f"Auto-deleted: tidak merespons {deadline_days} hari (user not found)"
                        )
                    skipped_count += 1
                    continue

                if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
                    logger.info("Auto-delete unresponsive: SKIP admin user %s.", user.phone_number)
                    skipped_count += 1
                    continue

                user_name = str(getattr(user, "full_name", "") or "").strip()
                if not user_name.startswith("Imported "):
                    logger.info(
                        "Auto-delete unresponsive: SKIP non-imported user %s.", user.phone_number
                    )
                    skipped_count += 1
                    continue

                if user.quota_expiry_date is not None and user.quota_expiry_date > now_utc:
                    logger.info(
                        "Auto-delete unresponsive: SKIP user %s — kuota aktif hingga %s.",
                        user.phone_number,
                        user.quota_expiry_date,
                    )
                    skipped_count += 1
                    continue

                username_08 = format_to_local_phone(user.phone_number)

                if api and username_08:
                    ok, msg = delete_hotspot_user(api_connection=api, username=username_08)
                    if not ok and "tidak ditemukan" not in str(msg).lower():
                        logger.warning(
                            "Auto-delete unresponsive: failed to delete MikroTik user %s: %s",
                            username_08, msg,
                        )

                # Gunakan run_user_auth_cleanup untuk cleanup menyeluruh:
                # - hapus UserDevice dari DB
                # - _cleanup_router_artifacts: hotspot host, ip-binding, DHCP, ARP,
                #   semua managed address-list (active, blocked, fup, habis, expired,
                #   inactive, unauthorized) — by IP dan by uid-comment scan.
                cleanup_summary = run_user_auth_cleanup(user)
                devices_cleaned = cleanup_summary.get("device_count_before", 0)
                mikrotik_connected = cleanup_summary.get("router", {}).get("mikrotik_connected", False)

                for sub in submissions:
                    sub.approval_status = "DELETED_AUTO"
                    sub.rejection_reason = f"Auto-deleted: tidak merespons {deadline_days} hari"

                # NOTE: Hindari keyword-args pada declarative model agar Pylance tidak memunculkan
                # `reportCallIssue` (model SQLAlchemy tidak selalu terinferensi memiliki __init__(**kwargs)).
                log_entry = AdminActionLog()
                log_entry.admin_id = None
                log_entry.target_user_id = None
                log_entry.action_type = AdminActionType.MANUAL_USER_DELETE
                log_entry.details = json.dumps({
                    "auto_delete": True,
                    "phone_number": raw_phone,
                    "full_name": user_name,
                    "deadline_days": deadline_days,
                    "devices_cleaned": devices_cleaned,
                    "mikrotik_connected": mikrotik_connected,
                }, default=str)
                db.session.add(log_entry)

                db.session.delete(user)
                deleted_count += 1
                logger.warning(
                    "Auto-delete unresponsive: DELETED %s (phone=%s, deadline=%d hari)",
                    user_name, raw_phone, deadline_days,
                )

        db.session.commit()

        logger.info(
            "Auto-delete unresponsive imported users: deleted=%d skipped=%d deadline_days=%d",
            deleted_count, skipped_count, deadline_days,
        )
        return {
            "success": True,
            "deleted": deleted_count,
            "skipped": skipped_count,
            "deadline_days": deadline_days,
        }


@celery_app.task(
    name="populate_update_submissions_from_imported_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def populate_update_submissions_from_imported_users_task(self):
    """Scan user Imported di tabel users → buat PublicDatabaseUpdateSubmission jika belum ada.

    Task ini memastikan setiap user yang diimport (nama diawali 'Imported ')
    memiliki minimal satu baris di public_database_update_submissions sehingga
    task send_public_update_submission_whatsapp_batch_task bisa mengirim WA notifikasi.
    Satu submission per nomor HP — jika sudah ada, skip.
    """
    app = create_app()
    with app.app_context():
        if not bool(app.config.get("UPDATE_ENABLE_SYNC", False)):
            logger.info("populate_imported_submissions skipped: UPDATE_ENABLE_SYNC disabled.")
            return {"success": True, "skipped": True, "reason": "update_sync_disabled"}

        imported_users = (
            db.session.query(User)
            .filter(User.full_name.like("Imported %"))
            .order_by(User.created_at.asc())
            .all()
        )

        created = 0
        already_exists = 0

        for user in imported_users:
            phone = str(getattr(user, "phone_number", "") or "").strip()
            if not phone:
                continue

            # Periksa variasi nomor agar tidak duplikat meskipun format beda
            variations = get_phone_number_variations(phone)
            existing = (
                db.session.query(PublicDatabaseUpdateSubmission)
                .filter(PublicDatabaseUpdateSubmission.phone_number.in_(variations))
                .first()
            )
            if existing:
                already_exists += 1
                continue

            # Buat submission stub — data aktual diisi oleh user via form
            submission = PublicDatabaseUpdateSubmission()
            submission.full_name = str(getattr(user, "full_name", "") or "").strip()
            submission.role = "USER"
            submission.phone_number = phone
            submission.source_ip = "system:populate_task"
            db.session.add(submission)
            created += 1

        db.session.commit()

        logger.info(
            "populate_imported_submissions: created=%d already_exists=%d total_imported_users=%d",
            created, already_exists, len(imported_users),
        )
        return {
            "success": True,
            "created": created,
            "already_exists": already_exists,
            "total_imported_users": len(imported_users),
        }

def _parse_mikrotik_duration_seconds(value: str) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return 0

    multipliers = {
        "w": 7 * 24 * 60 * 60,
        "d": 24 * 60 * 60,
        "h": 60 * 60,
        "m": 60,
        "s": 1,
    }

    total = 0
    for amount_text, unit in _MIKROTIK_DURATION_PART.findall(text):
        try:
            total += int(amount_text) * multipliers[unit.lower()]
        except Exception:
            continue

    return max(0, total)


@celery_app.task(
    name="send_manual_debt_reminders_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def send_manual_debt_reminders_task(self):
    """Kirim pengingat tunggakan manual 3 tahap: 3 hari, 1 hari, dan 3 jam sebelum due_date.

    Setiap tahap hanya dikirim sekali per debt (dedup via Redis).
    Task berjalan setiap 30 menit via Celery beat.
    """
    app = create_app()
    with app.app_context():
        enable_wa = settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
        if not enable_wa:
            return {"skipped": "whatsapp_disabled"}

        now_local = get_app_local_datetime()
        app_tz = now_local.tzinfo or dt_timezone.utc
        redis_client = getattr(app, "redis_client_otp", None)

        try:
            from sqlalchemy.orm import joinedload as _joinedload

            debts = (
                db.session.query(UserQuotaDebt)
                .options(_joinedload(UserQuotaDebt.user))
                .filter(
                    UserQuotaDebt.is_paid == False,  # noqa: E712
                    UserQuotaDebt.due_date.isnot(None),
                )
                .all()
            )
        except Exception:
            logger.exception("send_manual_debt_reminders: gagal query debts")
            return {"error": "query_failed"}

        summary = {"checked": 0, "sent": 0, "queued_pdf": 0, "skipped_dedup": 0, "skipped_past": 0, "failed": 0}
        report_context_cache: dict[str, dict[str, Any]] = {}
        pdf_url_cache: dict[str, str] = {}
        public_base_url = resolve_public_base_url().strip()

        # (stage_key, min_hours_inclusive, max_hours_exclusive, template_key)
        _STAGES = [
            ("3h", 0.0, 6.0, "user_manual_debt_reminder_3hours"),
            ("1d", 18.0, 30.0, "user_manual_debt_reminder_1day"),
            ("3d", 60.0, 84.0, "user_manual_debt_reminder_3days"),
        ]

        for debt in debts:
            user = debt.user
            if not user:
                continue
            if not (getattr(user, "is_approved", False) and getattr(user, "is_active", False)):
                continue
            summary["checked"] += 1

            due_date = debt.due_date
            if due_date is None:
                continue  # sudah difilter di query, guard untuk type checker
            # Jatuh tempo = akhir hari (23:59:59) waktu lokal
            due_dt = datetime(due_date.year, due_date.month, due_date.day, 23, 59, 59, tzinfo=app_tz)
            diff = due_dt - now_local
            diff_hours = diff.total_seconds() / 3600.0

            if diff_hours < 0:
                summary["skipped_past"] += 1
                continue

            for stage_key, min_h, max_h, template_key in _STAGES:
                if not (min_h <= diff_hours < max_h):
                    continue

                redis_key = f"debt_reminder:{debt.id}:{stage_key}"
                if redis_client:
                    try:
                        if redis_client.exists(redis_key):
                            summary["skipped_dedup"] += 1
                            continue
                    except Exception:
                        pass  # Redis error: lanjut kirim (better over-send than miss)

                try:
                    user_key = str(user.id)
                    report_context = report_context_cache.get(user_key)
                    if report_context is None:
                        report_context = build_user_manual_debt_report_context(user)
                        report_context_cache[user_key] = report_context

                    pdf_url = pdf_url_cache.get(user_key, "")
                    if not pdf_url and public_base_url:
                        temp_token = generate_temp_debt_report_token(str(user.id))
                        pdf_url = f"{public_base_url.rstrip('/')}/api/admin/users/debts/temp/{temp_token}.pdf"
                        pdf_url_cache[user_key] = pdf_url

                    reminder_context = build_due_debt_reminder_context(user, report_context, debt, pdf_url or "-")
                    msg = get_notification_message(
                        template_key,
                        reminder_context,
                    )

                    if str(msg).startswith("Peringatan:"):
                        summary["failed"] += 1
                        logger.error(
                            "send_manual_debt_reminders: render template gagal debt=%s stage=%s msg=%s",
                            debt.id,
                            stage_key,
                            msg,
                        )
                        continue

                    phone = getattr(user, "phone_number", "")
                    sent = False
                    if pdf_url:
                        send_whatsapp_invoice_task.delay(
                            str(phone),
                            msg,
                            pdf_url,
                            build_user_manual_debt_pdf_filename(user),
                            "",
                            None,
                            "debt_report",
                        )
                        summary["queued_pdf"] += 1
                        sent = True
                    else:
                        sent = bool(send_whatsapp_message(phone, msg))

                    if sent:
                        summary["sent"] += 1
                        if redis_client:
                            try:
                                ttl = max(3600, int(diff.total_seconds()) + 86400)
                                redis_client.setex(redis_key, ttl, "1")
                            except Exception:
                                pass
                    else:
                        summary["failed"] += 1
                        logger.warning(
                            "send_manual_debt_reminders: gagal kirim WA %s ke user=%s debt=%s",
                            stage_key,
                            getattr(user, "id", "?"),
                            debt.id,
                        )
                except Exception:
                    summary["failed"] += 1
                    logger.exception(
                        "send_manual_debt_reminders: exception saat kirim %s untuk debt %s",
                        stage_key,
                        debt.id,
                    )

        logger.info(
            "send_manual_debt_reminders summary: checked=%s sent=%s queued_pdf=%s skipped_dedup=%s skipped_past=%s failed=%s",
            summary["checked"],
            summary["sent"],
            summary["queued_pdf"],
            summary["skipped_dedup"],
            summary["skipped_past"],
            summary["failed"],
        )
        return summary


@celery_app.task(
    name="enforce_end_of_month_debt_block_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def enforce_end_of_month_debt_block_task(self):
    """At end-of-month, warn users with unpaid quota debt via WhatsApp, then block them.

    - WhatsApp warning must be attempted first.
    - Admin notifications are sent to subscribed recipients (NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED).
    """
    app = create_app()
    with app.app_context():
        now_local = get_app_local_datetime()
        last_day = calendar.monthrange(now_local.year, now_local.month)[1]

        # Default: run enforcement only on the last day, at/after 23:00 local time.
        try:
            min_hour = int(app.config.get("DEBT_EOM_BLOCK_MIN_HOUR", 23))
        except Exception:
            min_hour = 23

        if now_local.day != last_day or now_local.hour < min_hour:
            return

        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("EOM debt block: Mikrotik ops disabled; will still update DB + WhatsApp.")

        ref_packages = (
            db.session.query(Package)
            .filter(Package.is_active.is_(True))
            .filter(Package.data_quota_gb.isnot(None))
            .filter(Package.data_quota_gb > 0)
            .filter(Package.price.isnot(None))
            .filter(Package.price > 0)
            .order_by(Package.data_quota_gb.asc(), Package.price.asc())
            .all()
        )

        def _pick_ref_pkg_for_debt_mb(value_mb: float) -> Package | None:
            try:
                mb = float(value_mb or 0)
            except Exception:
                mb = 0.0
            if mb <= 0 or not ref_packages:
                return None
            debt_gb = mb / 1024.0
            for pkg in ref_packages:
                try:
                    if float(pkg.data_quota_gb or 0) >= debt_gb:
                        return pkg
                except Exception:
                    continue
            return ref_packages[-1]

        users = (
            db.session.query(User)
            .filter(User.is_active.is_(True))
            .filter(User.approval_status == ApprovalStatus.APPROVED)
            .filter(User.role == UserRole.USER)
            .filter(User.is_unlimited_user.is_(False))
            .options(selectinload(User.devices))
            .all()
        )

        enable_wa = settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
        blocked_profile = settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"
        list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
        other_status_lists = [
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis",
        ]
        blocked_binding_type = settings_service.get_ip_binding_type_setting("IP_BINDING_TYPE_BLOCKED", "blocked")

        recipients_query = (
            db.select(User)
            .join(NotificationRecipient, User.id == NotificationRecipient.admin_user_id)
            .where(
                NotificationRecipient.notification_type == NotificationType.QUOTA_DEBT_LIMIT_EXCEEDED,
                User.is_active.is_(True),
            )
        )
        subscribed_admins = db.session.scalars(recipients_query).all()

        summary = {
            "eligible": 0,
            "warn_failed": 0,
            "blocked_success": 0,
            "block_failed": 0,
            "admin_notify_failed": 0,
        }

        for user in users:
            manual_debt_mb = int(getattr(user, "manual_debt_mb", 0) or 0)
            if manual_debt_mb <= 0:
                continue

            try:
                debt_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
            except Exception:
                debt_mb = 0.0

            if debt_mb <= 0:
                continue

            if bool(getattr(user, "is_blocked", False)):
                continue

            summary["eligible"] += 1

            ref_pkg = _pick_ref_pkg_for_debt_mb(debt_mb)
            base_pkg_name = str(getattr(ref_pkg, "name", "") or "") or "-"
            estimate = estimate_debt_rp_from_cheapest_package(
                debt_mb=debt_mb,
                cheapest_package_price_rp=int(getattr(ref_pkg, "price", 0) or 0) if ref_pkg else 0,
                cheapest_package_quota_gb=float(getattr(ref_pkg, "data_quota_gb", 0) or 0) if ref_pkg else 0,
                cheapest_package_name=base_pkg_name,
            )
            estimate_rp = estimate.estimated_rp_rounded
            estimate_rp_text = format_rupiah(int(estimate_rp)) if isinstance(estimate_rp, int) else "-"

            debt_mb_text = str(int(round(debt_mb)))
            debt_gb_text = format_mb_to_gb(debt_mb)

            warned_ok = True
            if enable_wa:
                try:
                    user_msg = get_notification_message(
                        "user_quota_debt_end_of_month_warning",
                        {
                            "full_name": user.full_name,
                            "phone_number": user.phone_number,
                            "debt_gb": debt_gb_text,
                            "estimated_rp": estimate_rp_text,
                            "base_package_name": base_pkg_name,
                        },
                    )
                    warned_ok = bool(send_whatsapp_message(user.phone_number, user_msg))
                except Exception:
                    logger.exception("EOM debt block: gagal kirim WA warning ke user %s", getattr(user, "id", "?"))
                    warned_ok = False

            # Requirement: send WA first, then block.
            if enable_wa and not warned_ok:
                summary["warn_failed"] += 1
                continue

            try:
                lock_user_quota_row(user)
                before_state = snapshot_user_quota_state(user)

                if not user.mikrotik_password:
                    user.mikrotik_password = "".join(secrets.choice("0123456789") for _ in range(6))

                username_08 = format_to_local_phone(user.phone_number) or user.phone_number or ""
                comment = f"blocked|quota-debt-eom|user={username_08}"

                _handle_mikrotik_operation(
                    activate_or_update_hotspot_user,
                    user_mikrotik_username=username_08,
                    hotspot_password=user.mikrotik_password,
                    mikrotik_profile_name=blocked_profile,
                    limit_bytes_total=1,
                    session_timeout="1s",
                    comment=comment,
                    server=user.mikrotik_server_name,
                    force_update_profile=True,
                )

                user.is_blocked = True
                user.blocked_reason = build_manual_debt_eom_reason(
                    debt_mb_text=debt_mb_text,
                    manual_debt_mb=manual_debt_mb,
                    estimated_rp=int(estimate_rp) if isinstance(estimate_rp, int) else None,
                    base_pkg_name=base_pkg_name,
                )
                user.blocked_at = datetime.now(dt_timezone.utc)
                user.blocked_by_id = None

                # Rule: manual debt EOM wajib hard-block di ip-binding + address-list blocked.
                with get_mikrotik_connection() as api:
                    if api:
                        ok_host, host_map, _host_msg = get_hotspot_host_usage_map(api)
                        host_map = host_map if ok_host else {}

                        for device in user.devices or []:
                            mac = str(getattr(device, "mac_address", "") or "").upper().strip()
                            if not mac:
                                continue
                            upsert_ip_binding(
                                api_connection=api,
                                mac_address=mac,
                                binding_type=blocked_binding_type,
                                comment=f"blocked|manual-debt-eom|user={username_08}|uid={user.id}",
                            )

                            ip_addr = str(getattr(device, "ip_address", "") or "").strip()
                            if not ip_addr:
                                ip_addr = str(host_map.get(mac, {}).get("address") or "").strip()
                            if not ip_addr:
                                continue

                            upsert_address_list_entry(
                                api_connection=api,
                                address=ip_addr,
                                list_name=list_blocked,
                                comment=f"lpsaring|status=blocked|reason=manual-debt-eom|user={username_08}|uid={user.id}",
                            )
                            for list_name in other_status_lists:
                                if list_name and list_name != list_blocked:
                                    remove_address_list_entry(
                                        api_connection=api,
                                        address=ip_addr,
                                        list_name=list_name,
                                    )

                db.session.add(user)
                append_quota_mutation_event(
                    user=user,
                    source="policy.block_transition:manual_debt_eom",
                    before_state=before_state,
                    after_state=snapshot_user_quota_state(user),
                    event_details={
                        "action": "block",
                        "reason": str(getattr(user, "blocked_reason", "") or "") or None,
                        "manual_debt_mb": int(manual_debt_mb),
                        "debt_mb": float(debt_mb),
                    },
                )
                db.session.commit()
                summary["blocked_success"] += 1

                if enable_wa and subscribed_admins:
                    admin_msg = get_notification_message(
                        "admin_quota_debt_end_of_month_blocked",
                        {
                            "full_name": user.full_name,
                            "phone_number": user.phone_number,
                            "debt_gb": debt_gb_text,
                            "estimated_rp": estimate_rp_text,
                            "base_package_name": base_pkg_name,
                        },
                    )
                    for admin in subscribed_admins:
                        try:
                            sent = bool(send_whatsapp_message(admin.phone_number, admin_msg))
                            if not sent:
                                summary["admin_notify_failed"] += 1
                        except Exception:
                            summary["admin_notify_failed"] += 1
                            logger.exception(
                                "EOM debt block: gagal kirim WA admin %s utk user %s",
                                getattr(admin, "id", "?"),
                                getattr(user, "id", "?"),
                            )
            except Exception:
                db.session.rollback()
                summary["block_failed"] += 1
                logger.exception("EOM debt block: gagal proses block untuk user %s", getattr(user, "id", "?"))

        if summary["eligible"] > 0:
            increment_metric("eom.debt_block.eligible", summary["eligible"])
        if summary["warn_failed"] > 0:
            increment_metric("eom.debt_block.warn_failed", summary["warn_failed"])
        if summary["blocked_success"] > 0:
            increment_metric("eom.debt_block.success", summary["blocked_success"])
        if summary["block_failed"] > 0:
            increment_metric("eom.debt_block.failed", summary["block_failed"])
        if summary["admin_notify_failed"] > 0:
            increment_metric("eom.debt_block.admin_notify_failed", summary["admin_notify_failed"])

        logger.info(
            "EOM debt block summary: eligible=%s warn_failed=%s blocked_success=%s block_failed=%s admin_notify_failed=%s",
            summary["eligible"],
            summary["warn_failed"],
            summary["blocked_success"],
            summary["block_failed"],
            summary["admin_notify_failed"],
        )


def _record_task_failure(app, task_name: str, payload: dict, error_message: str) -> None:
    redis_client = getattr(app, "redis_client_otp", None)
    if redis_client is None:
        return
    try:
        dlq_key = app.config.get("TASK_DLQ_REDIS_KEY", "celery:dlq")
        item = {
            "task": task_name,
            "payload": payload,
            "error": error_message,
            "created_at": datetime.now(dt_timezone.utc).isoformat(),
        }
        redis_client.rpush(dlq_key, json.dumps(item))
    except Exception:
        return


@celery_app.task(
    name="audit_mikrotik_reconciliation_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def audit_mikrotik_reconciliation_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip audit MikroTik (MikroTik operations disabled).")
            return

        if settings_service.get_setting("ENABLE_MIKROTIK_AUDIT_RECONCILIATION", "True") != "True":
            logger.info("Celery Task: Skip audit MikroTik (reconciliation disabled by setting).")
            return

        backend_root = Path(__file__).resolve().parents[1]
        script_path = backend_root / "scripts" / "audit_mikrotik_total.py"
        if not script_path.exists():
            logger.warning("Celery Task: Script audit tidak ditemukan: %s", script_path)
            return

        cmd = [sys.executable, str(script_path), "--limit", "30"]
        if settings_service.get_setting("MIKROTIK_AUDIT_AUTO_CLEANUP_STALE_BLOCKED", "False") == "True":
            cmd.extend(["--cleanup-stale-blocked", "--apply"])
        if settings_service.get_setting("MIKROTIK_AUDIT_AUTO_CLEANUP_ORPHANED_LISTS", "False") == "True":
            cmd.extend(["--cleanup-orphaned-lists", "--apply"])

        logger.info("Celery Task: Menjalankan audit MikroTik reconciliation harian.")
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(backend_root),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()

            if completed.returncode != 0:
                raise RuntimeError(
                    f"audit_mikrotik_total exit={completed.returncode}; stderr={stderr or '-'}"
                )

            if stdout:
                logger.info("Celery Task: Audit MikroTik selesai. Summary:\n%s", stdout[-8000:])
            else:
                logger.info("Celery Task: Audit MikroTik selesai tanpa output.")
        except Exception as e:
            logger.error("Celery Task: Audit MikroTik gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "audit_mikrotik_reconciliation_task", {}, str(e))
            raise


@celery_app.task(
    name="policy_parity_guard_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,  # 5 minutes soft limit
    time_limit=360,  # 6 minutes hard limit
)
def policy_parity_guard_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip policy parity guard (MikroTik operations disabled).")
            return

        logger.info("Celery Task: Menjalankan policy parity guard.")
        try:
            report = collect_access_parity_report(max_items=300)
            if not report.get("ok", False):
                reason = str(report.get("reason") or "unknown")
                logger.warning("Celery Task: Policy parity guard unavailable. reason=%s", reason)
                return

            summary = report.get("summary", {}) or {}
            mismatches = int(summary.get("mismatches", 0) or 0)
            mismatch_types = summary.get("mismatch_types", {}) or {}

            remediation_summary = _run_policy_parity_auto_remediation(app, report)
            if remediation_summary.get("candidate_users", 0) > 0:
                logger.info(
                    "Policy parity auto-remediation summary: %s",
                    json.dumps(remediation_summary, ensure_ascii=False),
                )

            if remediation_summary.get("remediated_users", 0) > 0:
                refreshed_report = collect_access_parity_report(max_items=300)
                if refreshed_report.get("ok", False):
                    report = refreshed_report
                    summary = report.get("summary", {}) or {}
                    mismatches = int(summary.get("mismatches", 0) or 0)
                    mismatch_types = summary.get("mismatch_types", {}) or {}

            if mismatches > 0:
                increment_metric("policy.parity.guard.mismatches", mismatches)
                increment_metric("policy.parity.guard.binding_type", int(mismatch_types.get("binding_type", 0) or 0))
                increment_metric("policy.parity.guard.address_list", int(mismatch_types.get("address_list", 0) or 0))
                increment_metric(
                    "policy.parity.guard.address_list_multi_status",
                    int(mismatch_types.get("address_list_multi_status", 0) or 0),
                )

            redis_client = getattr(app, "redis_client_otp", None)
            if redis_client is not None:
                try:
                    redis_client.set(
                        "policy_parity:last_report",
                        json.dumps(
                            {
                                "generated_at": datetime.now(dt_timezone.utc).isoformat(),
                                "summary": summary,
                                "items": report.get("items", [])[:100],
                                "auto_remediation": remediation_summary,
                            }
                        ),
                        ex=24 * 3600,
                    )
                except Exception:
                    pass

            if mismatches > 0:
                top_items = report.get("items", [])[:5]
                logger.warning(
                    "Policy parity guard detected mismatches=%s detail=%s",
                    mismatches,
                    json.dumps(top_items, ensure_ascii=False),
                )
            else:
                logger.info("Policy parity guard: no mismatch detected.")
        except Exception as e:
            logger.error("Celery Task: Policy parity guard gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "policy_parity_guard_task", {}, str(e))
            raise


@celery_app.task(
    name="send_whatsapp_invoice_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def send_whatsapp_invoice_task(
    self,
    recipient_number: str,
    caption: str,
    pdf_url: str,
    filename: str,
    request_id: str = "",
    transaction_id: str | None = None,
    notification_kind: str = "invoice",
):
    """
    Celery task untuk mengirim pesan WhatsApp dengan lampiran PDF.

    Args:
        recipient_number (str): Nomor HP tujuan.
        caption (str): Teks/caption untuk pesan WhatsApp.
        pdf_url (str): URL publik ke file PDF invoice.
        filename (str): Nama file PDF.
    """
    # Penting: Buat instance aplikasi Flask di dalam konteks task
    # Ini memastikan current_app tersedia untuk semua fungsi yang dipanggil dalam task
    # yang membutuhkan konteks aplikasi (misalnya, mengakses app.config)
    # environ.get sekarang akan berfungsi karena 'environ' telah diimpor secara langsung.
    app = create_app()

    event_prefix = "WHATSAPP_INVOICE" if notification_kind == "invoice" else "WHATSAPP_DEBT_REPORT"

    def _log_notification_event(event_type: str, payload: dict[str, Any]) -> None:
        if not transaction_id:
            return
        try:
            tx_uuid = uuid.UUID(str(transaction_id))
        except (TypeError, ValueError):
            logger.warning(
                "Celery Task: transaction_id tidak valid untuk log event notif %s: %s",
                notification_kind,
                transaction_id,
            )
            return

        try:
            transaction = db.session.get(Transaction, tx_uuid)
            if transaction is None:
                logger.warning(
                    "Celery Task: transaksi %s tidak ditemukan saat mencatat event notif %s.",
                    transaction_id,
                    notification_kind,
                )
                return
            log_transaction_event(
                session=db.session,
                transaction=transaction,
                source=TransactionEventSource.APP,
                event_type=event_type,
                status=transaction.status,
                payload=payload,
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.warning(
                "Celery Task: gagal mencatat event notif %s untuk transaksi %s.",
                notification_kind,
                transaction_id,
                exc_info=True,
            )

    with app.app_context():
        logger.info(
            f"Celery Task: Memulai pengiriman WhatsApp dengan PDF ke {recipient_number} untuk URL: {pdf_url}. Request ID: {request_id}"
        )
        _log_notification_event(
            f"{event_prefix}_SEND_ATTEMPT",
            {
                "recipient_number": recipient_number,
                "pdf_url": pdf_url,
                "filename": filename,
                "request_id": request_id,
                "notification_kind": notification_kind,
            },
        )
        try:
            # send_whatsapp_with_pdf sekarang akan memiliki akses ke current_app
            success = send_whatsapp_with_pdf(recipient_number, caption, pdf_url, filename)
            if not success:
                logger.error(
                    f"Celery Task: Gagal mengirim WhatsApp invoice ke {recipient_number} (Fonnte reported failure)."
                )
                _log_notification_event(
                    f"{event_prefix}_PDF_FAILED",
                    {
                        "recipient_number": recipient_number,
                        "pdf_url": pdf_url,
                        "filename": filename,
                        "request_id": request_id,
                        "notification_kind": notification_kind,
                    },
                )
                # Fallback: kirim pesan teks tanpa PDF
                text_success = send_whatsapp_message(recipient_number, caption)
                if text_success:
                    logger.info(f"Celery Task: Pesan teks berhasil dikirim ke {recipient_number} setelah gagal PDF.")
                    _log_notification_event(
                        f"{event_prefix}_TEXT_FALLBACK_SUCCESS",
                        {
                            "recipient_number": recipient_number,
                            "request_id": request_id,
                            "notification_kind": notification_kind,
                        },
                    )
                else:
                    logger.error(f"Celery Task: Pesan teks juga gagal dikirim ke {recipient_number}.")
                    _log_notification_event(
                        f"{event_prefix}_TEXT_FALLBACK_FAILED",
                        {
                            "recipient_number": recipient_number,
                            "request_id": request_id,
                            "notification_kind": notification_kind,
                        },
                    )
                    raise RuntimeError("Fonnte gagal mengirim pesan PDF dan teks.")
            else:
                logger.info(f"Celery Task: Berhasil mengirim WhatsApp invoice ke {recipient_number}.")
                _log_notification_event(
                    f"{event_prefix}_SEND_SUCCESS",
                    {
                        "recipient_number": recipient_number,
                        "pdf_url": pdf_url,
                        "filename": filename,
                        "request_id": request_id,
                        "notification_kind": notification_kind,
                    },
                )
        except Exception as e:
            logger.error(
                f"Celery Task: Exception saat mengirim WhatsApp invoice ke {recipient_number}: {e}", exc_info=True
            )
            _log_notification_event(
                f"{event_prefix}_SEND_EXCEPTION",
                {
                    "recipient_number": recipient_number,
                    "pdf_url": pdf_url,
                    "filename": filename,
                    "request_id": request_id,
                    "notification_kind": notification_kind,
                    "error": str(e),
                },
            )
            if self.request.retries >= 3:
                _record_task_failure(
                    app,
                    "send_whatsapp_invoice_task",
                    {
                        "recipient_number": recipient_number,
                        "caption": caption,
                        "pdf_url": pdf_url,
                        "filename": filename,
                        "request_id": request_id,
                    },
                    str(e),
                )
            raise


@celery_app.task(
    name="sync_hotspot_usage_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=300,  # 5 minutes soft limit — task receives SoftTimeLimitExceeded
    time_limit=360,  # 6 minutes hard limit — kill task if still running
)
def sync_hotspot_usage_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi kuota dan profil hotspot.")
        sync_interval = _load_quota_sync_interval_seconds()
        redis_client = getattr(app, "redis_client_otp", None)
        current_task_id = str(getattr(self.request, "id", "") or "")

        # Throttle check: skip jika belum melewati interval sejak run terakhir
        if redis_client is not None:
            now_ts = int(datetime.now(dt_timezone.utc).timestamp())
            last_ts_str = redis_client.get(_QUOTA_SYNC_LAST_RUN_KEY)
            if last_ts_str:
                last_ts = int(last_ts_str)
                if now_ts - last_ts < max(sync_interval, 30):
                    logger.info("Celery Task: Skip sinkronisasi (menunggu interval dinamis).")
                    return

        # Mutex lock: cegah eksekusi concurrent dari beberapa worker (root cause deadlock DB)
        # Redis lock bisa tertinggal setelah worker crash/recreate; jika itu terjadi,
        # task baru boleh reclaim lock hanya saat inspector Celery memastikan tidak
        # ada sync_hotspot_usage_task aktif lain selain task saat ini.
        lock_acquired = False
        try:
            if redis_client is not None:
                lock_acquired = _acquire_quota_sync_run_lock(redis_client, current_task_id=current_task_id)
                if not lock_acquired:
                    logger.info("Celery Task: Skip sinkronisasi (worker lain sedang berjalan).")
                    return

            result = sync_hotspot_usage_and_profiles()
            logger.info(f"Celery Task: Sinkronisasi selesai. Result: {result}")
            if redis_client is not None:
                redis_client.set(_QUOTA_SYNC_LAST_RUN_KEY, int(datetime.now(dt_timezone.utc).timestamp()))
        except Exception as e:
            logger.error(f"Celery Task: Sinkronisasi gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_hotspot_usage_task", {}, str(e))
            raise
        finally:
            if redis_client is not None and lock_acquired:
                redis_client.delete(_QUOTA_SYNC_LOCK_KEY)


@celery_app.task(
    name="sync_unauthorized_hosts_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
    soft_time_limit=240,  # 4 minutes soft limit
    time_limit=300,  # 5 minutes hard limit
)
def sync_unauthorized_hosts_task(self):
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Celery Task: Skip sync unauthorized hosts (MikroTik operations disabled).")
            return

        redis_client = getattr(app, "redis_client_otp", None)
        lock_key = "sync_unauthorized_hosts:lock"
        lock_acquired = False
        lock_ttl_seconds = max(60, settings_service.get_setting_as_int("UNAUTHORIZED_SYNC_LOCK_TTL_SECONDS", 180))

        if redis_client is not None:
            try:
                lock_acquired = bool(
                    redis_client.set(
                        lock_key,
                        int(datetime.now(dt_timezone.utc).timestamp()),
                        nx=True,
                        ex=lock_ttl_seconds,
                    )
                )
            except Exception:
                lock_acquired = False

            if not lock_acquired:
                logger.info("Celery Task: Skip sync unauthorized hosts (lock aktif, run sebelumnya belum selesai).")
                return

        logger.info("Celery Task: Memulai sinkronisasi unauthorized hosts.")
        try:
            sync_unauthorized_hosts_command.main(args=["--apply"], standalone_mode=False)
            logger.info("Celery Task: Sinkronisasi unauthorized hosts selesai.")
        except SystemExit as e:
            if int(getattr(e, "code", 0) or 0) != 0:
                raise RuntimeError(f"sync-unauthorized-hosts exit code {e.code}")
        except Exception as e:
            logger.error(f"Celery Task: Sinkronisasi unauthorized hosts gagal: {e}", exc_info=True)
            if _is_non_retryable_unauthorized_sync_error(e):
                _record_task_failure(app, "sync_unauthorized_hosts_task", {}, str(e))
                logger.warning(
                    "Celery Task: Sinkronisasi unauthorized hosts tidak diretry karena error non-retryable."
                )
                return {
                    "success": False,
                    "reason": "non_retryable_mikrotik_sync_error",
                    "error": str(e),
                }
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_unauthorized_hosts_task", {}, str(e))
            raise
        finally:
            if redis_client is not None and lock_acquired:
                try:
                    redis_client.delete(lock_key)
                except Exception:
                    pass


@celery_app.task(
    name="cleanup_stale_user_devices_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_stale_user_devices_task(self):
    app = create_app()
    with app.app_context():
        if str(app.config.get("ENABLE_MIKROTIK_OPERATIONS", "True")).strip().lower() != "true":
            logger.info("Celery Task: Skip cleanup stale user devices (MikroTik operations disabled).")
            return

        if str(app.config.get("AUTO_CLEANUP_STALE_USER_DEVICES_ENABLED", "True")).strip().lower() != "true":
            logger.info("Celery Task: Skip cleanup stale user devices (feature disabled).")
            return

        stale_days = int(app.config.get("DEVICE_STALE_DAYS", 30) or 0)
        if stale_days <= 0:
            logger.info("Celery Task: Skip cleanup stale user devices (DEVICE_STALE_DAYS <= 0).")
            return

        redis_client = getattr(app, "redis_client_otp", None)
        lock_key = "cleanup_stale_user_devices:lock"
        lock_acquired = False
        lock_ttl_seconds = max(
            300,
            int(app.config.get("AUTO_CLEANUP_STALE_USER_DEVICES_INTERVAL_SECONDS", 3600) or 3600),
        )

        if redis_client is not None:
            try:
                lock_acquired = bool(redis_client.set(lock_key, "1", nx=True, ex=lock_ttl_seconds))
            except Exception:
                lock_acquired = False
            if not lock_acquired:
                logger.info("Celery Task: Skip cleanup stale user devices (worker lain sedang berjalan).")
                return

        stale_cutoff = datetime.now(dt_timezone.utc) - timedelta(days=stale_days)
        summary = {
            "inspected": 0,
            "stale_candidates": 0,
            "skipped_active_host": 0,
            "deleted": 0,
            "deleted_from_last_bytes_updated_at": 0,
            "deleted_from_last_seen_at": 0,
            "deleted_from_authorized_at": 0,
            "deleted_from_first_seen_at": 0,
            "cleanup_failed": 0,
        }

        logger.info(
            "Celery Task: Memulai cleanup stale user devices (stale_days=%s, cutoff=%s).",
            stale_days,
            stale_cutoff.isoformat(),
        )

        try:
            with get_mikrotik_connection() as api:
                if not api:
                    raise RuntimeError("Gagal konek MikroTik")

                ok_host, host_usage_map, host_msg = get_hotspot_host_usage_map(api)
                if not ok_host:
                    raise RuntimeError(f"Gagal ambil hotspot host: {host_msg}")

                active_host_macs = {
                    str(mac_address or "").strip().upper()
                    for mac_address in (host_usage_map or {}).keys()
                    if str(mac_address or "").strip()
                }
                devices = db.session.scalars(db.select(UserDevice).options(selectinload(UserDevice.user))).all()
                summary["inspected"] = len(devices)

                for device in devices:
                    activity_at, activity_source = _get_user_device_last_activity(device)
                    if activity_at is None or activity_at >= stale_cutoff:
                        continue

                    summary["stale_candidates"] += 1
                    mac_address = str(getattr(device, "mac_address", "") or "").strip().upper()
                    if mac_address and mac_address in active_host_macs:
                        summary["skipped_active_host"] += 1
                        continue

                    try:
                        _cleanup_stale_user_device_router_state(api, device)
                        db.session.delete(device)
                        summary["deleted"] += 1
                        bucket_name = f"deleted_from_{activity_source}"
                        if bucket_name in summary:
                            summary[bucket_name] += 1
                    except Exception:
                        summary["cleanup_failed"] += 1
                        logger.exception(
                            "Celery Task: Gagal prune stale device id=%s mac=%s user=%s",
                            getattr(device, "id", None),
                            mac_address,
                            getattr(device, "user_id", None),
                        )

                if summary["deleted"] > 0:
                    db.session.commit()

                logger.info(
                    "Celery Task: Cleanup stale user devices selesai. %s",
                    json.dumps(summary, ensure_ascii=False),
                )
                return summary
        except Exception as e:
            logger.error("Celery Task: Cleanup stale user devices gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_stale_user_devices_task", {}, str(e))
            raise
        finally:
            if redis_client is not None and lock_acquired:
                try:
                    redis_client.delete(lock_key)
                except Exception:
                    pass


@celery_app.task(
    name="cleanup_stale_hotspot_hosts_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_stale_hotspot_hosts_task(self):
    app = create_app()
    with app.app_context():
        if str(app.config.get("ENABLE_MIKROTIK_OPERATIONS", "True")).strip().lower() != "true":
            logger.info("Celery Task: Skip cleanup stale hotspot hosts (MikroTik operations disabled).")
            return

        if str(app.config.get("AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_ENABLED", "True")).strip().lower() != "true":
            logger.info("Celery Task: Skip cleanup stale hotspot hosts (feature disabled).")
            return

        cidr_values = app.config.get("HOTSPOT_CLIENT_IP_CIDRS") or app.config.get("MIKROTIK_UNAUTHORIZED_CIDRS") or []
        networks = _parse_ip_networks(cidr_values)
        if not networks:
            logger.info("Celery Task: Skip cleanup stale hotspot hosts (no hotspot client CIDRs configured).")
            return

        min_idle_seconds = max(
            300,
            int(app.config.get("AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_MIN_IDLE_SECONDS", 3600) or 3600),
        )
        redis_client = getattr(app, "redis_client_otp", None)
        lock_key = "cleanup_stale_hotspot_hosts:lock"
        lock_acquired = False
        lock_ttl_seconds = max(
            300,
            int(app.config.get("AUTO_CLEANUP_STALE_HOTSPOT_HOSTS_INTERVAL_SECONDS", 1800) or 1800),
        )

        if redis_client is not None:
            try:
                lock_acquired = bool(redis_client.set(lock_key, "1", nx=True, ex=lock_ttl_seconds))
            except Exception:
                lock_acquired = False
            if not lock_acquired:
                logger.info("Celery Task: Skip cleanup stale hotspot hosts (worker lain sedang berjalan).")
                return

        summary = {
            "inspected": 0,
            "removed": 0,
            "skipped_in_subnet": 0,
            "skipped_translated": 0,
            "skipped_not_bypassed": 0,
            "skipped_no_current_host": 0,
            "skipped_no_local_ip": 0,
            "skipped_recent": 0,
            "failed": 0,
        }

        try:
            with get_mikrotik_connection() as api:
                if not api:
                    raise RuntimeError("Gagal konek MikroTik")

                host_rows = api.get_resource("/ip/hotspot/host").get() or []
                local_ips_by_mac = _collect_local_hotspot_ips_by_mac(api, networks)
                local_host_ips_by_mac = _collect_local_hotspot_host_ips_by_mac(host_rows, networks)
                summary["inspected"] = len(host_rows)

                for row in host_rows:
                    address = str(row.get("address") or "").strip()
                    to_address = str(row.get("to-address") or "").strip()
                    mac_address = str(row.get("mac-address") or "").strip().upper()
                    bypassed = str(row.get("bypassed") or "").strip().lower() == "true"

                    if _ip_in_networks(address, networks):
                        summary["skipped_in_subnet"] += 1
                        continue

                    if to_address and _ip_in_networks(to_address, networks):
                        summary["skipped_translated"] += 1
                        continue

                    if not mac_address or not bypassed:
                        summary["skipped_not_bypassed"] += 1
                        continue

                    local_host_ips = local_host_ips_by_mac.get(mac_address) or set()
                    if not local_host_ips:
                        summary["skipped_no_current_host"] += 1
                        continue

                    local_ips = local_ips_by_mac.get(mac_address) or set()
                    if not local_ips:
                        summary["skipped_no_local_ip"] += 1
                        continue

                    idle_seconds = _parse_mikrotik_duration_seconds(str(row.get("idle-time") or ""))
                    if idle_seconds < min_idle_seconds:
                        summary["skipped_recent"] += 1
                        continue

                    ok_remove, remove_msg, removed = remove_hotspot_host_entries(
                        api_connection=api,
                        mac_address=mac_address,
                        address=address or None,
                    )
                    if ok_remove:
                        summary["removed"] += int(removed or 0)
                    else:
                        summary["failed"] += 1
                        logger.info(
                            "Celery Task: Gagal cleanup stale hotspot host mac=%s address=%s msg=%s",
                            mac_address,
                            address,
                            remove_msg,
                        )

                logger.info(
                    "Celery Task: Cleanup stale hotspot hosts selesai. %s",
                    json.dumps(summary, ensure_ascii=False),
                )
                return summary
        except Exception as e:
            logger.error("Celery Task: Cleanup stale hotspot hosts gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_stale_hotspot_hosts_task", {}, str(e))
            raise
        finally:
            if redis_client is not None and lock_acquired:
                try:
                    redis_client.delete(lock_key)
                except Exception:
                    pass


@celery_app.task(
    name="cleanup_waiting_dhcp_arp_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_waiting_dhcp_arp_task(self):
    app = create_app()
    with app.app_context():
        config = _load_cleanup_waiting_dhcp_arp_config()

        if not config.mikrotik_operations_enabled:
            logger.info("Celery Task: Skip cleanup waiting DHCP/ARP (MikroTik operations disabled).")
            return

        if not config.feature_enabled:
            logger.info("Celery Task: Skip cleanup waiting DHCP/ARP (feature disabled).")
            return

        keyword = config.keyword
        min_last_seen_seconds = config.min_last_seen_seconds

        logger.info(
            "Celery Task: Memulai cleanup waiting DHCP/ARP (keyword=%s, min_last_seen_seconds=%s).",
            keyword,
            min_last_seen_seconds,
        )

        try:
            with get_mikrotik_connection() as api:
                if not api:
                    raise RuntimeError("Gagal konek MikroTik")

                lease_res = api.get_resource("/ip/dhcp-server/lease")
                arp_res = api.get_resource("/ip/arp")

                leases = lease_res.get() or []
                arp_rows = arp_res.get() or []
                arp_by_ip = {
                    str(row.get("address") or "").strip(): row
                    for row in arp_rows
                    if str(row.get("address") or "").strip()
                }
                arp_by_mac = {
                    str(row.get("mac-address") or "").strip().upper(): row
                    for row in arp_rows
                    if str(row.get("mac-address") or "").strip()
                }

                summary = {
                    "waiting_candidates": 0,
                    "skipped_recent": 0,
                    "lease_removed": 0,
                    "arp_removed": 0,
                    "lease_failed": 0,
                    "arp_failed": 0,
                }
                removed_arp_ids: set[str] = set()

                for lease in leases:
                    status = str(lease.get("status") or "").strip().lower()
                    comment_text = str(lease.get("comment") or "").lower()
                    if status != "waiting" or keyword not in comment_text:
                        continue

                    summary["waiting_candidates"] += 1

                    last_seen_text = str(lease.get("last-seen") or "").strip()
                    last_seen_seconds = _parse_mikrotik_duration_seconds(last_seen_text)
                    if last_seen_seconds and last_seen_seconds < min_last_seen_seconds:
                        summary["skipped_recent"] += 1
                        continue

                    ip_text = str(lease.get("address") or "").strip()
                    mac_text = str(lease.get("mac-address") or "").strip().upper()
                    lease_id = lease.get(".id") or lease.get("id")

                    if lease_id:
                        try:
                            lease_res.remove(id=lease_id)
                            summary["lease_removed"] += 1
                        except Exception:
                            summary["lease_failed"] += 1
                            logger.exception(
                                "Celery Task: Gagal remove waiting lease id=%s ip=%s mac=%s",
                                lease_id,
                                ip_text,
                                mac_text,
                            )

                    arp_row = arp_by_ip.get(ip_text) or arp_by_mac.get(mac_text)
                    arp_id = (arp_row or {}).get(".id") or (arp_row or {}).get("id")
                    if arp_id and str(arp_id) not in removed_arp_ids:
                        try:
                            arp_res.remove(id=arp_id)
                            removed_arp_ids.add(str(arp_id))
                            summary["arp_removed"] += 1
                        except Exception:
                            summary["arp_failed"] += 1
                            logger.exception(
                                "Celery Task: Gagal remove ARP id=%s ip=%s mac=%s",
                                arp_id,
                                ip_text,
                                mac_text,
                            )

                logger.info(
                    "Celery Task: Cleanup waiting DHCP/ARP selesai. %s",
                    json.dumps(summary, ensure_ascii=False),
                )
        except Exception as e:
            logger.error("Celery Task: Cleanup waiting DHCP/ARP gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_waiting_dhcp_arp_task", {}, str(e))
            raise


@celery_app.task(
    name="cleanup_inactive_users_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def cleanup_inactive_users_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai pembersihan pengguna tidak aktif.")
        try:
            result = cleanup_inactive_users()
            logger.info(f"Celery Task: Pembersihan selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Pembersihan gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "cleanup_inactive_users_task", {}, str(e))
            raise


@celery_app.task(
    name="sync_walled_garden_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_walled_garden_task(self):
    app = create_app()
    with app.app_context():
        logger.info("Celery Task: Memulai sinkronisasi walled-garden.")
        try:
            result = sync_walled_garden()
            logger.info(f"Celery Task: Walled-garden sync selesai. Result: {result}")
        except Exception as e:
            logger.error(f"Celery Task: Walled-garden sync gagal: {e}", exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_walled_garden_task", {}, str(e))
            raise


@celery_app.task(
    name="expire_stale_transactions_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def expire_stale_transactions_task(self):
    app = create_app()
    with app.app_context():
        now_utc = datetime.now(dt_timezone.utc)
        try:
            try:
                expiry_minutes = int(app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
            except Exception:
                expiry_minutes = 15
            expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
            # Grace window untuk baris dengan expiry_time: beri waktu webhook Midtrans yang
            # terlambat agar sempat diproses sebelum transaksi di-expire.
            # Configurable via TRANSACTION_EXPIRY_GRACE_MINUTES (default 5 menit).
            try:
                grace_expiry_minutes = int(app.config.get("TRANSACTION_EXPIRY_GRACE_MINUTES", 5))
            except Exception:
                grace_expiry_minutes = 5
            grace_expiry_minutes = max(0, min(grace_expiry_minutes, 60))
            expiry_cutoff = now_utc - timedelta(minutes=grace_expiry_minutes)

            # Grace window untuk baris legacy (tanpa expiry_time).
            grace_minutes = 5
            legacy_cutoff = now_utc - timedelta(minutes=(expiry_minutes + grace_minutes))

            # Expire transactions that were initiated or pending but exceeded expiry_time.
            q = (
                db.session.query(Transaction)
                .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
                .filter(Transaction.expiry_time.isnot(None))
                .filter(Transaction.expiry_time < expiry_cutoff)
            )
            to_expire = q.all()

            # Also expire legacy rows that never had expiry_time set.
            q_legacy = (
                db.session.query(Transaction)
                .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
                .filter(Transaction.expiry_time.is_(None))
                .filter(Transaction.created_at < legacy_cutoff)
            )
            to_expire.extend(q_legacy.all())

            if not to_expire:
                return

            for tx in to_expire:
                tx.status = TransactionStatus.EXPIRED

            db.session.commit()
            logger.info("Celery Task: Expired %s stale transactions.", len(to_expire))
        except Exception as e:
            logger.error("Celery Task: Expire stale transactions gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "expire_stale_transactions_task", {}, str(e))
            raise


@celery_app.task(
    name="purge_stale_quota_keys_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def purge_stale_quota_keys_task(self):
    """
    Hapus Redis key quota:last_bytes:mac:<MAC> untuk perangkat yang sudah
    tidak aktif (tidak ada di UserDevice atau last_seen_at > STALE_DAYS hari lalu).
    Jalankan harian jam 03:30 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("QUOTA_STALE_KEY_PURGE_ENABLED", "True") != "True":
            logger.info("Celery Task: Skip purge stale quota keys (fitur disabled).")
            return

        stale_days = max(1, settings_service.get_setting_as_int("QUOTA_STALE_KEY_STALE_DAYS", 30))
        redis_client = getattr(app, "redis_client_otp", None)
        if redis_client is None:
            logger.warning("Celery Task: Skip purge stale quota keys (redis_client tidak tersedia).")
            return

        try:
            prefix = "quota:last_bytes:mac:"
            # Kumpulkan semua MAC dari Redis
            redis_macs: set[str] = set()
            cursor = 0
            while True:
                cursor, keys = redis_client.scan(cursor, match=f"{prefix}*", count=200)
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    mac = key_str[len(prefix):]
                    if mac:
                        redis_macs.add(mac.upper())
                if cursor == 0:
                    break

            if not redis_macs:
                logger.info("Celery Task: Purge stale quota keys — tidak ada key ditemukan.")
                return

            # Cari MAC yang masih aktif di DB (last_seen dalam stale_days)
            cutoff = datetime.now(dt_timezone.utc) - timedelta(days=stale_days)
            active_macs: set[str] = set()
            rows = (
                db.session.query(UserDevice.mac_address)
                .filter(UserDevice.last_seen_at >= cutoff)
                .filter(UserDevice.mac_address.isnot(None))
                .all()
            )
            for row in rows:
                if row.mac_address:
                    active_macs.add(row.mac_address.upper())

            # Hapus key untuk MAC yang tidak aktif
            stale_macs = redis_macs - active_macs
            deleted = 0
            for mac in stale_macs:
                try:
                    redis_client.delete(f"{prefix}{mac}")
                    deleted += 1
                except Exception:
                    pass

            logger.info(
                "Celery Task: Purge stale quota keys selesai. "
                "redis_total=%s active_db=%s stale_deleted=%s",
                len(redis_macs),
                len(active_macs),
                deleted,
            )
        except Exception as e:
            logger.error("Celery Task: Purge stale quota keys gagal: %s", e, exc_info=True)
            if self.request.retries >= 1:
                _record_task_failure(app, "purge_stale_quota_keys_task", {}, str(e))
            raise


@celery_app.task(
    name="dlq_health_monitor_task",
    bind=True,
    retry_kwargs={"max_retries": 0},
)
def dlq_health_monitor_task(self):
    """
    Cek panjang Dead Letter Queue (DLQ) Celery setiap 15 menit.
    Kirim notifikasi WhatsApp ke superadmin jika DLQ tidak kosong,
    dengan throttle agar tidak spam (default: 1x per 60 menit).
    """
    app = create_app()
    with app.app_context():
        throttle_minutes = settings_service.get_setting_as_int("TASK_DLQ_ALERT_THROTTLE_MINUTES", 60)
        if throttle_minutes <= 0:
            return

        redis_client = getattr(app, "redis_client_otp", None)
        if redis_client is None:
            return

        try:
            # --- Check 1: Dead Letter Queue ---
            dlq_key = app.config.get("TASK_DLQ_REDIS_KEY", "celery:dlq")
            dlq_length = redis_client.llen(dlq_key)
            if dlq_length > 0:
                throttle_key = "dlq:alert:last_sent"
                if redis_client.exists(throttle_key):
                    logger.debug("Celery Task: DLQ monitor — alert throttled (DLQ=%s).", dlq_length)
                else:
                    items_raw = redis_client.lrange(dlq_key, -3, -1)
                    preview_lines = []
                    for raw in items_raw:
                        try:
                            item = json.loads(raw)
                            preview_lines.append(f"- [{item.get('task','?')}] {item.get('error','')[:80]}")
                        except Exception:
                            pass
                    preview = "\n".join(preview_lines) if preview_lines else "(tidak bisa dibaca)"

                    admin_phone = app.config.get("SUPERADMIN_PHONE", "")
                    if admin_phone:
                        wa_number = re.sub(r"[^0-9]", "", str(admin_phone))
                        if wa_number.startswith("0"):
                            wa_number = "62" + wa_number[1:]
                        msg = (
                            f"⚠️ *ALERT: Celery DLQ tidak kosong*\n"
                            f"Total task gagal: *{dlq_length}*\n\n"
                            f"Preview 3 terakhir:\n{preview}\n\n"
                            f"Cek log container celery_worker untuk detail.\n"
                            f"Throttle: alert berikutnya dalam {throttle_minutes} menit."
                        )
                        try:
                            send_whatsapp_message(wa_number, msg)
                            logger.warning(
                                "Celery Task: DLQ alert dikirim ke admin. DLQ length=%s.", dlq_length
                            )
                        except Exception as wa_err:
                            logger.error("Celery Task: Gagal kirim DLQ alert WA: %s", wa_err)
                    redis_client.setex(throttle_key, throttle_minutes * 60, 1)

            # --- Check 2: Circuit breaker open alerts ---
            cb_count = redis_client.llen("cb:open_alerts")
            if cb_count > 0:
                raw_alerts = redis_client.lrange("cb:open_alerts", 0, -1)
                redis_client.delete("cb:open_alerts")
                circuit_names = []
                for raw in raw_alerts:
                    try:
                        item = json.loads(raw)
                        circuit_names.append(item.get("name", "unknown"))
                    except Exception:
                        pass
                if circuit_names:
                    alert_phone = (
                        app.config.get("CIRCUIT_BREAKER_ALERT_PHONE", "")
                        or app.config.get("SUPERADMIN_PHONE", "")
                    )
                    if alert_phone:
                        wa_number = re.sub(r"[^0-9]", "", str(alert_phone))
                        if wa_number.startswith("0"):
                            wa_number = "62" + wa_number[1:]
                        threshold = app.config.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5)
                        msg = (
                            f"🔴 *ALERT: Circuit Breaker Terbuka*\n"
                            f"Circuit: *{', '.join(sorted(set(circuit_names)))}*\n\n"
                            f"Koneksi ke layanan tersebut bermasalah "
                            f"(≥{threshold} failure berturut-turut).\n"
                            f"Router/API tidak dapat dijangkau.\n"
                            f"Cek log container backend / celery_worker untuk detail."
                        )
                        try:
                            send_whatsapp_message(wa_number, msg)
                            logger.warning(
                                "Celery Task: Circuit breaker open alert dikirim: %s", circuit_names
                            )
                        except Exception as wa_err:
                            logger.error(
                                "Celery Task: Gagal kirim circuit breaker alert WA: %s", wa_err
                            )

        except Exception as e:
            logger.error("Celery Task: DLQ health monitor gagal: %s", e, exc_info=True)


@celery_app.task(
    name="purge_quota_mutation_ledger_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def purge_quota_mutation_ledger_task(self):
    """
    Hapus entri quota_mutation_ledger yang lebih tua dari QUOTA_MUTATION_LEDGER_RETENTION_DAYS
    (default 90 hari). Mencegah tabel tumbuh tak terbatas dan menjaga performa query analytics.
    Jalan harian jam 04:00 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        try:
            try:
                retention_days = int(app.config.get("QUOTA_MUTATION_LEDGER_RETENTION_DAYS", 90))
            except Exception:
                retention_days = 90
            retention_days = min(90, max(30, retention_days))

            cutoff = datetime.now(dt_timezone.utc) - timedelta(days=retention_days)
            deleted = (
                db.session.query(QuotaMutationLedger)
                .filter(QuotaMutationLedger.created_at < cutoff)
                .delete(synchronize_session=False)
            )
            if deleted:
                db.session.commit()
                logger.info(
                    "Celery Task: Purged %s quota_mutation_ledger entri (retention=%d hari, cutoff=%s).",
                    deleted, retention_days, cutoff.date(),
                )
            else:
                logger.info(
                    "Celery Task: quota_mutation_ledger purge — tidak ada entri > %d hari.", retention_days
                )
        except Exception as e:
            db.session.rollback()
            logger.error("Celery Task: purge_quota_mutation_ledger gagal: %s", e, exc_info=True)
            if self.request.retries >= 1:
                _record_task_failure(app, "purge_quota_mutation_ledger_task", {}, str(e))
            raise


@celery_app.task(
    name="revoke_expired_refresh_tokens_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 1},
)
def revoke_expired_refresh_tokens_task(self):
    """
    Hapus refresh token yang sudah expired atau sudah di-revoke lebih dari
    REFRESH_TOKEN_CLEANUP_KEEP_DAYS (default 7) hari lalu.
    Mencegah tabel refresh_tokens akumulasi tak terbatas.
    Jalan harian jam 04:30 via Celery Beat.
    """
    app = create_app()
    with app.app_context():
        try:
            try:
                keep_days = int(app.config.get("REFRESH_TOKEN_CLEANUP_KEEP_DAYS", 7))
            except Exception:
                keep_days = 7
            keep_days = max(1, keep_days)

            now_utc = datetime.now(dt_timezone.utc)
            revoked_cutoff = now_utc - timedelta(days=keep_days)

            # Hapus token yang sudah expired
            deleted_expired = (
                db.session.query(RefreshToken)
                .filter(RefreshToken.expires_at < now_utc)
                .delete(synchronize_session=False)
            )
            # Hapus token yang sudah di-revoke (revoked_at IS NOT NULL) dan issued > keep_days lalu
            deleted_revoked = (
                db.session.query(RefreshToken)
                .filter(
                    RefreshToken.revoked_at.isnot(None),
                    RefreshToken.issued_at < revoked_cutoff,
                )
                .delete(synchronize_session=False)
            )
            total = deleted_expired + deleted_revoked
            if total:
                db.session.commit()
                logger.info(
                    "Celery Task: Cleanup refresh tokens — expired=%s, revoked_old=%s (total=%s).",
                    deleted_expired, deleted_revoked, total,
                )
            else:
                logger.info("Celery Task: Refresh token cleanup — tidak ada token usang.")
        except Exception as e:
            logger.error("Celery Task: Error cleanup refresh tokens: %s", str(e))
            raise


@celery_app.task(
    name="upsert_dhcp_static_lease_instant_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def upsert_dhcp_static_lease_instant_task(self, mac_address: str, address: str, comment: str, server: str | None):
    """
    Instant DHCP static lease upsert callback triggered after successful device binding.
    Runs as high-priority Celery task with automatic retry on MikroTik failures.

    Args:
        mac_address: MAC address of device (e.g., "AA:BB:CC:DD:EE:FF")
        address: IP address to bind (e.g., "172.16.2.123")
        comment: Comment for DHCP lease (contains user info and timestamp)
        server: DHCP server name in MikroTik (e.g., "Klien")
    """
    app = create_app()
    with app.app_context():
        if not bool(app.config.get("ENABLE_MIKROTIK_OPERATIONS", True)):
            logger.info("Celery Task: Skip instant DHCP upsert (MikroTik operations disabled).")
            return {"success": True, "skipped": True}

        if not server or not str(server).strip():
            logger.warning("Skip instant DHCP upsert: DHCP server name not specified.")
            return {"success": False, "error": "dhcp_server_not_configured"}

        try:
            from app.infrastructure.gateways.mikrotik_client import upsert_dhcp_static_lease as gateway_upsert_dhcp

            ok = gateway_upsert_dhcp(
                api_connection=None,  # Create new connection for this task
                mac_address=mac_address,
                address=address,
                comment=comment,
                server=server,
            )

            if ok:
                logger.info(
                    "Celery Task: Instant DHCP lease upserted successfully — mac=%s address=%s server=%s",
                    mac_address, address, server
                )
                return {"success": True}
            else:
                logger.warning(
                    "Celery Task: Instant DHCP lease upsert failed — mac=%s address=%s server=%s (will retry)",
                    mac_address, address, server
                )
                raise Exception(f"DHCP upsert returned False for mac={mac_address} address={address}")
        except Exception as e:
            logger.error(
                "Celery Task: Error during instant DHCP upsert — mac=%s address=%s error=%s (will retry)",
                mac_address, address, str(e)
            )
            raise


# ─────────────────────────────────────────────────────────────────────────────
# TASK: sync_access_banking_task  (7.3 Akses-Banking Scheduler)
# Populate address-list Bypass_Server di MikroTik dengan IP banking domains.
# Hanya mengelola entri dengan comment 'source=banking-sync' — entri manual aman.
# ─────────────────────────────────────────────────────────────────────────────
@celery_app.task(
    name="sync_access_banking_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def sync_access_banking_task(self):
    """Populate Bypass_Server address-list di MikroTik dengan banking domain IPs.

    - Hanya mengelola entri dengan comment 'source=banking-sync'.
    - Entri manual (comment berbeda) tidak disentuh sama sekali.
    - Resolve domain → IP via socket. Skip jika AKSES_BANKING_ENABLED=False.
    - List name configurable via setting AKSES_BANKING_LIST_NAME (default Bypass_Server).
    """
    import socket as _socket

    app = create_app()
    with app.app_context():
        enabled = settings_service.get_setting("AKSES_BANKING_ENABLED", "True") == "True"
        if not enabled:
            logger.info("Celery Task: sync_access_banking_task dinonaktifkan (AKSES_BANKING_ENABLED=False).")
            return {"skipped": "feature_disabled"}

        mikrotik_ops = settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") == "True"
        if not mikrotik_ops:
            logger.info("Celery Task: sync_access_banking_task skip (ENABLE_MIKROTIK_OPERATIONS=False).")
            return {"skipped": "mikrotik_ops_disabled"}

        # Daftar domain banking — configurable via settings DB.
        # Default mencakup bank-bank umum di Indonesia.
        domains_raw = settings_service.get_setting(
            "AKSES_BANKING_DOMAINS",
            "klikbca.com,bri.co.id,bankmandiri.co.id,bni.co.id,cimbniaga.co.id,"
            "permatabank.co.id,ocbcnisp.com,bca.co.id,danamon.co.id,btn.co.id",
        ) or ""
        banking_domains = [d.strip() for d in domains_raw.split(",") if d.strip()]

        list_name = settings_service.get_setting("AKSES_BANKING_LIST_NAME", "Bypass_Server") or "Bypass_Server"
        comment_marker = "source=banking-sync"
        comment_prefix = "AUTO-BANKING-BYPASS"

        db.session.remove()

        logger.info(
            "Celery Task: Memulai sync banking bypass. domains=%d list=%s",
            len(banking_domains),
            list_name,
        )

        try:
            # Resolve IP untuk setiap domain (ipv4 saja, CDN banking umumnya publik)
            # setdefaulttimeout(5): cegah getaddrinfo block lama jika DNS lambat/down.
            # Restore ke None setelah loop agar tidak pengaruhi operasi socket lain.
            resolved_ips: dict[str, str] = {}  # ip → domain
            _socket.setdefaulttimeout(5)
            try:
                for domain in banking_domains:
                    try:
                        for addr_info in _socket.getaddrinfo(domain, None, _socket.AF_INET):
                            ip = str(addr_info[4][0])
                            try:
                                ipaddress.ip_address(ip)
                                resolved_ips[ip] = domain
                            except ValueError:
                                pass
                    except Exception as exc:
                        logger.warning("Banking sync: gagal resolve domain=%s: %s", domain, exc)
            finally:
                _socket.setdefaulttimeout(None)

            if not resolved_ips:
                logger.warning(
                    "Banking sync: tidak ada IP berhasil di-resolve dari %d domain — cek koneksi DNS.",
                    len(banking_domains),
                )
                return {"ok": False, "reason": "no_ips_resolved", "domains_checked": len(banking_domains)}

            with get_mikrotik_connection() as api:
                if not api:
                    raise RuntimeError("Gagal konek MikroTik untuk banking sync")

                ok_get, current_entries, get_msg = get_firewall_address_list_entries(api, list_name)
                if not ok_get:
                    raise RuntimeError(f"Gagal ambil entri {list_name}: {get_msg}")

                # Hanya pertimbangkan entri yang dikelola oleh task ini
                banking_entries: dict[str, dict] = {}
                for entry in current_entries:
                    entry_comment = str(entry.get("comment") or "")
                    if comment_marker in entry_comment:
                        entry_ip = str(entry.get("address") or "").strip()
                        if entry_ip:
                            banking_entries[entry_ip] = entry

                summary = {
                    "domains_processed": len(banking_domains),
                    "ips_resolved": len(resolved_ips),
                    "added": 0,
                    "updated": 0,
                    "removed_stale": 0,
                    "errors": 0,
                }

                # Upsert IP yang berhasil di-resolve
                for ip, domain in resolved_ips.items():
                    entry_comment = (
                        f"{comment_prefix}|{comment_marker}|domain={domain}|managed-by=lpsaring"
                    )
                    ok_upsert, upsert_msg = upsert_address_list_entry(
                        api_connection=api,
                        address=ip,
                        list_name=list_name,
                        comment=entry_comment,
                    )
                    if ok_upsert:
                        if ip in banking_entries:
                            summary["updated"] += 1
                        else:
                            summary["added"] += 1
                    else:
                        summary["errors"] += 1
                        logger.warning(
                            "Banking sync: gagal upsert ip=%s domain=%s list=%s: %s",
                            ip, domain, list_name, upsert_msg,
                        )

                # Hapus entri banking-sync yang sudah stale (IP tidak lagi di-resolve)
                for stale_ip in banking_entries:
                    if stale_ip not in resolved_ips:
                        ok_rm, rm_msg = remove_address_list_entry(
                            api_connection=api,
                            address=stale_ip,
                            list_name=list_name,
                        )
                        if ok_rm:
                            summary["removed_stale"] += 1
                        else:
                            logger.warning(
                                "Banking sync: gagal remove stale ip=%s list=%s: %s",
                                stale_ip, list_name, rm_msg,
                            )

                logger.info("Celery Task: Banking bypass sync selesai. %s", json.dumps(summary))
                return summary

        except Exception as e:
            logger.error("Celery Task: Banking sync gagal: %s", e, exc_info=True)
            if self.request.retries >= 2:
                _record_task_failure(app, "sync_access_banking_task", {}, str(e))
            raise


# ─────────────────────────────────────────────────────────────────────────────
# TASK: enforce_overdue_debt_block_task  (P1 — Auto-block post-due-date)
# Blokir user dengan tunggakan yang sudah melewati due_date (bukan hanya EOM).
# Berbeda dari enforce_end_of_month_debt_block_task yang hanya jalan di akhir bulan.
# ─────────────────────────────────────────────────────────────────────────────
@celery_app.task(
    name="enforce_overdue_debt_block_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 2},
)
def enforce_overdue_debt_block_task(self):
    """Blokir user yang tunggakan manualnya sudah melewati due_date.

    - Berjalan harian (default jam 08:00 lokal via beat schedule).
    - Hanya menangani debt dari bulan SEBELUMNYA (bukan bulan berjalan,
      yang ditangani oleh enforce_end_of_month_debt_block_task di hari terakhir).
    - Skip user yang sudah diblokir, unlimited, atau tidak aktif.
    - Kirim WA warning sebelum block.
    - Configurable via setting ENABLE_OVERDUE_DEBT_BLOCK (default True).
    """
    app = create_app()
    with app.app_context():
        if settings_service.get_setting("ENABLE_OVERDUE_DEBT_BLOCK", "True") != "True":
            logger.info("Overdue debt block: Dinonaktifkan via setting ENABLE_OVERDUE_DEBT_BLOCK.")
            return {"skipped": "feature_disabled"}

        if settings_service.get_setting("ENABLE_MIKROTIK_OPERATIONS", "True") != "True":
            logger.info("Overdue debt block: MikroTik operations disabled via ENABLE_MIKROTIK_OPERATIONS.")
            return {"skipped": "mikrotik_disabled"}

        now_local = get_app_local_datetime()
        today = now_local.date()

        # Impor lokal agar tidak mempengaruhi loading modul global
        from sqlalchemy.orm import joinedload as _joinedload
        from app.infrastructure.db.models import UserQuotaDebt, User

        try:
            overdue_debts = (
                db.session.query(UserQuotaDebt)
                .options(
                    _joinedload(UserQuotaDebt.user)
                    .selectinload(User.devices)  # CRITICAL: Load devices relationship to avoid DetachedInstanceError
                )
                .filter(UserQuotaDebt.paid_at.is_(None))
                .filter(UserQuotaDebt.is_paid.is_(False))
                .filter(UserQuotaDebt.due_date.isnot(None))
                # Hanya debt dari bulan sebelumnya (due_date < hari ini)
                .filter(UserQuotaDebt.due_date < today)
                .all()
            )
        except Exception:
            logger.exception("Overdue debt block: gagal query overdue debts dari DB.")
            db.session.remove()
            return {"checked": 0, "blocked": 0, "error": "db_query_failed"}

        if not overdue_debts:
            logger.info("Overdue debt block: Tidak ada debt melewati due_date.")
            return {"checked": 0, "blocked": 0}

        # Group debt by user_id
        user_debts: dict = {}
        for debt in overdue_debts:
            user = debt.user
            if not user:
                continue
            uid = str(user.id)
            if uid not in user_debts:
                user_debts[uid] = {"user": user, "debts": []}
            user_debts[uid]["debts"].append(debt)

        blocked_profile = settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "inactive") or "inactive"
        list_blocked = settings_service.get_setting("MIKROTIK_ADDRESS_LIST_BLOCKED", "blocked") or "blocked"
        enable_wa = settings_service.get_setting("ENABLE_WHATSAPP_NOTIFICATIONS", "True") == "True"
        other_status_lists = [
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_ACTIVE", "active") or "active",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_FUP", "fup") or "fup",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_INACTIVE", "inactive") or "inactive",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_EXPIRED", "expired") or "expired",
            settings_service.get_setting("MIKROTIK_ADDRESS_LIST_HABIS", "habis") or "habis",
        ]
        blocked_binding_type = settings_service.get_ip_binding_type_setting("IP_BINDING_TYPE_BLOCKED", "blocked")

        summary = {
            "checked": len(user_debts),
            "skipped_already_blocked": 0,
            "skipped_unlimited": 0,
            "skipped_non_approved": 0,  # Renamed from skipped_inactive
            "skipped_non_user_role": 0,  # New: explicit counter for admin/komandan
            "warn_sent": 0,
            "warn_failed": 0,
            "blocked": 0,
            "block_failed": 0,
        }

        for uid, data in user_debts.items():
            user = data["user"]
            debts = data["debts"]

            # Guard: hanya blokir USER aktif yang disetujui, bukan admin/unlimited
            if not getattr(user, "is_active", False):
                summary["skipped_non_approved"] += 1  # Actually: not active
                continue
            if getattr(user, "approval_status", None) != ApprovalStatus.APPROVED:
                summary["skipped_non_approved"] += 1
                continue
            if getattr(user, "role", None) != UserRole.USER:
                summary["skipped_non_user_role"] += 1  # Explicit: komandan/admin
                continue
            if getattr(user, "is_unlimited_user", False):
                summary["skipped_unlimited"] += 1
                continue
            if getattr(user, "is_blocked", False):
                summary["skipped_already_blocked"] += 1
                continue

            username_08 = format_to_local_phone(user.phone_number) or str(user.phone_number or "")
            total_debt_mb = sum(int(d.amount_mb or 0) for d in debts)
            oldest_due_date = min(d.due_date for d in debts if d.due_date)
            days_overdue = (today - oldest_due_date).days

            # --- Step 1: WA warning sebelum block ---
            if enable_wa:
                try:
                    _debt_gb = total_debt_mb / 1024
                    _debt_display = f"{_debt_gb:.1f} GB" if _debt_gb >= 1 else f"{total_debt_mb} MB"
                    _portal_url = str(app.config.get("APP_PUBLIC_BASE_URL") or "").strip().rstrip("/")
                    wa_msg = (
                        f"\u26a0\ufe0f *TAGIHAN JATUH TEMPO — AKSES AKAN DIBLOKIR*\n\n"
                        f"Halo {username_08},\n\n"
                        f"Tunggakan kuota Anda sebesar *{_debt_display}* "
                        f"telah melewati jatuh tempo *{oldest_due_date.strftime('%d-%m-%Y')}* "
                        f"({days_overdue} hari yang lalu).\n\n"
                        f"Akses internet Anda *diblokir* sekarang.\n\n"
                        f"Lunasi tagihan di: {_portal_url}\n\n"
                        f"Hubungi admin jika ada pertanyaan."
                    )
                    ok_wa = bool(
                        send_whatsapp_message(
                            recipient_number=user.phone_number,
                            message_body=wa_msg,
                        )
                    )
                    if ok_wa:
                        summary["warn_sent"] += 1
                    else:
                        summary["warn_failed"] += 1
                except Exception:
                    logger.exception("Overdue debt block: gagal kirim WA ke user=%s", uid)
                    summary["warn_failed"] += 1

            # --- Step 2: Block di DB + MikroTik ---
            try:
                lock_user_quota_row(user)
                before_state = snapshot_user_quota_state(user)

                if not user.mikrotik_password:
                    user.mikrotik_password = "".join(secrets.choice("0123456789") for _ in range(6))

                _handle_mikrotik_operation(
                    activate_or_update_hotspot_user,
                    user_mikrotik_username=username_08,
                    hotspot_password=user.mikrotik_password,
                    mikrotik_profile_name=blocked_profile,
                    limit_bytes_total=1,
                    session_timeout="1s",
                    comment=f"blocked|quota-debt-overdue|user={username_08}",
                    server=user.mikrotik_server_name,
                    force_update_profile=True,
                )

                user.is_blocked = True
                user.blocked_reason = (
                    f"tunggakan_overdue|debt_mb={total_debt_mb}|due={oldest_due_date}|days_overdue={days_overdue}"
                )
                user.blocked_at = datetime.now(dt_timezone.utc)
                user.blocked_by_id = None

                with get_mikrotik_connection() as api:
                    if api:
                        ok_host, host_map, _ = get_hotspot_host_usage_map(api)
                        host_map = host_map if ok_host else {}

                        for device in user.devices or []:
                            mac = str(getattr(device, "mac_address", "") or "").upper().strip()
                            if not mac:
                                continue
                            upsert_ip_binding(
                                api_connection=api,
                                mac_address=mac,
                                binding_type=blocked_binding_type,
                                comment=f"blocked|debt-overdue|user={username_08}|uid={user.id}",
                            )
                            ip_addr = str(getattr(device, "ip_address", "") or "").strip()
                            if not ip_addr:
                                ip_addr = str(host_map.get(mac, {}).get("address") or "").strip()
                            if not ip_addr:
                                continue
                            upsert_address_list_entry(
                                api_connection=api,
                                address=ip_addr,
                                list_name=list_blocked,
                                comment=f"lpsaring|status=blocked|reason=debt-overdue|user={username_08}|uid={user.id}",
                            )
                            for other_list in other_status_lists:
                                if other_list and other_list != list_blocked:
                                    remove_address_list_entry(
                                        api_connection=api,
                                        address=ip_addr,
                                        list_name=other_list,
                                    )

                db.session.add(user)
                append_quota_mutation_event(
                    user=user,
                    source="policy.block_transition:debt_overdue",
                    before_state=before_state,
                    after_state=snapshot_user_quota_state(user),
                    event_details={
                        "action": "block",
                        "reason": "debt_overdue",
                        "total_debt_mb": total_debt_mb,
                        "oldest_due_date": str(oldest_due_date),
                        "days_overdue": days_overdue,
                        "debt_count": len(debts),
                    },
                )
                db.session.commit()
                summary["blocked"] += 1
                increment_metric("overdue.debt_block.blocked")
                logger.info(
                    "Overdue debt block: user=%s diblokir (debt=%dMB, due=%s, %d hari lewat).",
                    uid, total_debt_mb, oldest_due_date, days_overdue,
                )
            except Exception:
                logger.exception("Overdue debt block: gagal block user=%s", uid)
                db.session.rollback()
                summary["block_failed"] += 1

        increment_metric("overdue.debt_block.checked", summary["checked"])
        logger.info("Overdue debt block summary: %s", json.dumps(summary))
        db.session.remove()  # Cleanup session after all operations complete
        return summary
