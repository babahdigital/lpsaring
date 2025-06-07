# backend/app/infrastructure/http/auth_routes.py
# Versi: Perbaikan nama atribut Redis client untuk OTP dan konsistensi

from flask import Blueprint, request, jsonify, current_app
from pydantic import ValidationError
from http import HTTPStatus
import random
import string
from datetime import datetime, timedelta, timezone as dt_timezone
from jose import jwt, JWTError, ExpiredSignatureError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select
from functools import wraps
import uuid
import enum
from typing import Optional, Dict, Any
from werkzeug.security import check_password_hash
from .schemas.auth_schemas import validate_phone_number

# Impor get_client_ip dari utils
from app.utils.request_utils import get_client_ip # Pastikan app/utils/request_utils.py ada dan benar

# --- Import Timezone Handling ---
try:
    from pytz import timezone as pytz_timezone, utc as pytz_utc
    PYTZ_AVAILABLE = True
except ImportError:
    print("WARNING: pytz library not found. Timezone conversion might be limited.")
    PYTZ_AVAILABLE = False
    class WITA(dt_timezone): # type: ignore
        _offset = timedelta(hours=8)
        _name = "WITA"
        def utcoffset(self, dt): return self._offset # type: ignore
        def dst(self, dt): return timedelta(0) # type: ignore
        def tzname(self, dt): return self._name # type: ignore
    wita_tz_fallback = WITA()

# Import skema
from .schemas.auth_schemas import (
    RequestOtpRequestSchema, VerifyOtpRequestSchema,
    RequestOtpResponseSchema, VerifyOtpResponseSchema, AuthErrorResponseSchema,
    UserRegisterRequestSchema, UserRegisterResponseSchema
)
try:
    from .schemas.user_schemas import UserMeResponseSchema
except ImportError:
    from pydantic import BaseModel # type: ignore
    class UserMeResponseSchema(BaseModel): # Placeholder
        id: uuid.UUID
        phone_number: str
        full_name: Optional[str] = None
        is_active: bool
        blok: Optional[str] = None
        kamar: Optional[str] = None
        class Config: from_attributes = True; use_enum_values = True # type: ignore
    # Gunakan logger modul jika current_app belum tersedia saat definisi modul
    module_logger = logging.getLogger(__name__) if 'logging' in sys.modules else print
    module_logger.warning("UserMeResponseSchema not found/fully loaded from user_schemas.py. Using placeholder.")


# Import ekstensi dan model
from app.extensions import db
try:
    from app.infrastructure.db.models import User, UserRole, ApprovalStatus, UserBlok, UserKamar, UserLoginHistory
except ImportError as e_model_import:
    # Gunakan logger modul jika current_app belum tersedia
    module_logger_models = logging.getLogger(__name__) if 'logging' in sys.modules else print
    module_logger_models.critical(f"CRITICAL ERROR: Failed to import models (User, UserRole, ApprovalStatus, UserBlok, UserKamar, UserLoginHistory) in auth_routes.py: {e_model_import}")
    class UserRole(str, enum.Enum): USER = "USER"; ADMIN = "ADMIN"; SUPER_ADMIN = "SUPER_ADMIN" # type: ignore
    class ApprovalStatus(str, enum.Enum): PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; REJECTED = "REJECTED" # type: ignore
    class UserBlok(str, enum.Enum): A="A"; B="B"; C="C"; D="D"; E="E"; F="F" # type: ignore
    class UserKamar(str, enum.Enum): Kamar_1="1"; Kamar_2="2"; Kamar_3="3"; Kamar_4="4"; Kamar_5="5"; Kamar_6="6" # type: ignore
    User = None # type: ignore
    UserLoginHistory = None # type: ignore

# Import klien WhatsApp & helper format nomor
try:
    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message, send_otp_whatsapp
except ImportError:
    def send_whatsapp_message(to: str, body: str) -> bool:
        logger_wa = current_app.logger if current_app else logging.getLogger(__name__) # type: ignore
        logger_wa.error(f"Dummy send_whatsapp_message called to {to}.") # type: ignore
        return False
    def send_otp_whatsapp(to: str, otp: str) -> bool:
        logger_wa_otp = current_app.logger if current_app else logging.getLogger(__name__) # type: ignore
        logger_wa_otp.error(f"Dummy send_otp_whatsapp called to {to}.") # type: ignore
        return False

try:
    from app.infrastructure.gateways.mikrotik_client import format_to_local_phone
except ImportError:
    def format_to_local_phone(phone: str | None) -> str | None: return phone # type: ignore

# Import library user-agents
try:
    from user_agents import parse as parse_user_agent
