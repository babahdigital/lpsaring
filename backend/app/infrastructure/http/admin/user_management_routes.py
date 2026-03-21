# backend/app/infrastructure/http/admin/user_management_routes.py
import uuid
import re
from datetime import date, datetime, timedelta, timezone as dt_timezone
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
    QuotaMutationLedger,
    Transaction,
    TransactionStatus,
    UserDevice,
)
from app.infrastructure.http.decorators import admin_required
from app.infrastructure.http.schemas.user_schemas import (
    UserResponseSchema,
    AdminSelfProfileUpdateRequestSchema,
    UserQuotaDebtItemResponseSchema,
    UserUpdateByAdminSchema,
)
from app.services.user_management import user_debt as user_debt_service
from app.utils.formatters import (
    get_phone_number_variations,
    format_mb_to_gb,
    format_app_date_display,
    format_app_datetime_display,
    normalize_to_e164,
)

from app.infrastructure.db.models import UserQuotaDebt


# [FIX] Menambahkan kembali impor yang hilang untuk endpoint /mikrotik-status
from app.utils.formatters import format_to_local_phone, format_app_datetime
from app.services.user_management.helpers import _handle_mikrotik_operation, _send_whatsapp_notification
from app.infrastructure.gateways.mikrotik_client import get_hotspot_user_details, get_mikrotik_connection

from app.services.user_management.helpers import _log_admin_action

from app.services import settings_service
from app.services.notification_service import (
    generate_temp_debt_report_token,
    generate_temp_debt_settlement_receipt_token,
    generate_temp_user_detail_report_token,
    get_notification_message,
    verify_temp_debt_report_token,
    verify_temp_debt_settlement_receipt_token,
    verify_temp_user_detail_report_token,
)
from app.services.debt_settlement_receipt_service import (
    ADMIN_SETTLE_ALL_SOURCE,
    ADMIN_SETTLE_SINGLE_SOURCE,
    build_receipt_business_identity_context,
    build_debt_settlement_receipt_context,
    estimate_amount_rp_for_mb,
    format_currency_idr,
    get_latest_admin_debt_settlement_mutation,
)
from app.services.manual_debt_report_service import (
    build_user_debt_whatsapp_context as build_user_debt_whatsapp_context_shared,
    build_user_manual_debt_report_context as build_user_manual_debt_report_context_shared,
)
from app.services.quota_history_service import get_user_quota_history_payload
from app.tasks import send_whatsapp_invoice_task
from app.utils.block_reasons import is_debt_block_reason

from app.utils.quota_debt import estimate_debt_rp_from_cheapest_package
from app.services.user_management import user_approval, user_deletion, user_profile as user_profile_service
from app.services.access_policy_service import get_user_access_status

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
        "processed_at_display": format_app_datetime_display(item.processed_at, fallback="-"),
        "rejection_reason": item.rejection_reason,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "created_at_display": format_app_datetime_display(item.created_at, fallback="-"),
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


def _format_currency_idr(value: int | float | None) -> str:
    amount = int(float(value or 0))
    return f"Rp {amount:,}".replace(",", ".")


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
        ref = db.session.execute(base_q.order_by(Package.data_quota_gb.desc(), Package.price.asc()).limit(1)).scalar_one_or_none()
    return ref


def _estimate_for_debt_mb(value_mb: float):
    pkg = _pick_ref_pkg_for_debt_mb(value_mb)
    return estimate_debt_rp_from_cheapest_package(
        debt_mb=float(value_mb or 0),
        cheapest_package_price_rp=int(pkg.price) if pkg and pkg.price is not None else None,
        cheapest_package_quota_gb=float(pkg.data_quota_gb) if pkg and pkg.data_quota_gb is not None else None,
        cheapest_package_name=str(pkg.name) if pkg and pkg.name else None,
    )


def _build_user_manual_debt_report_context(user: User) -> dict:
    return build_user_manual_debt_report_context_shared(user)


def _render_user_manual_debts_pdf_bytes(context: dict, public_base_url: str) -> bytes:
    from weasyprint import HTML  # type: ignore

    html_string = render_template("admin_user_debt_report.html", **context)
    pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
    if pdf_bytes is None:
        raise RuntimeError("Gagal menghasilkan PDF debt report.")
    return pdf_bytes


def _build_user_debt_whatsapp_context(user: User, report_context: dict, pdf_url: str) -> dict:
    return build_user_debt_whatsapp_context_shared(user, report_context, pdf_url)


def _resolve_public_base_url() -> str:
    return (
        settings_service.get_setting("APP_PUBLIC_BASE_URL")
        or settings_service.get_setting("FRONTEND_URL")
        or settings_service.get_setting("APP_LINK_USER")
        or request.url_root
    )


def _render_debt_settlement_receipt_pdf_bytes(context: dict, public_base_url: str) -> bytes:
    from weasyprint import HTML  # type: ignore

    html_string = render_template("debt_settlement_receipt.html", **context)
    pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
    if pdf_bytes is None:
        raise RuntimeError("Gagal menghasilkan PDF receipt pelunasan debt.")
    return pdf_bytes


def _build_debt_settlement_receipt_url(entry_id: uuid.UUID, base_url: str) -> str:
    token = generate_temp_debt_settlement_receipt_token(str(entry_id))
    return f"{base_url.rstrip('/')}/api/admin/users/debt-settlements/temp/{token}.pdf"


def _resolve_admin_whatsapp_default() -> str:
    candidates = [
        settings_service.get_setting("NUXT_PUBLIC_ADMIN_WHATSAPP"),
        current_app.config.get("NUXT_PUBLIC_ADMIN_WHATSAPP"),
        current_app.config.get("BUSINESS_PHONE"),
    ]
    for candidate in candidates:
        raw = str(candidate or "").strip()
        if not raw:
            continue
        try:
            return normalize_to_e164(raw)
        except Exception:
            continue
    return ""


def _resolve_public_portal_url() -> str:
    return (
        settings_service.get_setting("APP_LINK_USER")
        or settings_service.get_setting("FRONTEND_URL")
        or settings_service.get_setting("APP_PUBLIC_BASE_URL")
        or request.url_root
    )


def _render_temp_document_error_page(
    *,
    status_code: int,
    title: str,
    message: str,
    document_label: str,
    badge: str,
):
    action_url = _resolve_public_portal_url()
    response = make_response(
        render_template(
            "public_temp_document_error.html",
            status_code=status_code,
            title=title,
            message=message,
            document_label=document_label,
            badge=badge,
            action_url=action_url,
        ),
        status_code,
    )
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


