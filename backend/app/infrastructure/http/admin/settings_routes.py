# backend/app/infrastructure/http/admin/settings_routes.py
# --------------------------------------------------------
# VERSI FINAL – selaras service & payload object {settings:{…}}
# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false

from http import HTTPStatus
from typing import Dict, Optional
from collections import defaultdict

from flask import Blueprint, jsonify, request, current_app
from pydantic import BaseModel, Field, ValidationError

from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting, User
from app.infrastructure.http.decorators import super_admin_required
from app.services import settings_service

settings_management_bp = Blueprint("settings_management_api", __name__)

# In-memory counter untuk tracking frekuensi field error (reset saat restart)
VALIDATION_ERROR_FIELD_COUNTS = defaultdict(int)

# ---------- Pydantic schemas ----------
class SettingSchema(BaseModel):
    setting_key: str = Field(..., description="Kunci unik")
    setting_value: Optional[str] = None

    model_config = {"from_attributes": True}


class SettingsUpdateSchema(BaseModel):
    settings: Dict[str, str]


# ---------- End-points ----------
@settings_management_bp.get("/settings")
@super_admin_required
def get_application_settings(current_admin: User):
    try:
        rows = (
            db.session.scalars(
                db.select(ApplicationSetting).order_by(ApplicationSetting.setting_key)
            ).all()
        )
        return (
            jsonify([SettingSchema.model_validate(r).model_dump(exclude_none=True) for r in rows]),
            HTTPStatus.OK,
        )
    except Exception as exc:
        current_app.logger.exception("Load settings failed")
        return (
            jsonify({"message": "Terjadi kesalahan internal saat memuat pengaturan."}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@settings_management_bp.put("/settings")
@super_admin_required
def update_application_settings(current_admin: User):
    payload = request.get_json()
    if not payload:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    try:
        # Normalisasi: pastikan semua nilai settings adalah string (None -> '') untuk mencegah 422 pydantic
        if isinstance(payload, dict) and isinstance(payload.get('settings'), dict):
            raw_settings = payload['settings']
            coerced = {}
            for k, v in raw_settings.items():
                if v is None:
                    coerced[k] = ''
                elif isinstance(v, (str,)):  # sudah string
                    coerced[k] = v
                else:
                    # Cast tipe lain (bool, int, float) ke string
                    coerced[k] = str(v)
            payload['settings'] = coerced
            current_app.logger.debug('[SETTINGS] Incoming keys=%s coerced_count=%s', list(coerced.keys())[:10], len(coerced))
        validated = SettingsUpdateSchema.model_validate(payload)
        settings   = validated.settings

        # -------- Bisnis validasi --------
        errors = []
        if "MAINTENANCE_MODE_ACTIVE" in settings:
            val = settings["MAINTENANCE_MODE_ACTIVE"]
            if val not in {"True", "False"}:
                errors.append(
                    {"field": "MAINTENANCE_MODE_ACTIVE", "message": "Harus 'True' atau 'False'"}
                )

        if "ENABLE_WHATSAPP_NOTIFICATIONS" in settings:
            val = settings["ENABLE_WHATSAPP_NOTIFICATIONS"]
            if val not in {"True", "False"}:
                errors.append(
                    {
                        "field": "ENABLE_WHATSAPP_NOTIFICATIONS",
                        "message": "Harus 'True' atau 'False'",
                    }
                )
            elif val == "True" and not settings.get("WHATSAPP_API_KEY"):
                errors.append(
                    {"field": "WHATSAPP_API_KEY", "message": "API Key wajib diisi ketika aktif"}
                )

        if errors:
            for err in errors:
                fld = err.get("field") or "__unknown__"
                VALIDATION_ERROR_FIELD_COUNTS[fld] += 1
            current_app.logger.warning(
                "[SETTINGS] Validation failed fields=%s counts=%s",  # log ringkas
                [e.get("field") for e in errors],
                {k: VALIDATION_ERROR_FIELD_COUNTS[k] for k in VALIDATION_ERROR_FIELD_COUNTS},
            )
            return (
                jsonify({
                    "success": False,
                    "message": "Validasi gagal",
                    "errorCode": "VALIDATION_ERROR",
                    "data": {"errors": errors},
                }),
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )

        # -------- Simpan --------
        settings_service.update_settings(settings)
        db.session.commit()
        return jsonify({"message": "Pengaturan berhasil diperbarui."}), HTTPStatus.OK

    except ValidationError as ve:
        ve_list = ve.errors()
        for err in ve_list:
            loc = err.get("loc")
            fld = loc[-1] if isinstance(loc, (list, tuple)) and loc else "__pydantic__"
            VALIDATION_ERROR_FIELD_COUNTS[fld] += 1
        current_app.logger.warning(
            "[SETTINGS] Pydantic validation errors locs=%s counts=%s",
            [e.get("loc") for e in ve_list],
            {k: VALIDATION_ERROR_FIELD_COUNTS[k] for k in VALIDATION_ERROR_FIELD_COUNTS},
        )
        return (
            jsonify({
                "success": False,
                "message": "Validasi gagal",
                "errorCode": "VALIDATION_ERROR",
                "data": {"errors": ve_list},
            }),
            HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Update settings failed")
        return (
            jsonify({"message": "Terjadi kesalahan internal saat menyimpan pengaturan."}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


@settings_management_bp.get("/settings/validation-stats")
@super_admin_required
def get_settings_validation_stats(current_admin: User):
    """Mengembalikan statistik frekuensi error validasi (sementara, reset saat restart)."""
    from datetime import datetime
    stats = {k: VALIDATION_ERROR_FIELD_COUNTS[k] for k in VALIDATION_ERROR_FIELD_COUNTS}
    return (
        jsonify({
            "success": True,
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "totalDistinct": len(stats),
            "stats": stats,
        }),
        HTTPStatus.OK,
    )