except ImportError:
    def parse_user_agent(u_agent_str: str) -> Any: # type: ignore
        class DummyDevice: brand: Optional[str] = None; family: Optional[str] = None; model: Optional[str] = None # type: ignore
        class DummyParsed: device: DummyDevice = DummyDevice() # type: ignore
        class DummyOS: family: Optional[str] = None; version_string: Optional[str] = None # type: ignore
        DummyParsed.os = DummyOS() # type: ignore
        DummyParsed.is_mobile = False; DummyParsed.is_tablet = False # type: ignore
        return DummyParsed() # type: ignore


auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# --- Decorator token_required ---
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        error_response = AuthErrorResponseSchema(error="Unauthorized")
        if not auth_header:
            current_app.logger.debug("[@token_required] No Authorization header found.")
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

        parts = auth_header.split()
        if parts[0].lower() != 'bearer' or len(parts) != 2:
            current_app.logger.debug(f"[@token_required] Invalid token header format: {auth_header}")
            error_response.error = "Invalid token header format."
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED

        token = parts[1]
        user_uuid_from_token: Optional[uuid.UUID] = None
        try:
            payload = jwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
            current_app.logger.debug(f"[@token_required] Token payload decoded: {payload}")
            current_user_id_str = payload.get('sub')
            if not current_user_id_str:
                current_app.logger.warning("[@token_required] Missing 'sub' claim in token.")
                raise JWTError("Missing 'sub' claim in token.")

            user_uuid_from_token = uuid.UUID(current_user_id_str)
            current_app.logger.debug(f"[@token_required] User UUID from token: {user_uuid_from_token}")

            stmt = select(User).where(User.id == user_uuid_from_token) # type: ignore
            user_from_token = db.session.execute(stmt).scalar_one_or_none()
            
            if not user_from_token:
                current_app.logger.warning(f"[@token_required] User ID {user_uuid_from_token} from token not found in DB (checked with fresh query).")
                error_response.error = "User associated with token not found."
                return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
            
            current_app.logger.debug(f"[@token_required] User found from DB: ID={user_from_token.id}, Active={user_from_token.is_active}")

            if not user_from_token.is_active:
                current_app.logger.warning(f"[@token_required] User ID {user_uuid_from_token} from token is not active.")
                error_response.error = "User account is inactive."
                return jsonify(error_response.model_dump()), HTTPStatus.FORBIDDEN

        except ExpiredSignatureError:
            current_app.logger.info(f"[@token_required] Token has expired for UUID (attempted): {user_uuid_from_token}")
            error_response.error = "Token has expired."
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
        except (JWTError, ValueError) as e: # ValueError bisa terjadi jika UUID tidak valid
            current_app.logger.warning(f"[@token_required] Invalid token: {str(e)}. Token: {token[:20]}...")
            error_response.error = f"Invalid token: {str(e)}"
            return jsonify(error_response.model_dump()), HTTPStatus.UNAUTHORIZED
        except Exception as e:
            current_app.logger.error(f"[@token_required] Token validation encountered an unexpected exception: {e}", exc_info=True)
            error_response.error = "Could not process token due to an internal server error."
            return jsonify(error_response.model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        
        if user_uuid_from_token is None: # Pemeriksaan tambahan
             current_app.logger.error("CRITICAL: user_uuid_from_token is None after successful token decoding in @token_required.")
             return jsonify(AuthErrorResponseSchema(error="Internal error during token processing.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

        return f(current_user_id=user_uuid_from_token, *args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    @token_required
    def decorated_function(current_user_id, *args, **kwargs):
        # Dapatkan objek user dari current_user_id yang diberikan oleh @token_required
        admin_user = db.session.get(User, current_user_id)
        
        # Periksa apakah user ada dan memiliki peran yang sesuai
        if not admin_user or not admin_user.is_admin_role:
            current_app.logger.warning(
                f"Akses DITOLAK ke rute admin. User ID: {current_user_id}, "
                f"Role: {admin_user.role.value if admin_user and admin_user.role else 'Tidak Ditemukan'}"
            )
            return jsonify(AuthErrorResponseSchema(error="Akses ditolak. Memerlukan hak akses Admin.").model_dump()), HTTPStatus.FORBIDDEN
        
        # Jika valid, teruskan ke fungsi endpoint asli
        # Kita bisa meneruskan objek admin_user untuk menghindari query ulang
        return f(current_admin=admin_user, *args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def generate_otp(length: int = 6) -> str:
    """Generates a random numeric OTP."""
    return "".join(random.choices(string.digits, k=length))

def store_otp_in_redis(phone_number: str, otp: str) -> bool:
    """Stores OTP in Redis with an expiration time."""
    try:
        key = f"otp:{phone_number}"
        expire_seconds = current_app.config.get('OTP_EXPIRE_SECONDS', 300)
        # PERBAIKAN KUNCI: Gunakan current_app.redis_client_otp
        redis_client = current_app.redis_client_otp 
        
        if redis_client is None:
            current_app.logger.error(f"Redis client for OTP (redis_client_otp) is not initialized. Cannot store OTP for {phone_number}.")
            return False
            
        redis_client.setex(key, expire_seconds, otp)
        current_app.logger.debug(f"OTP {otp} stored in Redis for {phone_number} with {expire_seconds}s expiry.")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to store OTP in Redis for {phone_number}: {e}", exc_info=True)
        return False

def verify_otp_from_redis(phone_number: str, otp_code: str) -> bool:
    """Verifies OTP from Redis and deletes it if valid."""
    try:
        key = f"otp:{phone_number}"
        # PERBAIKAN KUNCI: Gunakan current_app.redis_client_otp
        redis_client = current_app.redis_client_otp
        
        if redis_client is None:
            current_app.logger.error(f"Redis client for OTP (redis_client_otp) is not initialized. Cannot verify OTP for {phone_number}.")
            return False
            
        stored_otp = redis_client.get(key)
        current_app.logger.debug(f"Verifying OTP for {phone_number}. Input: {otp_code}, Stored: {stored_otp}")
    except Exception as e:
        current_app.logger.error(f"Failed to retrieve OTP from Redis for {phone_number}: {e}", exc_info=True)
        return False

    if stored_otp:
        # decode_responses=True di Redis client seharusnya sudah menangani ini, tapi defensive check tidak masalah
        if isinstance(stored_otp, bytes): 
            stored_otp = stored_otp.decode('utf-8')
            
        if stored_otp == otp_code:
            try:
                 if redis_client: # Pastikan client ada sebelum delete
                    redis_client.delete(key)
                    current_app.logger.debug(f"OTP verified for {phone_number}. Key {key} deleted from Redis.")
            except Exception as e_del:
                 current_app.logger.warning(f"Failed to delete OTP key {key} from Redis after verification: {e_del}", exc_info=False)
            return True
    current_app.logger.warning(f"OTP verification failed for {phone_number}. Input: {otp_code}, Stored: {stored_otp}")
    return False

def create_access_token(data: dict) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    expire_minutes = current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES_MINUTES', 30)
    expire_delta = timedelta(minutes=expire_minutes)
    now_utc = datetime.now(dt_timezone.utc)
    expire_at_utc = now_utc + expire_delta
    to_encode.update({"exp": expire_at_utc, "iat": now_utc})
    
    encoded_jwt = jwt.encode(
        to_encode,
        current_app.config['JWT_SECRET_KEY'],
        algorithm=current_app.config['JWT_ALGORITHM']
    )
    current_app.logger.debug(f"Access token created for sub: {data.get('sub')}, exp: {expire_at_utc.isoformat()}")
    return encoded_jwt

# === Endpoint Registrasi Pengguna ===
@auth_bp.route('/register', methods=['POST'])
def register_user():
    # ... (Kode endpoint register_user tetap sama seperti sebelumnya) ...
    # ... (Pastikan tidak ada referensi ke current_app.redis_client di sini) ...
    normalized_phone_number = "N/A"
    new_user_obj: Optional[User] = None
    data_input: Optional[UserRegisterRequestSchema] = None

    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    try:
        data_input = UserRegisterRequestSchema.model_validate(request.json)
        normalized_phone_number = data_input.phone_number
    except ValidationError as e:
        error_details_log = []
        for error_item in e.errors():
            field = ".".join(str(loc) for loc in error_item['loc']) if error_item['loc'] else 'N/A'
            error_details_log.append(f"Field: {field}, Message: {error_item['msg']}, Type: {error_item['type']}")
        current_app.logger.warning(f"Registration Pydantic validation failed: {'; '.join(error_details_log)}. Input: {request.json}")
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e_val:
        current_app.logger.error(f"Registration data validation/parsing error (non-Pydantic): {e_val}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan saat memvalidasi data input Anda.").model_dump()), HTTPStatus.BAD_REQUEST

    if User is None or UserRole is None or ApprovalStatus is None or UserBlok is None or UserKamar is None:
        current_app.logger.critical("Essential models (User, UserRole, ApprovalStatus, UserBlok, UserKamar) are not initialized.")
        return jsonify(AuthErrorResponseSchema(error="Kesalahan konfigurasi server (model/enum).").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

    if not data_input:
        current_app.logger.error("data_input is None after validation block in registration.")
        return jsonify(AuthErrorResponseSchema(error="Kesalahan internal server saat memproses data.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

    if db.session.execute(select(User.id).filter_by(phone_number=normalized_phone_number)).scalar_one_or_none():
        return jsonify(AuthErrorResponseSchema(error="Nomor telepon sudah terdaftar.").model_dump()), HTTPStatus.CONFLICT

    ua_string = request.headers.get('User-Agent')
    device_brand: Optional[str] = None
    device_model: Optional[str] = None
    raw_ua: Optional[str] = None

    current_app.logger.debug(f"[Register] Received User-Agent: {ua_string}")
    if ua_string:
        raw_ua = ua_string[:1024] 
        try:
            ua_info = parse_user_agent(ua_string)
            brand_parsed = getattr(ua_info.device, 'brand', 'N/A')
            model_parsed = getattr(ua_info.device, 'model', 'N/A')
            family_parsed = getattr(ua_info.device, 'family', 'N/A')
            current_app.logger.debug(f"[Register] Parsed UA Info: Brand='{brand_parsed}', Model='{model_parsed}', Family='{family_parsed}'")

            if ua_info and hasattr(ua_info, 'device'):
                device_brand = getattr(ua_info.device, 'brand', None)
                device_model = getattr(ua_info.device, 'model', None)
                if device_brand == "Other": device_brand = None
                if device_model == "Other": device_model = getattr(ua_info.device, 'family', None)
                if device_model == "Other": device_model = None
                elif device_model: current_app.logger.debug(f"[Register] Using device family '{device_model}' as final model.")
        except Exception as ua_err:
            current_app.logger.error(f"[Register] Error parsing User-Agent string '{ua_string[:50]}...': {ua_err}", exc_info=False)

    try:
        new_user_obj = User(
            phone_number=normalized_phone_number,
            full_name=data_input.full_name,
            blok=data_input.blok,
            kamar=data_input.kamar,
            role=UserRole.USER, # type: ignore
            approval_status=ApprovalStatus.PENDING_APPROVAL, # type: ignore
            is_active=False,
            device_brand=device_brand,
            device_model=device_model,
            raw_user_agent=raw_ua
        )
        db.session.add(new_user_obj)
        db.session.commit()
        db.session.refresh(new_user_obj)
        current_app.logger.info(f"New user registered: ID={new_user_obj.id}, Phone={new_user_obj.phone_number}")

        user_full_name_for_notif = new_user_obj.full_name
        user_phone_for_notif = new_user_obj.phone_number
        user_id_for_notif = new_user_obj.id
        user_created_at_for_notif = new_user_obj.created_at
        user_device_brand_for_notif = new_user_obj.device_brand
        user_device_model_for_notif = new_user_obj.device_model
        user_blok_for_notif = new_user_obj.blok
        user_kamar_for_notif = new_user_obj.kamar

        try:
            user_message = (
                f"Terima kasih {user_full_name_for_notif or 'Pelanggan'}, pendaftaran Anda di Portal Hotspot "
                f"telah kami terima dan sedang ditinjau oleh Admin. Mohon tunggu informasi selanjutnya."
            )
            if not send_whatsapp_message(user_phone_for_notif, user_message):
                current_app.logger.warning(f"Failed to send WA to user {user_phone_for_notif}")
        except Exception as e_wa_user:
            current_app.logger.error(f"Error sending WA to new user {user_id_for_notif}: {e_wa_user}", exc_info=True)

        try:
            stmt_admins = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN]), User.is_active == True) # type: ignore
            active_admins = db.session.execute(stmt_admins).scalars().all()

            if active_admins:
                days_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
                months_id = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
                hari_str, tanggal_str, waktu_str = "N/A", "N/A", "N/A"

                if user_created_at_for_notif:
                    created_at_utc = user_created_at_for_notif
                    created_at_wita = None
                    
                    if PYTZ_AVAILABLE:
                        try: target_tz = pytz_timezone('Asia/Makassar')
                        except Exception as tz_load_err:
                             current_app.logger.error(f"Failed to load pytz timezone 'Asia/Makassar': {tz_load_err}")
                             target_tz = dt_timezone.utc 
                    else:
                        target_tz = wita_tz_fallback 
                               
                    try: created_at_wita = created_at_utc.astimezone(target_tz)
                    except Exception as tz_conv_err:
                        current_app.logger.error(f"Timezone conversion error: {tz_conv_err}")
                        hari_str, tanggal_str = created_at_utc.strftime('%A'), created_at_utc.strftime('%d %B %Y')
                        waktu_str = created_at_utc.strftime('%H:%M UTC') + (" (pytz available)" if PYTZ_AVAILABLE else " (pytz not available)")
                    
                    if created_at_wita:
                        try:
                            hari_str = days_id[created_at_wita.weekday()]
                            tanggal_str = f"{created_at_wita.day:02d} {months_id[created_at_wita.month - 1]} {created_at_wita.year}"
                            waktu_str = created_at_wita.strftime('%H:%M WITA')
                        except IndexError:
                            current_app.logger.error("Index error day/month formatting for admin notification.")
                            hari_str, tanggal_str = created_at_wita.strftime('%A'), created_at_wita.strftime('%d %B %Y')
                            waktu_str = created_at_wita.strftime('%H:%M %Z')
                
                formatted_phone_for_admin = format_to_local_phone(user_phone_for_notif) or user_phone_for_notif
                brand_text_for_admin = user_device_brand_for_notif or 'N/A'
                model_text_for_admin = user_device_model_for_notif or 'N/A'
                blok_value_for_admin = user_blok_for_notif.value if user_blok_for_notif and hasattr(user_blok_for_notif, 'value') else str(user_blok_for_notif) if user_blok_for_notif else 'N/A' # type: ignore
                kamar_value_for_admin = user_kamar_for_notif.value if user_kamar_for_notif and hasattr(user_kamar_for_notif, 'value') else str(user_kamar_for_notif) if user_kamar_for_notif else 'N/A' # type: ignore

                admin_message = (
                    f"🔔 Pendaftaran Baru 🔔\n\n"
                    f"Hari: {hari_str}, {tanggal_str}\n"
                    f"Waktu: {waktu_str}\n\n"
                    f"Nama Lengkap: {user_full_name_for_notif}\n"
                    f"No. Telepon: {formatted_phone_for_admin}\n\n"
                    f"Blok: {blok_value_for_admin}\n"
                    f"Kamar: {kamar_value_for_admin}\n\n"
                    f"Device Brand: {brand_text_for_admin}\n"
                    f"Device Model: {model_text_for_admin}\n\n"
                    f"Mohon untuk segera ditinjau."
                )
                sent_admin_count, failed_admin_count = 0, 0
                for admin_user in active_admins:
                    if admin_user.phone_number:
                        if send_whatsapp_message(admin_user.phone_number, admin_message): sent_admin_count += 1
                        else: failed_admin_count += 1; current_app.logger.warning(f"Failed send admin notif to {admin_user.phone_number}")
                    else: current_app.logger.warning(f"Admin {admin_user.id} has no phone.")
                current_app.logger.info(f"Admin notification: {sent_admin_count} sent, {failed_admin_count} failed.")
            else:
                current_app.logger.warning("No active admins found for new user registration notification.")
        except Exception as e_notify_admin:
            current_app.logger.error(f"Error during admin notification for {user_id_for_notif}: {e_notify_admin}", exc_info=True)

        response_data = UserRegisterResponseSchema(
            message="Registrasi berhasil. Akun Anda sedang menunggu persetujuan Admin.",
            user_id=user_id_for_notif, # type: ignore
            phone_number=user_phone_for_notif
        )
        return jsonify(response_data.model_dump()), HTTPStatus.CREATED

    except IntegrityError:
        db.session.rollback()
        current_app.logger.warning(f"Reg IntegrityError for {normalized_phone_number}.", exc_info=False)
        return jsonify(AuthErrorResponseSchema(error="Data konflik (nomor telepon mungkin sudah ada).").model_dump()), HTTPStatus.CONFLICT
    except SQLAlchemyError as e_sql:
        db.session.rollback()
        current_app.logger.error(f"Reg SQLAlchemyError for {normalized_phone_number}: {e_sql}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan database saat registrasi.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        if hasattr(db, 'session') and db.session.is_active: db.session.rollback()
        current_app.logger.error(f"Unexpected error for {normalized_phone_number} in /register: {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan tidak terduga saat registrasi.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        current_app.logger.debug(f"Ending /register for {normalized_phone_number}.")
        if hasattr(db, 'session'):
            db.session.remove()


# === Endpoint /me ===
@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user_id: uuid.UUID):
    user_for_response: Optional[User] = None
    try:
        current_app.logger.debug(f"[/me] Request received for user_id from token: {current_user_id}")
        if User is None or UserMeResponseSchema is None: # type: ignore
            current_app.logger.critical("[/me] User model or UserMeResponseSchema not available.")
            return jsonify(AuthErrorResponseSchema(error="Kesalahan konfigurasi server.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

        stmt = select(User).where(User.id == current_user_id) # type: ignore
        user_for_response = db.session.execute(stmt).scalar_one_or_none()
        
        if not user_for_response:
            current_app.logger.error(f"[/me] User {current_user_id} from token NOT FOUND in DB (checked with fresh query).")
            return jsonify(AuthErrorResponseSchema(error="Pengguna tidak ditemukan.").model_dump()), HTTPStatus.NOT_FOUND
        
        current_app.logger.debug(f"[/me] User found: ID={user_for_response.id}, Active={user_for_response.is_active}, Role={user_for_response.role.value if user_for_response.role else 'N/A'}") # type: ignore

        if not user_for_response.is_active: # type: ignore
            current_app.logger.warning(f"[/me] User {current_user_id} is not active.")
            return jsonify(AuthErrorResponseSchema(error="Akun pengguna tidak aktif.").model_dump()), HTTPStatus.FORBIDDEN

        user_data_response = UserMeResponseSchema.model_validate(user_for_response) # type: ignore
        return jsonify(user_data_response.model_dump(mode='json')), HTTPStatus.OK

    except Exception as e_me:
        current_app.logger.error(f"[/me] Error fetching user details for user {current_user_id}: {e_me}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan server saat mengambil data pengguna.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        current_app.logger.debug(f"Ending /me for user {current_user_id}.")
        if hasattr(db, 'session'):
            db.session.remove()

# === Endpoint /request-otp ===
@auth_bp.route('/request-otp', methods=['POST'])
def request_otp():
    phone_number_for_otp = "N/A"
    user_for_otp: Optional[User] = None
    try:
        if not request.is_json:
            return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

        if User is None or ApprovalStatus is None: # type: ignore
            current_app.logger.critical("User model or ApprovalStatus enum not available for /request-otp.")
            return jsonify(AuthErrorResponseSchema(error="Kesalahan konfigurasi server.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

        data = RequestOtpRequestSchema.model_validate(request.json)
        phone_number_for_otp = data.phone_number

        user_for_otp = db.session.execute(select(User).filter_by(phone_number=phone_number_for_otp)).scalar_one_or_none() # type: ignore

        if not user_for_otp:
            return jsonify(AuthErrorResponseSchema(error="Nomor telepon belum terdaftar.").model_dump()), HTTPStatus.NOT_FOUND

        is_user_approved = (user_for_otp.approval_status == ApprovalStatus.APPROVED) # type: ignore
        if not user_for_otp.is_active or not is_user_approved: # type: ignore
            message_otp_denied = "Login gagal. Akun Anda belum aktif atau belum disetujui oleh Admin."
            if user_for_otp.approval_status == ApprovalStatus.PENDING_APPROVAL: # type: ignore
                message_otp_denied = "Login gagal. Akun Anda sedang dalam proses peninjauan oleh Admin."
            elif user_for_otp.approval_status == ApprovalStatus.REJECTED: # type: ignore
                message_otp_denied = "Login gagal. Pendaftaran akun Anda telah ditolak."
            elif not user_for_otp.is_active and is_user_approved: # type: ignore
                 message_otp_denied = "Login gagal. Akun Anda saat ini tidak aktif. Silakan hubungi Admin."
            current_app.logger.warning(f"OTP request for {phone_number_for_otp} denied. Status: active={user_for_otp.is_active}, approval={user_for_otp.approval_status.value if user_for_otp.approval_status and hasattr(user_for_otp.approval_status, 'value') else 'N/A'}") # type: ignore
            return jsonify(AuthErrorResponseSchema(error=message_otp_denied).model_dump()), HTTPStatus.FORBIDDEN

        otp_generated = generate_otp()
        if not store_otp_in_redis(phone_number_for_otp, otp_generated): # Fungsi ini sekarang menggunakan redis_client_otp
            return jsonify(AuthErrorResponseSchema(error="Gagal memproses permintaan OTP karena kesalahan server (penyimpanan).").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

        if not send_otp_whatsapp(phone_number_for_otp, otp_generated):
            current_app.logger.warning(f"Failed to send OTP via WhatsApp to {phone_number_for_otp}, but OTP was stored in Redis.")

        return jsonify(RequestOtpResponseSchema(message="OTP telah dikirim ke nomor telepon Anda.").model_dump()), HTTPStatus.OK

    except ValidationError as e_val_otp:
        error_details_log_otp = []
        for error_item_otp in e_val_otp.errors():
            field_otp = ".".join(str(loc) for loc in error_item_otp['loc']) if error_item_otp['loc'] else 'N/A'
            error_details_log_otp.append(f"Field: {field_otp}, Message: {error_item_otp['msg']}, Type: {error_item_otp['type']}")
        current_app.logger.warning(f"Request OTP Pydantic validation failed for {phone_number_for_otp}: {'; '.join(error_details_log_otp)}. Input: {request.json if request.is_json else 'Not JSON'}")
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e_val_otp.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except SQLAlchemyError as e_db_otp:
        current_app.logger.error(f"Database error during OTP request for {phone_number_for_otp}: {e_db_otp}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan server saat memproses permintaan OTP.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e_otp_req:
        current_app.logger.error(f"Unexpected error during OTP request for {phone_number_for_otp}: {e_otp_req}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tidak terduga saat meminta OTP.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        user_id_log = user_for_otp.id if user_for_otp and hasattr(user_for_otp, 'id') else "N/A" # type: ignore
        current_app.logger.debug(f"Ending /request-otp for {phone_number_for_otp}. User found: {user_id_log}")
        if hasattr(db, 'session'):
            db.session.remove()

# === Endpoint /verify-otp ===
@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    phone_number_to_verify = "N/A" 
    user_id_for_log: Optional[str] = "N/A" 
    client_ip_address = get_client_ip() # Panggil di awal untuk logging
    current_app.logger.info(f"[/verify-otp] Attempt from IP: {client_ip_address}")

    try:
        if not request.is_json:
            return jsonify(AuthErrorResponseSchema(error="Request body must be JSON.").model_dump()), HTTPStatus.BAD_REQUEST

        if User is None or ApprovalStatus is None or UserLoginHistory is None: # type: ignore
            current_app.logger.critical("User model, ApprovalStatus enum, or UserLoginHistory model not available for /verify-otp.")
            return jsonify(AuthErrorResponseSchema(error="Kesalahan konfigurasi server.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR

        data = VerifyOtpRequestSchema.model_validate(request.json)
        phone_number_to_verify = data.phone_number
        otp_code_to_verify = data.otp

        if not verify_otp_from_redis(phone_number_to_verify, otp_code_to_verify): # Fungsi ini sekarang menggunakan redis_client_otp
            return jsonify(AuthErrorResponseSchema(error="Kode OTP tidak valid atau telah kedaluwarsa.").model_dump()), HTTPStatus.UNAUTHORIZED

        user_to_login = db.session.execute(select(User).filter_by(phone_number=phone_number_to_verify)).scalar_one_or_none() # type: ignore

        if not user_to_login:
            current_app.logger.error(f"CRITICAL: OTP verified for {phone_number_to_verify}, but user not found in database!")
            return jsonify(AuthErrorResponseSchema(error="Pengguna tidak ditemukan setelah verifikasi OTP berhasil. Hubungi Admin.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
        
        user_id_for_log = str(user_to_login.id) # type: ignore

        if not user_to_login.is_active or user_to_login.approval_status != ApprovalStatus.APPROVED: # type: ignore
            current_app.logger.warning(f"Login attempt for {phone_number_to_verify} denied after OTP verification. Status: active={user_to_login.is_active}, approval={user_to_login.approval_status.value if user_to_login.approval_status and hasattr(user_to_login.approval_status, 'value') else 'N/A'}") # type: ignore
            return jsonify(AuthErrorResponseSchema(error="Akun belum aktif atau disetujui. Tidak dapat login.").model_dump()), HTTPStatus.FORBIDDEN

        # Catat riwayat login
        try:
            user_agent_str = request.headers.get('User-Agent')
            new_login_entry = UserLoginHistory(
                user_id=user_to_login.id, # type: ignore
                ip_address=client_ip_address, 
                user_agent_string=user_agent_str[:1024] if user_agent_str else None
            )
            db.session.add(new_login_entry)
            current_app.logger.info(f"Login history entry created for user {user_id_for_log}. IP: {client_ip_address}, UA: {user_agent_str[:50] if user_agent_str else 'N/A'}...")
        except Exception as e_log_history:
            current_app.logger.error(f"Failed to log login history for user {user_id_for_log}: {e_log_history}", exc_info=True)

        # Update last_login_at
        try:
            user_to_login.last_login_at = datetime.now(dt_timezone.utc) # type: ignore
        except SQLAlchemyError as e_sql_last_login:
            current_app.logger.error(f"Failed to set last_login_at for user {user_id_for_log}: {e_sql_last_login}", exc_info=True)
            
        try:
            db.session.commit() 
            current_app.logger.info(f"Successfully committed last_login_at and login_history for user {user_id_for_log}")
        except SQLAlchemyError as e_sql_commit_all:
            db.session.rollback() 
            current_app.logger.error(f"Failed to commit last_login_at/login_history for user {user_id_for_log}: {e_sql_commit_all}", exc_info=True)

        user_id_str_for_jwt = str(user_to_login.id) # type: ignore
        user_role_value_for_jwt = user_to_login.role.value # type: ignore

        jwt_payload = {"sub": user_id_str_for_jwt, "rl": user_role_value_for_jwt}
        access_token = create_access_token(data=jwt_payload)
        current_app.logger.info(f"JWT created for user {user_id_str_for_jwt} after OTP verification.")

        return jsonify(VerifyOtpResponseSchema(access_token=access_token, token_type="bearer").model_dump()), HTTPStatus.OK

    except ValidationError as e_val_verify_otp:
        error_details_log_verify_otp = []
        for error_item_verify_otp in e_val_verify_otp.errors():
            field_verify_otp = ".".join(str(loc) for loc in error_item_verify_otp['loc']) if error_item_verify_otp['loc'] else 'N/A'
            error_details_log_verify_otp.append(f"Field: {field_verify_otp}, Message: {error_item_verify_otp['msg']}, Type: {error_item_verify_otp['type']}")
        current_app.logger.warning(f"Verify OTP Pydantic validation failed for {phone_number_to_verify}: {'; '.join(error_details_log_verify_otp)}. Input: {request.json if request.is_json else 'Not JSON'}")
        return jsonify(AuthErrorResponseSchema(error="Input tidak valid.", details=e_val_verify_otp.errors()).model_dump()), HTTPStatus.UNPROCESSABLE_ENTITY
    except SQLAlchemyError as e_db_verify:
        if hasattr(db, 'session') and db.session.is_active: db.session.rollback()
        current_app.logger.error(f"Database error during OTP verification for {phone_number_to_verify}: {e_db_verify}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan server saat verifikasi OTP.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    except JWTError as e_jwt_verify:
        if hasattr(db, 'session') and db.session.is_active: db.session.rollback()
        current_app.logger.error(f"JWT creation error after OTP verification for user {phone_number_to_verify}: {e_jwt_verify}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Gagal memproses login setelah verifikasi OTP (token error).").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e_verify_otp:
        if hasattr(db, 'session') and db.session.is_active: db.session.rollback()
        current_app.logger.error(f"Unexpected error during OTP verification for {phone_number_to_verify}: {e_verify_otp}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan tidak terduga saat verifikasi OTP.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        current_app.logger.debug(f"Ending /verify-otp for {phone_number_to_verify}. User found: {user_id_for_log}, IP recorded: {client_ip_address if 'client_ip_address' in locals() else 'N/A'}")
        if hasattr(db, 'session'):
            db.session.remove()

# === Endpoint /logout ===
@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout_user(current_user_id: uuid.UUID):
    try:
        current_app.logger.info(f"User {current_user_id} initiated logout via POST /api/auth/logout.")
        return jsonify({"message": "Logout successful"}), HTTPStatus.OK
    except Exception as e_logout:
        current_app.logger.error(f"Error during logout for user {current_user_id}: {e_logout}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Kesalahan server saat logout.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        current_app.logger.debug(f"Ending /logout for user {current_user_id}.")
        if hasattr(db, 'session'):
            db.session.remove()

# === Endpoint /admin/login (BARU) ===
@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """Endpoint khusus untuk login admin menggunakan username (nomor telepon) dan password."""
    if not request.is_json:
        return jsonify(AuthErrorResponseSchema(error="Request body harus JSON.").model_dump()), HTTPStatus.BAD_REQUEST

    data = request.get_json()
    username_input = data.get('username')
    password = data.get('password')

    if not username_input or not password:
        return jsonify(AuthErrorResponseSchema(error="Username dan password wajib diisi.").model_dump()), HTTPStatus.BAD_REQUEST

    # --- PERBAIKAN UTAMA: Normalisasi nomor telepon sebelum query ---
    try:
        normalized_phone = validate_phone_number(username_input)
    except ValueError as e:
        current_app.logger.warning(f"Login admin gagal: Format username/telepon tidak valid. Input: '{username_input}'. Error: {e}")
        return jsonify(AuthErrorResponseSchema(error="Format nomor telepon tidak valid.").model_dump()), HTTPStatus.BAD_REQUEST
    # ----------------------------------------------------------------

    current_app.logger.info(f"Percobaan login admin oleh username: '{username_input}' (dinormalisasi menjadi: '{normalized_phone}')")

    try:
        # Gunakan nomor yang sudah dinormalisasi untuk mencari di database
        user_to_login = db.session.execute(
            db.select(User).filter(User.phone_number == normalized_phone)
        ).scalar_one_or_none()

        if (not user_to_login or 
            not user_to_login.is_admin_role or 
            not user_to_login.password_hash or 
            not check_password_hash(user_to_login.password_hash, password)):
            
            current_app.logger.warning(f"Login admin gagal untuk '{normalized_phone}'. Salah satu kondisi tidak terpenuhi.")
            return jsonify(AuthErrorResponseSchema(error="Username atau password salah.").model_dump()), HTTPStatus.UNAUTHORIZED

        # Jika lolos semua verifikasi
        user_id_str_for_jwt = str(user_to_login.id)
        user_role_value_for_jwt = user_to_login.role.value
        jwt_payload = {"sub": user_id_str_for_jwt, "rl": user_role_value_for_jwt}
        access_token = create_access_token(data=jwt_payload)
        
        current_app.logger.info(f"Login admin BERHASIL untuk user '{normalized_phone}' (ID: {user_id_str_for_jwt}).")
        return jsonify(VerifyOtpResponseSchema(access_token=access_token, token_type="bearer").model_dump()), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error tidak terduga saat proses login admin untuk '{username_input}': {e}", exc_info=True)
        return jsonify(AuthErrorResponseSchema(error="Terjadi kesalahan internal pada server.").model_dump()), HTTPStatus.INTERNAL_SERVER_ERROR