def _humanize_detail_profile_name(user: User, raw_profile_name: str | None) -> str:
    raw_value = str(raw_profile_name or "").strip()
    lowered = raw_value.lower()

    alias_map: dict[str, str] = {}
    for value, label in [
        (settings_service.get_setting("MIKROTIK_PROFILE_ACTIVE", "default"), "Aktif"),
        (settings_service.get_setting("MIKROTIK_PROFILE_DEFAULT", "default"), "Aktif"),
        (settings_service.get_setting("MIKROTIK_PROFILE_USER", "user"), "Aktif"),
        (settings_service.get_setting("MIKROTIK_PROFILE_KOMANDAN", "komandan"), "Komandan"),
        (settings_service.get_setting("MIKROTIK_PROFILE_FUP", "fup"), "FUP"),
        (settings_service.get_setting("MIKROTIK_PROFILE_HABIS", "habis"), "Habis"),
        (settings_service.get_setting("MIKROTIK_PROFILE_EXPIRED", "expired"), "Habis"),
        (settings_service.get_setting("MIKROTIK_BLOCKED_PROFILE", "blocked"), "Blokir"),
        (settings_service.get_setting("MIKROTIK_PROFILE_UNLIMITED", "unlimited"), "Unlimited"),
        (settings_service.get_setting("MIKROTIK_PROFILE_INACTIVE", "inactive"), "Inactive"),
    ]:
        normalized = str(value or "").strip().lower()
        if normalized:
            alias_map[normalized] = label

    for needle, label in [
        ("blocked", "Blokir"),
        ("blokir", "Blokir"),
        ("fup", "FUP"),
        ("habis", "Habis"),
        ("expired", "Habis"),
        ("inactive", "Inactive"),
        ("unlimited", "Unlimited"),
        ("komandan", "Komandan"),
        ("aktif", "Aktif"),
        ("active", "Aktif"),
        ("default", "Aktif"),
        ("user", "Aktif"),
    ]:
        if needle not in alias_map:
            alias_map[needle] = label

    if lowered in alias_map:
        return alias_map[lowered]

    if not lowered:
        if getattr(user, "is_blocked", False):
            return "Blokir"
        if getattr(user, "is_unlimited_user", False):
            return "Unlimited"
        if getattr(user, "is_active", False) is not True:
            return "Inactive"
        if getattr(user, "role", None) == UserRole.KOMANDAN:
            return "Komandan"
        return "Aktif"

    for needle, label in alias_map.items():
        if needle and needle in lowered:
            return label

    cleaned = re.sub(r"^(profile|paket|pkg)[-_\s]+", "", raw_value, flags=re.IGNORECASE)
    cleaned = re.sub(r"[_-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "Aktif"
    if cleaned.upper() == "FUP":
        return "FUP"
    return " ".join(part.upper() if len(part) <= 3 else part.capitalize() for part in cleaned.split(" "))


def _format_detail_role_label(role: UserRole | None) -> str:
    mapping = {
        UserRole.USER: "User",
        UserRole.KOMANDAN: "Komandan",
        UserRole.ADMIN: "Admin",
        UserRole.SUPER_ADMIN: "Super Admin",
    }
    if role is None:
        return "-"
    if not isinstance(role, UserRole):
        raw_value = str(getattr(role, "value", role) or "").strip().upper()
        role = UserRole.__members__.get(raw_value)
        if role is None:
            return str(getattr(role, "value", raw_value) or "-")
    return mapping.get(role, "-")


def _format_detail_kamar_label(kamar: str | None) -> str:
    raw_value = str(getattr(kamar, "value", kamar) or "").strip()
    if not raw_value:
        return ""

    normalized = raw_value.replace(" ", "")
    lowered = normalized.lower()
    for prefix in ("kamar_", "kamr_"):
        if lowered.startswith(prefix) and normalized[len(prefix):].isdigit():
            return normalized[len(prefix):]

    match = re.search(r"(\d+)$", normalized)
    if match:
        return match.group(1)

    return raw_value.replace("_", " ").strip()


def _format_detail_address_label(user: User) -> str:
    if getattr(user, "is_tamping", False):
        tamping_type = str(getattr(user, "tamping_type", "") or "").strip()
        return f"Tamping • {tamping_type}" if tamping_type else "Tamping"

    blok_value = str(getattr(user, "blok", "") or "").strip()
    kamar_value = _format_detail_kamar_label(getattr(user, "kamar", None))
    if blok_value and kamar_value:
        return f"Blok {blok_value} • Kamar {kamar_value}"
    if blok_value:
        return f"Blok {blok_value}"
    if kamar_value:
        return f"Kamar {kamar_value}"
    return "-"


def _build_user_manual_debt_payload(user: User, *, max_age_days: int | None = None) -> dict[str, object]:
    cutoff_datetime = None
    cutoff_date = None
    if max_age_days is not None and max_age_days > 0:
        cutoff_datetime = datetime.now(dt_timezone.utc) - timedelta(days=max_age_days)
        cutoff_date = cutoff_datetime.date()

    debts = db.session.scalars(
        select(UserQuotaDebt)
        .where(UserQuotaDebt.user_id == user.id)
        .order_by(
            UserQuotaDebt.debt_date.desc().nulls_last(),
            UserQuotaDebt.created_at.desc(),
        )
    ).all()

    ref_packages = db.session.scalars(
        select(Package)
        .where(Package.is_active == True, Package.data_quota_gb > 0)
        .order_by(Package.price.asc())
    ).all()

    def _pick_ref_pkg(amount_mb: int):
        for package in ref_packages:
            if float(package.data_quota_gb or 0) * 1024 >= amount_mb:
                return package
        return ref_packages[0] if ref_packages else None

    items: list[dict] = []
    open_count = 0
    paid_count = 0

    for debt in debts:
        if cutoff_datetime is not None and cutoff_date is not None:
            debt_date_value = getattr(debt, "debt_date", None)
            created_at_value = getattr(debt, "created_at", None)
            include_item = False

            if isinstance(debt_date_value, date):
                include_item = debt_date_value >= cutoff_date
            elif isinstance(created_at_value, datetime):
                normalized_created_at = created_at_value if created_at_value.tzinfo else created_at_value.replace(tzinfo=dt_timezone.utc)
                include_item = normalized_created_at >= cutoff_datetime

            if not include_item:
                continue

        amount = int(getattr(debt, "amount_mb", 0) or 0)
        paid_mb = int(getattr(debt, "paid_mb", 0) or 0)
        remaining = max(0, amount - paid_mb)
        is_paid = bool(getattr(debt, "is_paid", False)) or remaining <= 0
        if is_paid:
            paid_count += 1
        else:
            open_count += 1

        ref_pkg = _pick_ref_pkg(amount)
        estimate = estimate_debt_rp_from_cheapest_package(
            debt_mb=float(amount),
            cheapest_package_price_rp=int(ref_pkg.price) if ref_pkg else None,
            cheapest_package_quota_gb=float(ref_pkg.data_quota_gb) if ref_pkg else None,
            cheapest_package_name=str(ref_pkg.name) if ref_pkg else None,
        )

        payload = UserQuotaDebtItemResponseSchema.from_orm(debt).model_dump()
        payload["remaining_mb"] = int(remaining)
        payload["is_paid"] = bool(is_paid)
        payload["paid_mb"] = int(paid_mb)
        payload["amount_mb"] = int(amount)
        payload["estimated_rp"] = int(estimate.estimated_rp_rounded or 0)
        items.append(payload)

    return {
        "items": items,
        "summary": {
            "manual_debt_mb": int(getattr(user, "quota_debt_manual_mb", getattr(user, "manual_debt_mb", 0)) or 0),
            "open_items": int(open_count),
            "paid_items": int(paid_count),
            "total_items": int(len(items)),
        },
    }


def _build_detail_access_status_meta(user: User) -> dict[str, str]:
    status_key = str(get_user_access_status(user) or "inactive").strip().lower()

    if status_key == "blocked":
        return {
            "access_status_key": "blocked",
            "access_status_label": "Blokir",
            "access_status_hint": str(getattr(user, "blocked_reason", "") or "Akses login ditolak sampai blokir dibuka.").strip(),
            "access_status_tone": "error",
        }
    if status_key == "inactive":
        return {
            "access_status_key": "inactive",
            "access_status_label": "Inactive",
            "access_status_hint": "Akun tidak aktif atau belum disetujui.",
            "access_status_tone": "secondary",
        }
    if status_key == "unlimited":
        return {
            "access_status_key": "unlimited",
            "access_status_label": "Unlimited",
            "access_status_hint": "Pengguna memakai akses tanpa batas kuota selama masa aktif berlaku.",
            "access_status_tone": "success",
        }
    if status_key == "fup":
        return {
            "access_status_key": "fup",
            "access_status_label": "FUP",
            "access_status_hint": "Pengguna sudah masuk batas fair usage policy.",
            "access_status_tone": "info",
        }
    if status_key in {"expired", "habis"}:
        return {
            "access_status_key": status_key,
            "access_status_label": "Habis",
            "access_status_hint": "Masa aktif atau kuota aktif pengguna sudah habis.",
            "access_status_tone": "warning",
        }

    return {
        "access_status_key": "active",
        "access_status_label": "Aktif",
        "access_status_hint": "Layanan internet aktif dan masih dapat digunakan.",
        "access_status_tone": "success",
    }


def _serialize_detail_whatsapp_recipient(
    *,
    phone_number: str,
    user: User | None = None,
    full_name: str | None = None,
    role_label: str | None = None,
) -> dict:
    resolved_name = str(full_name or getattr(user, "full_name", "") or "Penerima").strip() or "Penerima"
    resolved_role = role_label or _format_detail_role_label(getattr(user, "role", None))
    return {
        "user_id": str(getattr(user, "id", "") or "") or None,
        "full_name": resolved_name,
        "role": resolved_role,
        "phone_number": phone_number,
    }


def _resolve_internal_detail_report_recipients(current_admin: User, recipient_user_ids: list) -> list[dict]:
    if not isinstance(recipient_user_ids, list) or len(recipient_user_ids) == 0:
        raise ValueError("Pilih minimal satu admin atau super admin penerima.")

    normalized_ids: list[uuid.UUID] = []
    seen_ids: set[uuid.UUID] = set()
    for raw_id in recipient_user_ids:
        try:
            user_id = uuid.UUID(str(raw_id))
        except (TypeError, ValueError):
            raise ValueError("Daftar admin penerima tidak valid.") from None
        if user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        normalized_ids.append(user_id)

    query = select(User).where(User.id.in_(normalized_ids)).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
    if not current_admin.is_super_admin_role:
        query = query.where(User.role != UserRole.SUPER_ADMIN)

    internal_users = db.session.scalars(query).all()
    internal_user_map = {internal_user.id: internal_user for internal_user in internal_users}
    if len(internal_user_map) != len(normalized_ids):
        raise ValueError("Sebagian admin penerima tidak ditemukan atau tidak bisa dipilih.")

    recipients: list[dict] = []
    for recipient_id in normalized_ids:
        internal_user = internal_user_map[recipient_id]
        raw_phone = str(getattr(internal_user, "phone_number", "") or "").strip()
        if not raw_phone:
            raise ValueError(f"Nomor WhatsApp untuk {internal_user.full_name} belum tersedia.")
        try:
            normalized_phone = normalize_to_e164(raw_phone)
        except Exception:
            raise ValueError(f"Nomor WhatsApp untuk {internal_user.full_name} tidak valid.") from None
        recipients.append(_serialize_detail_whatsapp_recipient(phone_number=normalized_phone, user=internal_user))
    return recipients


def _resolve_detail_report_whatsapp_targets(current_admin: User, user: User, payload: dict) -> tuple[str, list[dict]]:
    recipient_mode = str(payload.get("recipient_mode") or "").strip().lower()
    recipient_user_ids = payload.get("recipient_user_ids") or []
    raw_recipient_phone = str(payload.get("recipient_phone") or "").strip()

    if recipient_mode not in {"", "user", "internal"}:
        raise ValueError("Mode penerima WhatsApp tidak valid.")

    if recipient_mode == "internal" or (not recipient_mode and recipient_user_ids):
        return "internal", _resolve_internal_detail_report_recipients(current_admin, recipient_user_ids)

    raw_user_phone = str(getattr(user, "phone_number", "") or "").strip()
    resolved_phone_source = raw_recipient_phone or raw_user_phone
    if not resolved_phone_source:
        raise ValueError("Nomor WhatsApp pengguna belum tersedia.")

    try:
        normalized_phone = normalize_to_e164(resolved_phone_source)
    except Exception:
        raise ValueError("Nomor WhatsApp tujuan tidak valid.") from None

    if raw_recipient_phone and raw_user_phone and raw_recipient_phone != raw_user_phone:
        return "user", [
            _serialize_detail_whatsapp_recipient(
                phone_number=normalized_phone,
                full_name="Tujuan manual",
                role_label="Manual",
            )
        ]

    return "user", [_serialize_detail_whatsapp_recipient(phone_number=normalized_phone, user=user)]


def _default_profile_for_user(user: User) -> str:
    active_profile = str(settings_service.get_setting("MIKROTIK_PROFILE_ACTIVE", "default") or "default").strip()
    user_profile = str(settings_service.get_setting("MIKROTIK_PROFILE_USER", "user") or "user").strip()
    komandan_profile = str(settings_service.get_setting("MIKROTIK_PROFILE_KOMANDAN", "komandan") or "komandan").strip()
    inactive_profile = str(settings_service.get_setting("MIKROTIK_PROFILE_INACTIVE", "inactive") or "inactive").strip()
    unlimited_profile = str(settings_service.get_setting("MIKROTIK_PROFILE_UNLIMITED", "unlimited") or "unlimited").strip()

    if getattr(user, "is_active", False) is not True:
        return inactive_profile
    if getattr(user, "is_unlimited_user", False) is True:
        return unlimited_profile
    if getattr(user, "role", None) == UserRole.KOMANDAN:
        return komandan_profile or active_profile or user_profile
    return active_profile or user_profile


def _persist_mikrotik_snapshot(user: User, *, exists_on_mikrotik: bool, details: dict | None) -> None:
    changed = False
    if bool(getattr(user, "mikrotik_user_exists", False)) != bool(exists_on_mikrotik):
        user.mikrotik_user_exists = bool(exists_on_mikrotik)
        changed = True

    if exists_on_mikrotik and isinstance(details, dict):
        profile_name = str(details.get("profile") or "").strip()
        server_name = str(details.get("server") or "").strip()
        if profile_name and profile_name != str(getattr(user, "mikrotik_profile_name", "") or "").strip():
            user.mikrotik_profile_name = profile_name
            changed = True
        if server_name and server_name != str(getattr(user, "mikrotik_server_name", "") or "").strip():
            user.mikrotik_server_name = server_name
            changed = True

    if changed:
        db.session.commit()


def _get_user_mikrotik_status_payload(user: User) -> dict:
    mikrotik_username = format_to_local_phone(user.phone_number)
    purchased_mb = float(user.total_quota_purchased_mb or 0)
    used_mb = float(user.total_quota_used_mb or 0)
    remaining_mb = max(0.0, purchased_mb - used_mb)
    database_profile_name = str(getattr(user, "mikrotik_profile_name", "") or "").strip()
    derived_profile_name = _default_profile_for_user(user)

    db_quota = {
        "db_quota_purchased_mb": purchased_mb,
        "db_quota_used_mb": used_mb,
        "db_quota_remaining_mb": remaining_mb,
        "database_profile_name": database_profile_name or None,
        "derived_profile_name": derived_profile_name,
    }

    if not mikrotik_username:
        return {
            "user_id": str(user.id),
            "exists_on_mikrotik": bool(user.mikrotik_user_exists),
            "details": None,
            "live_available": False,
            "message": "Format nomor telepon pengguna belum valid untuk pengecekan live.",
            "reason": "invalid_phone_format",
            "resolved_profile_name": database_profile_name or derived_profile_name,
            **db_quota,
        }

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
            user.id,
            mikrotik_message,
        )
        return {
            "user_id": str(user.id),
            "exists_on_mikrotik": bool(user.mikrotik_user_exists),
            "details": None,
            "live_available": False,
            "message": "Live check MikroTik tidak tersedia. Menampilkan data sinkron terakhir dari database.",
            "reason": mikrotik_message,
            "resolved_profile_name": database_profile_name or derived_profile_name,
            **db_quota,
        }

    user_exists = isinstance(details, dict) and bool(details)
    _persist_mikrotik_snapshot(user, exists_on_mikrotik=user_exists, details=details if isinstance(details, dict) else None)

    resolved_profile_name = str((details or {}).get("profile") or "").strip() or database_profile_name or derived_profile_name
    return {
        "user_id": str(user.id),
        "exists_on_mikrotik": user_exists,
        "details": details if isinstance(details, dict) else None,
        "live_available": True,
        "message": "Data live MikroTik berhasil dimuat." if user_exists else "Pengguna tidak ditemukan di MikroTik.",
        "resolved_profile_name": resolved_profile_name,
        **db_quota,
    }


