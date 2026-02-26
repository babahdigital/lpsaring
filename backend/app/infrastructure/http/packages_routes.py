# backend/app/infrastructure/http/packages_routes.py
# VERSI: Disesuaikan dengan nama field baru di model dan skema paket.
# PERBAIKAN: Mengatasi RuntimeError dan memastikan pemuatan Package.profile.
# PERBAIKAN FINAL: Menambahkan import HTTPStatus untuk mengatasi NameError.

from flask import Blueprint, jsonify, current_app, request
from sqlalchemy.orm import selectinload  # Import selectinload
from http import HTTPStatus  # <--- PERBAIKAN DI SINI
import uuid
from jose import jwt

from app.extensions import db
from app.infrastructure.db.models import Package as PackageModel, User
from .schemas.package_schemas import PackagePublic
from app.utils.formatters import get_phone_number_variations, normalize_to_e164


packages_bp = Blueprint("packages_api", __name__, url_prefix="/api/packages")


def _normalize_phone_digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _is_demo_user_eligible(user: User | None) -> bool:
    if user is None:
        return False

    if not bool(current_app.config.get("DEMO_MODE_ENABLED", False)):
        return False

    allowed_raw = current_app.config.get("DEMO_ALLOWED_PHONES") or []
    if not isinstance(allowed_raw, list) or len(allowed_raw) == 0:
        return False

    user_phone_raw = str(getattr(user, "phone_number", "") or "").strip()
    if user_phone_raw == "":
        return False

    user_digits_variants: set[str] = {_normalize_phone_digits(user_phone_raw)}
    try:
        normalized_user = normalize_to_e164(user_phone_raw)
        for var in get_phone_number_variations(normalized_user):
            user_digits_variants.add(_normalize_phone_digits(var))
    except Exception:
        pass

    user_digits_variants = {v for v in user_digits_variants if v}
    if not user_digits_variants:
        return False

    for candidate in allowed_raw:
        candidate_raw = str(candidate or "").strip()
        if candidate_raw == "":
            continue

        candidate_digits_variants: set[str] = {_normalize_phone_digits(candidate_raw)}
        try:
            normalized_candidate = normalize_to_e164(candidate_raw)
            for var in get_phone_number_variations(normalized_candidate):
                candidate_digits_variants.add(_normalize_phone_digits(var))
        except Exception:
            pass

        candidate_digits_variants = {v for v in candidate_digits_variants if v}
        if user_digits_variants.intersection(candidate_digits_variants):
            return True

    return False


def _get_request_user_optional() -> User | None:
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    if not token:
        cookie_name = current_app.config.get("AUTH_COOKIE_NAME", "auth_token")
        token = request.cookies.get(cookie_name)

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
        )
        user_id = uuid.UUID(str(payload.get("sub")))
    except Exception:
        return None

    try:
        return db.session.get(User, user_id)
    except Exception:
        return None


@packages_bp.route("", methods=["GET"])
def get_packages():
    """
    Endpoint untuk mengambil daftar semua paket hotspot yang aktif.
    """
    current_app.logger.info("GET /api/packages endpoint requested")
    if not hasattr(db, "session"):
        return jsonify(
            {"success": False, "message": "Kesalahan konfigurasi server (model/database)."}
        ), HTTPStatus.SERVICE_UNAVAILABLE
    try:
        request_user = _get_request_user_optional()
        is_demo_user = _is_demo_user_eligible(request_user)

        packages_db = (
            db.session.query(PackageModel)
            .options(selectinload(PackageModel.profile))
            .filter(PackageModel.is_active.is_(True))
            .order_by(PackageModel.price.asc())
            .all()
        )

        demo_mode_enabled = bool(current_app.config.get("DEMO_MODE_ENABLED", False))
        demo_show_test_package = bool(current_app.config.get("DEMO_SHOW_TEST_PACKAGE", False))
        demo_package_ids_raw = current_app.config.get("DEMO_PACKAGE_IDS") or []
        demo_package_ids: set[uuid.UUID] = set()

        if demo_mode_enabled and demo_show_test_package and isinstance(demo_package_ids_raw, list):
            for raw in demo_package_ids_raw:
                try:
                    demo_package_ids.add(uuid.UUID(str(raw)))
                except Exception:
                    continue

        if demo_package_ids and is_demo_user:
            demo_packages = (
                db.session.query(PackageModel)
                .options(selectinload(PackageModel.profile))
                .filter(PackageModel.id.in_(list(demo_package_ids)))
                .all()
            )
            existing_ids = {pkg.id for pkg in packages_db}
            for pkg in demo_packages:
                if pkg.id not in existing_ids:
                    packages_db.append(pkg)

            packages_db.sort(key=lambda p: (int(getattr(p, "price", 0) or 0), str(getattr(p, "name", ""))))
        count = len(packages_db)
        current_app.logger.info(f"Retrieved {count} active packages from database.")

        if count > 0:
            current_app.logger.debug("--- Inspecting Package Objects from DB Query ---")
            for idx, pkg_obj in enumerate(packages_db):
                # PERBAIKAN: Sesuaikan logging dengan struktur model baru
                quota_gb_value = getattr(pkg_obj, "data_quota_gb", "ATTR_NOT_FOUND")
                duration_days_value = getattr(pkg_obj, "duration_days", "ATTR_NOT_FOUND")
                current_app.logger.debug(
                    f"  Package {idx + 1}: Name='{pkg_obj.name}', "
                    f"QuotaGB={repr(quota_gb_value)}, "
                    f"DurationDays={repr(duration_days_value)}"
                )
            current_app.logger.debug("--- End Inspecting Package Objects ---")

        packages_list = []
        for pkg in packages_db:
            serialized = PackagePublic.model_validate(pkg).model_dump(mode="json")
            packages_list.append(serialized)

        return jsonify(
            {
                "success": True,
                "data": packages_list,
                "message": "Paket berhasil diambil." if count > 0 else "Tidak ada paket aktif yang tersedia saat ini.",
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_packages: {e}", exc_info=True)
        return jsonify(
            {"success": False, "message": "Terjadi kesalahan internal pada server.", "error": str(e)}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
