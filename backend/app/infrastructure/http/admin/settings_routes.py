# backend/app/infrastructure/http/admin/settings_routes.py
# VERSI FINAL SEMPURNA: Menyelaraskan alur data dari Route ke Service.

from flask import Blueprint, jsonify, request, current_app
from http import HTTPStatus
from pydantic import ValidationError, BaseModel, Field, ConfigDict
from typing import Optional, Dict

# Impor-impor esensial
from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting, User
from app.infrastructure.http.decorators import super_admin_required
from app.services import settings_service


_ALLOWED_CORE_API_METHODS = {"qris", "gopay", "va", "shopeepay"}
_ALLOWED_VA_BANKS = {"bca", "bni", "bri", "cimb", "mandiri", "permata"}


def _parse_csv_set(value: str | None) -> set[str]:
    if value is None:
        return set()
    raw = str(value).strip()
    if not raw:
        return set()
    parts = [p.strip().lower() for p in raw.split(",")]
    return {p for p in parts if p}


# Blueprint ini sudah didaftarkan dengan prefix /api/admin di __init__.py
settings_management_bp = Blueprint("settings_management_api", __name__)

# --- Skema Pydantic untuk Pengaturan ---


class SettingSchema(BaseModel):
    """Skema untuk menampilkan data pengaturan individual."""

    setting_key: str = Field(..., description="Kunci unik pengaturan")
    setting_value: Optional[str] = Field(None, description="Nilai pengaturan")
    model_config = ConfigDict(from_attributes=True)


class SettingsUpdateSchema(BaseModel):
    """
    Skema untuk menerima dictionary dari frontend, sesuai dengan payload:
    { "settings": { "key": "value", ... } }
    """

    settings: Dict[str, str] = Field(..., description="Dictionary pengaturan key-value untuk diperbarui")


# --- Endpoints Pengaturan Aplikasi ---