def _build_user_detail_report_context(
    user: User,
    *,
    mikrotik_status: dict | None = None,
    debt_max_age_days: int | None = None,
    purchase_window_days: int | None = 365,
) -> dict:
    status_payload = mikrotik_status or _get_user_mikrotik_status_payload(user)
    live_available = bool(status_payload.get("live_available"))
    exists_on_mikrotik = bool(status_payload.get("exists_on_mikrotik"))
    profile_display_name = _humanize_detail_profile_name(
        user,
        str(status_payload.get("resolved_profile_name") or _default_profile_for_user(user)).strip(),
    )
    profile_source = "Live MikroTik" if live_available and exists_on_mikrotik else ("Sinkron terakhir" if getattr(user, "mikrotik_profile_name", None) else "Standar sistem")

    if live_available and exists_on_mikrotik:
        mikrotik_account_label = "Sinkron live"
        mikrotik_account_hint = "Akun hotspot terbaca langsung dari MikroTik."
    elif live_available and not exists_on_mikrotik:
        mikrotik_account_label = "Tidak ada di MikroTik"
        mikrotik_account_hint = "Live check tidak menemukan akun hotspot pengguna ini."
    elif bool(getattr(user, "mikrotik_user_exists", False)):
        mikrotik_account_label = "Sinkron tersimpan"
        mikrotik_account_hint = "Panel memakai data sinkron terakhir dari database."
    else:
        mikrotik_account_label = "Perlu cek live"
        mikrotik_account_hint = "Jalankan cek live untuk memastikan akun hotspot."

    remaining_mb = max(0.0, float(getattr(user, "total_quota_purchased_mb", 0) or 0) - float(getattr(user, "total_quota_used_mb", 0) or 0))
    debt_auto_mb = float(getattr(user, "quota_debt_auto_mb", 0) or 0)
    debt_manual_mb = int(getattr(user, "quota_debt_manual_mb", getattr(user, "manual_debt_mb", 0)) or 0)
    debt_total_mb = float(getattr(user, "quota_debt_total_mb", debt_auto_mb + debt_manual_mb) or 0)
    manual_debt_payload = _build_user_manual_debt_payload(user, max_age_days=debt_max_age_days)
    manual_debt_items_value = manual_debt_payload.get("items")
    manual_debt_summary_value = manual_debt_payload.get("summary")
    manual_debt_items = manual_debt_items_value if isinstance(manual_debt_items_value, list) else []
    manual_debt_summary = manual_debt_summary_value if isinstance(manual_debt_summary_value, dict) else {}
    open_debt_items = int(manual_debt_summary.get("open_items") or 0)
    paid_debt_items = int(manual_debt_summary.get("paid_items") or 0)
    total_manual_debt_items = int(manual_debt_summary.get("total_items") or 0)

    purchase_stmt = (
        select(Transaction)
        .where(Transaction.user_id == user.id, Transaction.status == TransactionStatus.SUCCESS)
        .order_by(sa.func.coalesce(Transaction.payment_time, Transaction.created_at).desc())
        .limit(24)
    )
    if purchase_window_days is not None and purchase_window_days > 0:
        cutoff = datetime.now(dt_timezone.utc) - timedelta(days=purchase_window_days)
        purchase_stmt = purchase_stmt.where(sa.func.coalesce(Transaction.payment_time, Transaction.created_at) >= cutoff)
    purchase_rows = db.session.scalars(purchase_stmt).all()

    recent_purchases: list[dict] = []
    recent_purchase_total_amount = 0
    for tx in purchase_rows:
        paid_at = getattr(tx, "payment_time", None) or getattr(tx, "created_at", None)
        recent_purchase_total_amount += int(getattr(tx, "amount", 0) or 0)
        recent_purchases.append(
            {
                "order_id": str(getattr(tx, "midtrans_order_id", "") or "-").strip() or "-",
                "package_name": str(getattr(getattr(tx, "package", None), "name", "") or "Paket tidak diketahui").strip() or "Paket tidak diketahui",
                "amount": int(getattr(tx, "amount", 0) or 0),
                "amount_display": _format_currency_idr(getattr(tx, "amount", 0) or 0),
                "payment_method": str(getattr(tx, "payment_method", "") or "-").strip() or "-",
                "paid_at": paid_at.isoformat() if paid_at else None,
                "paid_at_display": format_app_datetime_display(paid_at, fallback="-"),
            }
        )

    access_status_meta = _build_detail_access_status_meta(user)

    debt_breakdown_rows: list[dict[str, object]] = []
    if debt_auto_mb > 0:
        debt_breakdown_rows.append(
            {
                "kind": "Otomatis",
                "amount_mb": debt_auto_mb,
                "amount_display": format_mb_to_gb(debt_auto_mb),
                "status_label": "Belum lunas",
                "status_tone": "warning",
                "detail": "Selisih pemakaian terhadap kuota tercatat pada sistem.",
            }
        )
    if total_manual_debt_items > 0 or debt_manual_mb > 0:
        debt_breakdown_rows.append(
            {
                "kind": "Manual",
                "amount_mb": debt_manual_mb,
                "amount_display": format_mb_to_gb(debt_manual_mb),
                "status_label": (
                    f"{open_debt_items} belum lunas / {paid_debt_items} lunas"
                    if total_manual_debt_items > 0
                    else ("Belum lunas" if debt_manual_mb > 0 else "Lunas")
                ),
                "status_tone": "warning" if open_debt_items > 0 or debt_manual_mb > 0 else "success",
                "detail": "Catatan admin per item, termasuk entri yang sudah lunas.",
            }
        )

    last_login_label = format_app_datetime_display(getattr(user, "last_login_at", None), fallback="Belum ada login")
    device_count = int(getattr(user, "device_count", 0) or 0)
    debt_summary_line = (
        f"- Tunggakan aktif: *{format_mb_to_gb(debt_total_mb)}* ({int(open_debt_items)} item)"
        if debt_total_mb > 0
        else ""
    )
    recent_purchase_summary_line = (
        f"- Pembelian 30 hari: *{len(recent_purchases)} transaksi* • *{_format_currency_idr(recent_purchase_total_amount)}*"
        if recent_purchases
        else ""
    )
    address_display = _format_detail_address_label(user)

    business_context = build_receipt_business_identity_context()
    return {
        "user": user,
        "generated_at": format_app_datetime_display(datetime.now(dt_timezone.utc), fallback="-"),
        "printed_at": format_app_datetime_display(datetime.now(dt_timezone.utc), fallback="-"),
        "user_phone_display": format_to_local_phone(getattr(user, "phone_number", None)) or str(getattr(user, "phone_number", "") or "-"),
        "user_role_label": _format_detail_role_label(getattr(user, "role", None)),
        "address_display": address_display,
        "profile_display_name": profile_display_name,
        "profile_source": profile_source,
        "mikrotik_account_label": mikrotik_account_label,
        "mikrotik_account_hint": mikrotik_account_hint,
        "live_available": live_available,
        "exists_on_mikrotik": exists_on_mikrotik,
        "access_status_key": access_status_meta["access_status_key"],
        "access_status_label": access_status_meta["access_status_label"],
        "access_status_hint": access_status_meta["access_status_hint"],
        "access_status_tone": access_status_meta["access_status_tone"],
        "device_count": device_count,
        "device_count_label": f"{device_count} perangkat aktif" if device_count > 0 else "Belum ada perangkat",
        "last_login_label": last_login_label,
        "quota_total_mb": float(getattr(user, "total_quota_purchased_mb", 0) or 0),
        "quota_used_mb": float(getattr(user, "total_quota_used_mb", 0) or 0),
        "quota_remaining_mb": remaining_mb,
        "quota_expiry_label": format_app_datetime_display(getattr(user, "quota_expiry_date", None), fallback="Belum diatur"),
        "is_unlimited_user": bool(getattr(user, "is_unlimited_user", False)),
        "debt_auto_mb": debt_auto_mb,
        "debt_manual_mb": debt_manual_mb,
        "debt_total_mb": debt_total_mb,
        "open_debt_items": int(open_debt_items),
        "paid_debt_items": int(paid_debt_items),
        "manual_debt_items": manual_debt_items,
        "manual_debt_summary": manual_debt_summary,
        "debt_breakdown_rows": debt_breakdown_rows,
        "show_debt_section": debt_total_mb > 0 or total_manual_debt_items > 0,
        "show_manual_debt_table": total_manual_debt_items > 0,
        "recent_purchases": recent_purchases,
        "purchase_count_30d": len(recent_purchases),
        "purchase_total_amount_30d": recent_purchase_total_amount,
        "purchase_total_amount_30d_display": _format_currency_idr(recent_purchase_total_amount),
        "show_purchase_section": len(recent_purchases) > 0,
        "debt_summary_line": debt_summary_line,
        "recent_purchase_summary_line": recent_purchase_summary_line,
        "admin_whatsapp_default": _resolve_admin_whatsapp_default(),
        **business_context,
    }


def _render_user_detail_report_pdf_bytes(context: dict, public_base_url: str) -> bytes:
    from weasyprint import HTML  # type: ignore

    html_string = render_template("admin_user_detail_report.html", **context)
    pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
    if pdf_bytes is None:
        raise RuntimeError("Gagal menghasilkan PDF detail pengguna.")
    return pdf_bytes


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
    raw_data = request.get_json(silent=True)
    if not raw_data:
        return jsonify({"message": "Request data kosong."}), HTTPStatus.BAD_REQUEST
    try:
        validated_data = UserUpdateByAdminSchema.model_validate(raw_data)
        data = validated_data.model_dump(exclude_unset=True)
        success, message, updated_user = user_profile_service.update_user_by_admin_comprehensive(
            user, current_admin, data
        )
        if not success:
            db.session.rollback()
            return jsonify({"message": message}), HTTPStatus.BAD_REQUEST
        db.session.commit()
        response_user_id = getattr(updated_user, "id", None) or user_id
        response_user = db.session.get(User, response_user_id)
        if response_user is None:
            current_app.logger.error("Updated user %s tidak ditemukan setelah commit.", response_user_id)
            return jsonify({"message": "Kesalahan internal server."}), HTTPStatus.INTERNAL_SERVER_ERROR
        return jsonify(UserResponseSchema.from_orm(response_user).model_dump()), HTTPStatus.OK
    except ValidationError as e:
        db.session.rollback()
        return jsonify({"message": "Data tidak valid.", "errors": e.errors()}), HTTPStatus.BAD_REQUEST
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
        payload = _build_user_manual_debt_payload(user)
        return jsonify(payload), HTTPStatus.OK
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
        # Snapshot untuk notifikasi dan auto-unblock
        debt_manual_before = int(getattr(user, "quota_debt_manual_mb", 0) or 0)
        was_blocked = bool(getattr(user, "is_blocked", False))
        blocked_reason = str(getattr(user, "blocked_reason", "") or "")

        paid_mb = user_debt_service.settle_manual_debt_item_to_zero(
            user=user,
            admin_actor=current_admin,
            debt=debt,
            source="admin_settle_item",
        )

        # Auto-unblock jika semua tunggakan (auto + manual) sudah nol dan user diblokir karena debt.
        unblocked = False
        if paid_mb > 0 and was_blocked and is_debt_block_reason(blocked_reason):
            if float(getattr(user, "quota_debt_total_mb", 0) or 0) <= 0:
                user.is_blocked = False
                user.blocked_reason = None
                user.blocked_at = None
                user.blocked_by_id = None
                unblocked = True

        db.session.commit()

        receipt_url = None
        receipt_context = None
        try:
            receipt_entry = get_latest_admin_debt_settlement_mutation(user.id, ADMIN_SETTLE_SINGLE_SOURCE)
            if receipt_entry is not None:
                base_url = _resolve_public_base_url()
                if base_url:
                    receipt_url = _build_debt_settlement_receipt_url(receipt_entry.id, base_url)
                receipt_context = build_debt_settlement_receipt_context(user=user, settlement_entry=receipt_entry)
        except Exception as receipt_err:
            current_app.logger.warning(
                "Gagal menyiapkan receipt pelunasan partial debt user %s: %s",
                user.id,
                receipt_err,
            )

        # Notify user via WhatsApp (best-effort)
        try:
            if paid_mb > 0:
                remaining_manual_debt = max(0, debt_manual_before - int(paid_mb))
                purchased_now = float(getattr(user, "total_quota_purchased_mb", 0) or 0)
                used_now = float(getattr(user, "total_quota_used_mb", 0) or 0)
                remaining_quota_mb = max(0.0, purchased_now - used_now)
                quota_expiry = getattr(user, "quota_expiry_date", None)

                # Format expiry_date dengan fallback untuk NULL value
                if quota_expiry:
                    try:
                        expiry_date_str = format_app_date_display(quota_expiry, fallback="Belum ditentukan")
                    except Exception:
                        expiry_date_str = "Belum ditentukan"
                else:
                    expiry_date_str = "Belum ditentukan"

                # Format debt_date dan paid_at dengan zona waktu aplikasi
                debt_date_str = format_app_date_display(debt.debt_date, fallback="–")
                paid_at_str = (
                    format_app_datetime_display(debt.paid_at, fallback=format_app_datetime()) if debt.paid_at else format_app_datetime()
                )

                wa_template = "user_debt_partial_payment_unblock" if unblocked else "user_debt_partial_payment"
                _send_whatsapp_notification(
                    user.phone_number,
                    wa_template,
                    {
                        "full_name": user.full_name,
                        "debt_date": debt_date_str,
                        "paid_at": paid_at_str,
                        "paid_manual_debt_gb": format_mb_to_gb(paid_mb),
                        "paid_manual_debt_amount_display": (
                            receipt_context.get("paid_manual_amount_display") if receipt_context else format_currency_idr(estimate_amount_rp_for_mb(paid_mb))
                        ),
                        "paid_total_debt_gb": receipt_context.get("paid_total_gb") if receipt_context else format_mb_to_gb(paid_mb),
                        "paid_total_debt_amount_display": (
                            receipt_context.get("paid_total_amount_display") if receipt_context else format_currency_idr(estimate_amount_rp_for_mb(paid_mb))
                        ),
                        "payment_channel_label": "Pelunasan manual oleh Admin",
                        "remaining_manual_debt_gb": format_mb_to_gb(remaining_manual_debt),
                        "remaining_quota_gb": format_mb_to_gb(remaining_quota_mb),
                        "expiry_date": expiry_date_str,
                        "receipt_url": receipt_url or "-",
                    },
                )
        except Exception as e:
            current_app.logger.warning(
                "Gagal mengirim notifikasi pembayaran partial debt user %s: %s", user.id, e
            )

        return jsonify({
            "message": "Debt berhasil dilunasi.",
            "paid_mb": int(paid_mb),
            "unblocked": bool(unblocked),
            "receipt_url": receipt_url,
        }), HTTPStatus.OK
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

        receipt_url = None
        receipt_context = None
        try:
            receipt_entry = get_latest_admin_debt_settlement_mutation(user.id, ADMIN_SETTLE_ALL_SOURCE)
            if receipt_entry is not None:
                base_url = _resolve_public_base_url()
                if base_url:
                    receipt_url = _build_debt_settlement_receipt_url(receipt_entry.id, base_url)
                receipt_context = build_debt_settlement_receipt_context(user=user, settlement_entry=receipt_entry)
        except Exception as receipt_err:
            current_app.logger.warning(
                "Gagal menyiapkan receipt pelunasan semua debt user %s: %s",
                user.id,
                receipt_err,
            )

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
                        "paid_auto_debt_gb": format_mb_to_gb(paid_auto_mb),
                        "paid_manual_debt_gb": format_mb_to_gb(paid_manual_mb),
                        "paid_total_debt_gb": format_mb_to_gb(paid_total_mb),
                        "paid_total_debt_amount_display": (
                            receipt_context.get("paid_total_amount_display") if receipt_context else format_currency_idr(estimate_amount_rp_for_mb(paid_total_mb))
                        ),
                        "payment_channel_label": "Pelunasan manual oleh Admin",
                        "remaining_quota": format_mb_to_gb(remaining_mb),
                        "receipt_url": receipt_url or "-",
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
                "receipt_url": receipt_url,
            }
        ), HTTPStatus.OK
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error settling all debts for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal melunasi tunggakan."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/mikrotik/verify-rules", methods=["GET"])
@admin_required
def verify_mikrotik_rules(current_admin: User):
    """Verifikasi rule firewall kritis di MikroTik.

    Memeriksa rule pada tabel yang sesuai dengan arsitektur hotspot aktual:
    - /ip/firewall/raw  → prerouting drop klient_inactive (src & dst)
    - /ip/firewall/filter → hs-unauth return klient_aktif, klient_fup (src)
    """
    # _table: tabel RouterOS yang akan diquery ("raw" atau "filter")
    # Sisa key adalah field yang harus cocok pada rule (semua harus ada & sama).
    EXPECTED_RULES: list[dict] = [
        {"_table": "raw",    "chain": "prerouting", "action": "drop",   "src-address-list": "klient_inactive"},
        {"_table": "raw",    "chain": "prerouting", "action": "drop",   "dst-address-list": "klient_inactive"},
        {"_table": "filter", "chain": "hs-unauth",  "action": "return", "src-address-list": "klient_aktif"},
        {"_table": "filter", "chain": "hs-unauth",  "action": "return", "src-address-list": "klient_fup"},
    ]

    filter_rules: list[dict] | None = None
    raw_rules: list[dict] | None = None
    try:
        with get_mikrotik_connection(raise_on_error=True) as api_conn:
            if not api_conn:
                return jsonify({"status": "error", "message": "Koneksi MikroTik tidak tersedia."}), HTTPStatus.SERVICE_UNAVAILABLE
            filter_rules = api_conn.get_resource("/ip/firewall/filter").get()
            raw_rules = api_conn.get_resource("/ip/firewall/raw").get()
    except Exception as e:
        current_app.logger.error("Gagal mengambil firewall rules dari MikroTik: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": f"Gagal koneksi MikroTik: {str(e)}"}), HTTPStatus.SERVICE_UNAVAILABLE

    if filter_rules is None or raw_rules is None:
        return jsonify({"status": "error", "message": "Gagal membaca firewall rules dari MikroTik."}), HTTPStatus.SERVICE_UNAVAILABLE

    rules_by_table: dict[str, list[dict]] = {
        "filter": [r for r in filter_rules if r.get("disabled", "false") != "true"],
        "raw":    [r for r in raw_rules    if r.get("disabled", "false") != "true"],
    }

    def _matches(actual: dict, expected: dict) -> bool:
        return all(actual.get(k, "") == v for k, v in expected.items() if not k.startswith("_"))

    checks = []
    for expected in EXPECTED_RULES:
        table = expected["_table"]
        pool = rules_by_table.get(table, [])
        chain = expected.get("chain", "")
        action = expected.get("action", "")
        src = expected.get("src-address-list", "")
        dst = expected.get("dst-address-list", "")
        label = f"{table}/{chain} {action} src={src} dst={dst}".strip()
        found = any(_matches(r, expected) for r in pool)
        checks.append({"label": label, "found": found})

    all_found = all(c["found"] for c in checks)
    active_filter_count = len(rules_by_table["filter"])
    active_raw_count = len(rules_by_table["raw"])

    return jsonify({
        "status": "ok" if all_found else "error",
        "all_found": all_found,
        "total_filter_rules": active_filter_count,
        "total_raw_rules": active_raw_count,
        "checks": checks,
    }), HTTPStatus.OK


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
        __import__("weasyprint")
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        context = _build_user_manual_debt_report_context(user)
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        pdf_bytes = _render_user_manual_debts_pdf_bytes(context, public_base_url)
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