@settings_management_bp.route("/settings", methods=["GET"])
@super_admin_required
def get_application_settings(current_admin: User):
    """Mengambil semua pengaturan aplikasi untuk admin."""
    try:
        settings_query = db.select(ApplicationSetting).order_by(ApplicationSetting.setting_key)
        settings = db.session.scalars(settings_query).all()
        response_data = []
        for setting in settings:
            # Penting: untuk kunci terenkripsi, kembalikan nilai yang sudah didekripsi.
            # Jika mengirim ciphertext ke frontend, saat disimpan ulang akan terenkripsi lagi (double-encrypt)
            # dan runtime tidak akan bisa mendekripsi.
            value = settings_service.get_setting(setting.setting_key, "")
            response_data.append(
                {
                    "setting_key": setting.setting_key,
                    "setting_value": value if value is not None else "",
                }
            )
        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Gagal mengambil pengaturan aplikasi: {e}", exc_info=True)
        return jsonify(
            {"message": "Terjadi kesalahan internal saat memuat pengaturan."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@settings_management_bp.route("/settings", methods=["PUT"])
@super_admin_required
def update_application_settings(current_admin: User):
    """Memperbarui pengaturan aplikasi dengan validasi dan alur data yang sudah selaras."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    try:
        # 1. Validasi struktur payload utama dari frontend (mengharapkan dictionary)
        validated_data = SettingsUpdateSchema.model_validate(json_data)
        settings_dict = validated_data.settings

        # 2. Logika validasi bisnis
        errors = []
        if "MAINTENANCE_MODE_ACTIVE" in settings_dict:
            is_active_str = settings_dict.get("MAINTENANCE_MODE_ACTIVE", "False")
            if is_active_str not in ["True", "False"]:
                errors.append({"field": "MAINTENANCE_MODE_ACTIVE", "message": "Nilai harus 'True' atau 'False'"})
            # PERBAIKAN: Validasi pesan maintenance dihapus agar boleh kosong.
            # Logika sebelumnya: elif is_active_str == 'True' and not settings_dict.get('MAINTENANCE_MODE_MESSAGE'):
            # Sekarang tidak ada validasi untuk pesan, sehingga pesan boleh kosong.

        if "ENABLE_WHATSAPP_NOTIFICATIONS" in settings_dict:
            is_enabled_str = settings_dict.get("ENABLE_WHATSAPP_NOTIFICATIONS", "False")
            if is_enabled_str not in ["True", "False"]:
                errors.append({"field": "ENABLE_WHATSAPP_NOTIFICATIONS", "message": "Nilai harus 'True' atau 'False'"})
            elif is_enabled_str == "True" and not settings_dict.get("WHATSAPP_API_KEY"):
                errors.append(
                    {"field": "WHATSAPP_API_KEY", "message": "API Key WhatsApp wajib diisi jika notifikasi diaktifkan"}
                )

        if "ENABLE_TELEGRAM_NOTIFICATIONS" in settings_dict:
            is_enabled_str = settings_dict.get("ENABLE_TELEGRAM_NOTIFICATIONS", "False")
            if is_enabled_str not in ["True", "False"]:
                errors.append({"field": "ENABLE_TELEGRAM_NOTIFICATIONS", "message": "Nilai harus 'True' atau 'False'"})
            elif is_enabled_str == "True" and not settings_dict.get("TELEGRAM_BOT_TOKEN"):
                errors.append(
                    {
                        "field": "TELEGRAM_BOT_TOKEN",
                        "message": "Bot Token Telegram wajib diisi jika notifikasi Telegram diaktifkan",
                    }
                )

        mode_raw = None
        if "PAYMENT_PROVIDER_MODE" in settings_dict:
            mode_raw = str(settings_dict.get("PAYMENT_PROVIDER_MODE", "")).strip().lower()
            if mode_raw not in ["snap", "core_api", "coreapi", "core-api"]:
                errors.append(
                    {
                        "field": "PAYMENT_PROVIDER_MODE",
                        "message": "Nilai harus 'snap' atau 'core_api'",
                    }
                )

        # Core API payment options validation (only enforced when Core API is active).
        effective_mode_raw = mode_raw
        if effective_mode_raw is None:
            effective_mode_raw = (
                str(settings_service.get_setting("PAYMENT_PROVIDER_MODE", "snap") or "snap").strip().lower()
            )
        effective_mode = "core_api" if effective_mode_raw in {"core_api", "coreapi", "core-api"} else "snap"

        if effective_mode == "core_api":
            methods_raw = settings_dict.get(
                "CORE_API_ENABLED_PAYMENT_METHODS",
                settings_service.get_setting("CORE_API_ENABLED_PAYMENT_METHODS", "qris,gopay,va") or "qris,gopay,va",
            )
            methods = _parse_csv_set(methods_raw)
            invalid_methods = sorted(m for m in methods if m not in _ALLOWED_CORE_API_METHODS)
            if invalid_methods:
                errors.append(
                    {
                        "field": "CORE_API_ENABLED_PAYMENT_METHODS",
                        "message": f"Metode tidak dikenali: {', '.join(invalid_methods)}",
                    }
                )
            if not methods:
                errors.append(
                    {
                        "field": "CORE_API_ENABLED_PAYMENT_METHODS",
                        "message": "Minimal pilih 1 metode pembayaran untuk Core API.",
                    }
                )

            if "va" in methods:
                banks_raw = settings_dict.get(
                    "CORE_API_ENABLED_VA_BANKS",
                    settings_service.get_setting("CORE_API_ENABLED_VA_BANKS", "bca,bni,bri,mandiri,permata,cimb")
                    or "bca,bni,bri,mandiri,permata,cimb",
                )
                banks = _parse_csv_set(banks_raw)
                invalid_banks = sorted(b for b in banks if b not in _ALLOWED_VA_BANKS)
                if invalid_banks:
                    errors.append(
                        {
                            "field": "CORE_API_ENABLED_VA_BANKS",
                            "message": f"Bank VA tidak dikenali: {', '.join(invalid_banks)}",
                        }
                    )
                if not banks:
                    errors.append(
                        {
                            "field": "CORE_API_ENABLED_VA_BANKS",
                            "message": "Minimal pilih 1 bank untuk Virtual Account.",
                        }
                    )

        if errors:
            return jsonify({"errors": errors}), HTTPStatus.UNPROCESSABLE_ENTITY

        # 3. Langsung panggil service dengan data dictionary yang sudah valid.
        settings_service.update_settings(settings_dict)

        # 4. Commit transaksi setelah service selesai bekerja.
        db.session.commit()

        return jsonify({"message": "Pengaturan berhasil diperbarui."}), HTTPStatus.OK

    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal memperbarui pengaturan oleh {current_admin.id}: {e}", exc_info=True)
        return jsonify(
            {"message": "Terjadi kesalahan internal saat menyimpan pengaturan."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