@user_management_bp.route("/users/debts/temp/<string:token>", methods=["GET"])
@user_management_bp.route("/users/debts/temp/<string:token>.pdf", methods=["GET"])
def export_user_manual_debts_pdf_temp(token: str):
    user_id = verify_temp_debt_report_token(token, max_age_seconds=3600)
    if not user_id:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Laporan Sudah Kedaluwarsa",
            message="Minta admin mengirim ulang tautan laporan tunggakan ini agar Anda bisa membuka versi terbaru.",
            document_label="Laporan tunggakan",
            badge="Tautan sementara berakhir",
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError):
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Laporan Tidak Valid",
            message="Periksa kembali tautan yang dibuka atau minta admin mengirim ulang dokumen ini.",
            document_label="Laporan tunggakan",
            badge="Token tidak valid",
        )

    user = db.session.get(User, user_uuid)
    if not user:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.NOT_FOUND,
            title="Dokumen Tidak Ditemukan",
            message="Data pengguna untuk laporan ini sudah tidak tersedia di sistem.",
            document_label="Laporan tunggakan",
            badge="Data tidak ditemukan",
        )

    try:
        __import__("weasyprint")
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        context = _build_user_manual_debt_report_context(user)
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        pdf_bytes = _render_user_manual_debts_pdf_bytes(context, public_base_url)
        if not pdf_bytes:
            return jsonify({"message": "Gagal menghasilkan file PDF."}), HTTPStatus.INTERNAL_SERVER_ERROR

        safe_phone = (getattr(user, "phone_number", "") or "").replace("+", "")
        filename = f"debt-{safe_phone or user.id}-ledger.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error(f"Error export temp debt PDF for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/debt-settlements/temp/<string:token>", methods=["GET"])
@user_management_bp.route("/users/debt-settlements/temp/<string:token>.pdf", methods=["GET"])
def export_debt_settlement_receipt_temp(token: str):
    entry_id = verify_temp_debt_settlement_receipt_token(token, max_age_seconds=3600)
    if not entry_id:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Receipt Sudah Kedaluwarsa",
            message="Minta admin mengirim ulang receipt pelunasan ini agar Anda mendapat tautan yang masih aktif.",
            document_label="Receipt pelunasan",
            badge="Tautan sementara berakhir",
        )

    try:
        entry_uuid = uuid.UUID(entry_id)
    except (TypeError, ValueError):
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Receipt Tidak Valid",
            message="Tautan receipt ini tidak bisa diverifikasi. Minta admin mengirim ulang dokumen baru.",
            document_label="Receipt pelunasan",
            badge="Token tidak valid",
        )

    entry = db.session.get(QuotaMutationLedger, entry_uuid)
    if not entry:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.NOT_FOUND,
            title="Receipt Tidak Ditemukan",
            message="Receipt pelunasan yang Anda buka sudah tidak tersedia di sistem.",
            document_label="Receipt pelunasan",
            badge="Data tidak ditemukan",
        )

    user = db.session.get(User, getattr(entry, "user_id", None))
    if not user:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.NOT_FOUND,
            title="Dokumen Tidak Ditemukan",
            message="Data pengguna untuk receipt ini sudah tidak tersedia di sistem.",
            document_label="Receipt pelunasan",
            badge="Data tidak ditemukan",
        )

    try:
        __import__("weasyprint")
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    transaction = None
    order_id = str((getattr(entry, "event_details", None) or {}).get("order_id") or "").strip()
    if order_id:
        transaction = db.session.execute(select(Transaction).where(Transaction.midtrans_order_id == order_id)).scalar_one_or_none()

    try:
        context = build_debt_settlement_receipt_context(user=user, settlement_entry=entry, transaction=transaction)
        context.update(build_receipt_business_identity_context())
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        pdf_bytes = _render_debt_settlement_receipt_pdf_bytes(context, public_base_url)
        filename = f"receipt-{context.get('receipt_number') or entry.id}.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error(f"Error export debt settlement receipt {entry_id}: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/debts/send-whatsapp", methods=["POST"])
@admin_required
def send_user_manual_debts_whatsapp(current_admin: User, user_id: uuid.UUID):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response
    if not getattr(user, "phone_number", None):
        return jsonify({"message": "Nomor WhatsApp pengguna tidak tersedia."}), HTTPStatus.BAD_REQUEST

    try:
        report_context = _build_user_manual_debt_report_context(user)
        open_items = [item for item in report_context.get("items", []) if not bool(item.get("is_paid"))]
        if not open_items:
            return jsonify({"message": "Tidak ada tunggakan manual yang masih terbuka untuk dikirimkan."}), HTTPStatus.BAD_REQUEST

        base_url = _resolve_public_base_url()
        if not base_url:
            return jsonify({"message": "Konfigurasi alamat publik aplikasi tidak ditemukan."}), HTTPStatus.SERVICE_UNAVAILABLE

        temp_token = generate_temp_debt_report_token(str(user.id))
        pdf_url = f"{base_url.rstrip('/')}/api/admin/users/debts/temp/{temp_token}.pdf"
        wa_context = _build_user_debt_whatsapp_context(user, report_context, pdf_url)
        caption_message = get_notification_message("user_debt_report_with_pdf", wa_context)
        filename = f"debt-{(getattr(user, 'phone_number', '') or str(user.id)).replace('+', '')}-ledger.pdf"
        request_id = request.environ.get("FLASK_REQUEST_ID", "")
        send_whatsapp_invoice_task.delay(
            str(user.phone_number),
            caption_message,
            pdf_url,
            filename,
            request_id,
            None,
            "debt_report",
        )
        current_app.logger.info(
            "ADMIN_DEBT_WA: WA debt report queued for user=%s phone=%s admin=%s",
            user.id,
            user.phone_number,
            current_admin.id,
        )
        return jsonify({"message": "Ringkasan tunggakan berhasil diantrikan ke WhatsApp.", "queued": True}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error queue debt WhatsApp report for user {user_id}: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengantrekan WhatsApp tunggakan."}), HTTPStatus.INTERNAL_SERVER_ERROR


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
        generated_local = format_app_datetime_display(datetime.now(dt_timezone.utc), include_seconds=False)
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
        return jsonify(_get_user_mikrotik_status_payload(user)), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(
            f"Kesalahan tak terduga di endpoint mikrotik-status untuk user {user_id}: {e}", exc_info=True
        )
        return jsonify(
            {"message": "Terjadi kesalahan internal tak terduga pada server."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/detail-summary", methods=["GET"])
@admin_required
def get_user_detail_summary(current_admin: User, user_id: uuid.UUID):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    try:
        status_payload = _get_user_mikrotik_status_payload(user)
        report_context = _build_user_detail_report_context(
            user,
            mikrotik_status=status_payload,
            debt_max_age_days=None,
            purchase_window_days=365,
        )
        return jsonify(
            {
                "mikrotik": {
                    "live_available": bool(status_payload.get("live_available")),
                    "exists_on_mikrotik": bool(status_payload.get("exists_on_mikrotik")),
                    "message": status_payload.get("message"),
                    "reason": status_payload.get("reason"),
                },
                "profile_display_name": report_context["profile_display_name"],
                "profile_source": report_context["profile_source"],
                "mikrotik_account_label": report_context["mikrotik_account_label"],
                "mikrotik_account_hint": report_context["mikrotik_account_hint"],
                "access_status_label": report_context["access_status_label"],
                "access_status_hint": report_context["access_status_hint"],
                "access_status_tone": report_context["access_status_tone"],
                "device_count": report_context["device_count"],
                "device_count_label": report_context["device_count_label"],
                "last_login_label": report_context["last_login_label"],
                "debt": {
                    "auto_mb": report_context["debt_auto_mb"],
                    "manual_mb": report_context["debt_manual_mb"],
                    "total_mb": report_context["debt_total_mb"],
                    "open_items": report_context["open_debt_items"],
                },
                "recent_purchases": report_context["recent_purchases"],
                "purchase_count_30d": report_context["purchase_count_30d"],
                "purchase_total_amount_30d": report_context["purchase_total_amount_30d"],
                "purchase_total_amount_30d_display": report_context["purchase_total_amount_30d_display"],
                "admin_whatsapp_default": report_context["admin_whatsapp_default"],
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error("Error getting detail summary for user %s: %s", user_id, e, exc_info=True)
        return jsonify({"message": "Gagal memuat ringkasan pengguna."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/detail-report/export", methods=["GET"])
@admin_required
def export_user_detail_report_pdf(current_admin: User, user_id: uuid.UUID):
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
        __import__("weasyprint")
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        status_payload = _get_user_mikrotik_status_payload(user)
        context = _build_user_detail_report_context(
            user,
            mikrotik_status=status_payload,
            debt_max_age_days=30,
            purchase_window_days=30,
        )
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        pdf_bytes = _render_user_detail_report_pdf_bytes(context, public_base_url)
        safe_phone = (getattr(user, "phone_number", "") or "").replace("+", "")
        filename = f"user-detail-{safe_phone or user.id}.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error("Error export detail PDF for user %s: %s", user_id, e, exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/detail-report/temp/<string:token>", methods=["GET"])
@user_management_bp.route("/users/detail-report/temp/<string:token>.pdf", methods=["GET"])
def export_user_detail_report_pdf_temp(token: str):
    user_id = verify_temp_user_detail_report_token(token, max_age_seconds=3600)
    if not user_id:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Laporan Sudah Kedaluwarsa",
            message="Link laporan detail ini bersifat sementara. Minta admin mengirim ulang tautan baru agar Anda bisa membuka PDF terbaru.",
            document_label="Laporan detail pengguna",
            badge="Tautan sementara berakhir",
        )

    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError):
        return _render_temp_document_error_page(
            status_code=HTTPStatus.FORBIDDEN,
            title="Tautan Laporan Tidak Valid",
            message="Tautan yang dibuka tidak bisa diverifikasi. Periksa kembali atau minta admin mengirim ulang dokumen ini.",
            document_label="Laporan detail pengguna",
            badge="Token tidak valid",
        )

    user = db.session.get(User, user_uuid)
    if not user:
        return _render_temp_document_error_page(
            status_code=HTTPStatus.NOT_FOUND,
            title="Dokumen Tidak Ditemukan",
            message="Data pengguna untuk laporan ini sudah tidak tersedia di sistem.",
            document_label="Laporan detail pengguna",
            badge="Data tidak ditemukan",
        )

    try:
        __import__("weasyprint")
    except Exception:
        return jsonify({"message": "Komponen PDF server tidak tersedia."}), HTTPStatus.NOT_IMPLEMENTED

    try:
        status_payload = _get_user_mikrotik_status_payload(user)
        context = _build_user_detail_report_context(
            user,
            mikrotik_status=status_payload,
            debt_max_age_days=30,
            purchase_window_days=30,
        )
        public_base_url = current_app.config.get("APP_PUBLIC_BASE_URL", request.url_root)
        pdf_bytes = _render_user_detail_report_pdf_bytes(context, public_base_url)
        safe_phone = (getattr(user, "phone_number", "") or "").replace("+", "")
        filename = f"user-detail-{safe_phone or user.id}.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'inline; filename="{filename}"'
        return resp
    except Exception as e:
        current_app.logger.error("Error export temp detail PDF for user %s: %s", user_id, e, exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal."}), HTTPStatus.INTERNAL_SERVER_ERROR


@user_management_bp.route("/users/<uuid:user_id>/detail-report/send-whatsapp", methods=["POST"])
@admin_required
def send_user_detail_report_whatsapp(current_admin: User, user_id: uuid.UUID):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"message": "Pengguna tidak ditemukan."}), HTTPStatus.NOT_FOUND
    denied_response = _deny_non_super_admin_target_access(current_admin, user)
    if denied_response:
        return denied_response

    payload = request.get_json(silent=True) or {}
    try:
        recipient_mode, recipients = _resolve_detail_report_whatsapp_targets(current_admin, user, payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST

    try:
        status_payload = _get_user_mikrotik_status_payload(user)
        report_context = _build_user_detail_report_context(
            user,
            mikrotik_status=status_payload,
            debt_max_age_days=30,
            purchase_window_days=30,
        )

        base_url = _resolve_public_base_url()
        if not base_url:
            return jsonify({"message": "Konfigurasi alamat publik aplikasi tidak ditemukan."}), HTTPStatus.SERVICE_UNAVAILABLE

        temp_token = generate_temp_user_detail_report_token(str(user.id))
        pdf_url = f"{base_url.rstrip('/')}/api/admin/users/detail-report/temp/{temp_token}.pdf"
        wa_context = {
            "full_name": user.full_name,
            "access_status_label": report_context["access_status_label"],
            "mikrotik_account_label": report_context["mikrotik_account_label"],
            "profile_display_name": report_context["profile_display_name"],
            "device_count_label": report_context["device_count_label"],
            "last_login_label": report_context["last_login_label"],
            "debt_summary_line": report_context["debt_summary_line"] or "",
            "recent_purchase_summary_line": report_context["recent_purchase_summary_line"] or "",
            "detail_pdf_url": pdf_url,
        }
        caption_message = get_notification_message("user_detail_report_with_pdf", wa_context)
        filename = f"user-detail-{(getattr(user, 'phone_number', '') or str(user.id)).replace('+', '')}.pdf"
        request_id = request.environ.get("FLASK_REQUEST_ID", "")
        for recipient in recipients:
            send_whatsapp_invoice_task.delay(
                recipient["phone_number"],
                caption_message,
                pdf_url,
                filename,
                request_id,
                None,
                "detail_report",
            )
        current_app.logger.info(
            "ADMIN_USER_DETAIL_WA: detail report queued for user=%s recipients=%s mode=%s admin=%s",
            user.id,
            [recipient["phone_number"] for recipient in recipients],
            recipient_mode,
            current_admin.id,
        )
        recipient_total = len(recipients)
        if recipient_mode == "internal":
            message = f"Laporan detail pengguna berhasil diantrikan ke {recipient_total} admin penerima."
        else:
            message = "Laporan detail pengguna berhasil diantrikan ke WhatsApp pengguna."
        return jsonify(
            {
                "message": message,
                "queued": True,
                "queued_count": recipient_total,
                "recipient_mode": recipient_mode,
                "recipients": recipients,
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error("Error queue detail WhatsApp report for user %s: %s", user_id, e, exc_info=True)
        return jsonify({"message": "Gagal mengantrekan laporan detail ke WhatsApp."}), HTTPStatus.INTERNAL_SERVER_ERROR


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
