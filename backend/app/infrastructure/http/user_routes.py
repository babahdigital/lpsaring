# backend/app/infrastructure/http/user_routes.py
# VERSI: Penambahan endpoint /me/login-history dan perbaikan minor

from flask import Blueprint, request, jsonify, current_app, abort
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, desc, func, cast
import uuid
from typing import Optional, List, Dict, Any
from datetime import date, timedelta, datetime, timezone as dt_timezone
from dateutil.relativedelta import relativedelta
import secrets
import string
import enum

from app.extensions import db
# Impor model yang relevan
try:
    from app.infrastructure.db.models import (
        User, DailyUsageLog, Transaction, TransactionStatus, Package,
        UserRole, ApprovalStatus, UserBlok, UserKamar,
        UserLoginHistory # Pastikan UserLoginHistory diimpor
    )
except ImportError:
    # Placeholder jika import gagal
    User, DailyUsageLog, Transaction, TransactionStatus, Package = None, None, None, None, None # type: ignore
    UserLoginHistory = None # type: ignore
    class UserRole(str, enum.Enum): USER = "USER"; ADMIN = "ADMIN"; SUPER_ADMIN = "SUPER_ADMIN" # type: ignore
    class ApprovalStatus(str, enum.Enum): PENDING_APPROVAL = "PENDING_APPROVAL"; APPROVED = "APPROVED"; REJECTED = "REJECTED" # type: ignore
    class UserBlok(str, enum.Enum): A="A"; B="B"; C="C"; D="D"; E="E"; F="F" # type: ignore
    class UserKamar(str, enum.Enum): Kamar_1="1"; Kamar_2="2"; Kamar_3="3"; Kamar_4="4"; Kamar_5="5"; Kamar_6 = "6" # type: ignore
    print("WARNING: Gagal mengimpor model dari app.infrastructure.db.models di user_routes.py")


# Impor skema dari file schemas yang sudah diperbaiki
from .schemas.user_schemas import (
    PhoneCheckRequest, PhoneCheckResponse, UserQuotaResponse, WeeklyUsageResponse,
    MonthlyUsageResponse, MonthlyUsageData,
    UserProfileResponseSchema,
    UserProfileUpdateRequestSchema
)

# Import helper dari transaction_routes (dengan penanganan error)
try:
    from .transactions_routes import (
        get_midtrans_core_api_client,
        safe_parse_midtrans_datetime,
        extract_va_number,
        extract_qr_code_url
    )
    print("INFO: Helper transaksi berhasil diimpor dari .transactions_routes ke user_routes.")
except ImportError as e_tx_helper:
    print(f"WARNING: Gagal mengimpor helper transaksi ke user_routes: {e_tx_helper}. Fitur terkait mungkin error.")
    def get_midtrans_core_api_client(): raise NotImplementedError("Helper get_midtrans_core_api_client tidak ditemukan") # type: ignore
    def safe_parse_midtrans_datetime(dt): raise NotImplementedError("Helper safe_parse_midtrans_datetime tidak ditemukan") # type: ignore
    def extract_va_number(data): raise NotImplementedError("Helper extract_va_number tidak ditemukan") # type: ignore
    def extract_qr_code_url(data): raise NotImplementedError("Helper extract_qr_code_url tidak ditemukan") # type: ignore

# Import decorator token_required (dengan penanganan error)
try:
    from .decorators import token_required
    print("INFO: Decorator @token_required berhasil diimpor dari .auth_routes ke user_routes.")
except ImportError:
    try:
        from ..utils.decorators import token_required # type: ignore
        print("INFO: Decorator @token_required berhasil diimpor dari ..utils.decorators ke user_routes.")
    except ImportError:
        import functools
        print("CRITICAL WARNING: Gagal mengimpor @token_required. Menggunakan DUMMY decorator di user_routes! AUTH TIDAK AMAN.")
        def token_required(f): # type: ignore
            @functools.wraps(f) # type: ignore
            def decorated_function(*args, **kwargs): # type: ignore
                # Dummy implementation - JANGAN GUNAKAN DI PRODUKSI
                user_id_from_header = request.headers.get('X-User-ID-For-Testing-UserRoutes')
                if user_id_from_header:
                    try:
                        print(f"WARNING: Using dummy auth with User ID from header: {user_id_from_header}")
                        return f(current_user_id=uuid.UUID(user_id_from_header), *args, **kwargs) # type: ignore
                    except ValueError:
                        abort(401, description="Format User ID di header tidak valid (dummy auth user_routes).")
                else:
                    # Coba ambil user pertama sebagai fallback testing (SANGAT TIDAK AMAN)
                    if db and User: # type: ignore
                        test_user = db.session.query(User).order_by(User.created_at.desc()).first() # type: ignore
                        if test_user and hasattr(test_user, 'id'):
                             print(f"WARNING: Using dummy auth, fallback to first user found: {test_user.id}")
                             return f(current_user_id=test_user.id, *args, **kwargs) # type: ignore
                    abort(401, description="Autentikasi diperlukan (dummy decorator user_routes).")
            return decorated_function # type: ignore

# --- Import Fungsi Klien (dengan penanganan error) ---
try:
    from app.infrastructure.gateways.mikrotik_client import (
        get_mikrotik_connection,
        activate_or_update_hotspot_user,
        update_mikrotik_user_password,
        format_to_local_phone
    )
    print("INFO: Fungsi Mikrotik berhasil diimpor ke user_routes.")

    from app.infrastructure.gateways.whatsapp_client import send_whatsapp_message
    print("INFO: Fungsi WhatsApp berhasil diimpor ke user_routes.")

except ImportError as e_client_func:
    print(f"CRITICAL ERROR: Gagal mengimpor fungsi dari gateway client di user_routes: {e_client_func}.")
    def format_to_local_phone(phone): return phone # type: ignore # Dummy
    def update_mikrotik_user_password(pool, username, password): return False, "Not implemented" # type: ignore # Dummy
    def send_whatsapp_message(to, body): print(f"DUMMY WA to {to}: {body}"); return False # type: ignore # Dummy
    def get_mikrotik_connection(): return None # type: ignore # Dummy
    def activate_or_update_hotspot_user(pool, username, profile, password, comment): return False, "Not implemented" # type: ignore # Dummy
# -----------------------------------------------------

# --- DEFINISI BLUEPRINT ---
users_bp = Blueprint('users_api', __name__, url_prefix='/api/users')
# --------------------------

# --- Helper Fungsi Generate Password (NUMERIK) ---
def generate_random_password(length=6):
    """Generates a random numeric password of specified length."""
    numeric_alphabet = string.digits
    password = ''.join(secrets.choice(numeric_alphabet) for _ in range(length)) # Menggunakan secrets untuk keamanan lebih
    return password
# ---------------------------------------------

# --- Endpoint /check-or-register (TETAP SAMA, tidak membuat user baru) ---
@users_bp.route('/check-or-register', methods=['POST'])
def check_or_register_phone():
    current_app.logger.info("POST /api/users/check-or-register endpoint requested.")
    try:
        json_data = request.get_json(silent=True)
        if not json_data:
             current_app.logger.warning("[Check Phone] Request body is empty or not JSON.")
             return jsonify({"success": False, "message": "Request body tidak boleh kosong dan harus JSON."}), 400
        req_data = PhoneCheckRequest.model_validate(json_data)
        phone_number = req_data.phone_number # Sudah diformat +62 oleh validator
        full_name = req_data.full_name # Opsional
        current_app.logger.debug(f"[Check Phone] Request validated for: {phone_number}, Name: {full_name}")
    except ValidationError as e:
        current_app.logger.warning(f"[Check Phone] Invalid payload: {e.errors()}")
        return jsonify({"success": False, "message": "Data input tidak valid.", "details": e.errors()}), 422
    except Exception as e:
         current_app.logger.warning(f"[Check Phone] Failed to parse request JSON: {e}", exc_info=True)
         return jsonify({"success": False, "message": "Format request tidak valid."}), 400

    user: Optional[User] = None # type: ignore
    try:
        user = db.session.execute(select(User).filter_by(phone_number=phone_number)).scalar_one_or_none() # type: ignore

        if not user:
            user_exists = False
            current_app.logger.info(f"[Check Phone] Nomor {phone_number} belum terdaftar.")
            # Sesuai alur baru, endpoint ini tidak mendaftarkan user
            return jsonify(PhoneCheckResponse(user_exists=False, message="Nomor telepon belum terdaftar.").model_dump()), 200
        else:
            user_exists = True
            current_app.logger.info(f"[Check Phone] Pengguna ditemukan untuk nomor {phone_number} (ID: {user.id})")
            # Update nama jika pengguna ada tapi belum punya nama, dan nama diberikan di request
            if not user.full_name and full_name:
                 try:
                      user.full_name = full_name
                      db.session.commit()
                      current_app.logger.info(f"[Check Phone] Nama pengguna {user.id} diupdate menjadi: {full_name}")
                 except SQLAlchemyError as e_update:
                      db.session.rollback()
                      current_app.logger.error(f"[Check Phone] Gagal update nama untuk user {user.id}: {e_update}", exc_info=True)
                      # Tetap lanjutkan respons sukses, update nama tidak kritikal di sini
            return jsonify(PhoneCheckResponse(user_exists=True, user_id=user.id).model_dump()), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"[Check Phone] Error database untuk nomor {phone_number}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal proses database (check-or-register)."}), 500
    except Exception as e:
        if db.session.is_active: db.session.rollback()
        current_app.logger.error(f"[Check Phone] Error tidak terduga untuk nomor {phone_number}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Kesalahan internal server (check-or-register)."}), 500
# --------------------------------------------------------------------------

# --- Endpoint /me/quota (TETAP SAMA) ---
@users_bp.route('/me/quota', methods=['GET'])
@token_required
def get_my_quota_status(current_user_id):
    current_app.logger.info(f"GET /api/users/me/quota requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        current_app.logger.warning(f"[Quota] User {user_uuid} dari token tidak ditemukan.")
        abort(404, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
        current_app.logger.warning(f"[Quota] User {user_uuid} tidak aktif/approved. Status: active={user.is_active}, approval={user.approval_status}")
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat kuota.")

    try:
        purchased_mb = int(user.total_quota_purchased_mb or 0)
        used_mb = int(user.total_quota_used_mb or 0)
        remaining_mb = max(0, purchased_mb - used_mb)
        hotspot_username = user.phone_number # Gunakan nomor telepon sebagai username hotspot
        last_sync_time = user.updated_at # Atau field lain yang relevan

        quota_data = UserQuotaResponse(
            total_quota_purchased_mb=purchased_mb,
            total_quota_used_mb=used_mb,
            remaining_mb=remaining_mb,
            hotspot_username=hotspot_username,
            last_sync_time=last_sync_time
        )
        return jsonify(quota_data.model_dump(mode='json')), 200
    except Exception as e:
        current_app.logger.error(f"[Quota] Error saat memproses data kuota user {user_uuid}: {e}", exc_info=True)
        abort(500, description="Gagal memproses data kuota.")
# ------------------------------------

# --- Endpoint /me/weekly-usage (TETAP SAMA) ---
@users_bp.route('/me/weekly-usage', methods=['GET'])
@token_required
def get_my_weekly_usage(current_user_id):
    current_app.logger.info(f"GET /api/users/me/weekly-usage requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        abort(404, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat riwayat penggunaan.")

    try:
        today = date.today()
        start_date = today - timedelta(days=6) # 7 hari termasuk hari ini

        stmt = select(DailyUsageLog.log_date, DailyUsageLog.usage_mb)\
            .where(DailyUsageLog.user_id == user_uuid,  # type: ignore
                   DailyUsageLog.log_date >= start_date,
                   DailyUsageLog.log_date <= today)\
            .order_by(DailyUsageLog.log_date.asc())

        usage_logs = db.session.execute(stmt).all()
        # Buat dictionary untuk lookup cepat
        usage_dict = {log.log_date: float(log.usage_mb or 0.0) for log in usage_logs}

        # Generate data 7 hari, isi 0 jika tidak ada log
        weekly_data_points = []
        for i in range(7):
            current_date = start_date + timedelta(days=i)
            usage = usage_dict.get(current_date, 0.0)
            weekly_data_points.append(max(0.0, usage)) # Pastikan tidak negatif

        return jsonify(WeeklyUsageResponse(weekly_data=weekly_data_points).model_dump()), 200
    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[Weekly Usage] Error database user {user_uuid}: {e_sql}", exc_info=True)
        abort(500, description="Gagal mengambil data penggunaan mingguan dari database.")
    except Exception as e:
        current_app.logger.error(f"[Weekly Usage] Error proses user {user_uuid}: {e}", exc_info=True)
        abort(500, description="Gagal memproses data penggunaan mingguan.")
# ------------------------------------

# --- Endpoint /me/monthly-usage (REVISI FINAL - Logika Saran Pertama: Selalu N Bulan Terakhir) ---
@users_bp.route('/me/monthly-usage', methods=['GET'])
@token_required
def get_my_monthly_usage(current_user_id):
    """
    Mengambil data penggunaan bulanan pengguna.
    Selalu menampilkan data untuk N bulan terakhir (default 12),
    mengisi 0 untuk bulan tanpa data atau sebelum pengguna terdaftar.
    """
    current_app.logger.info(f"GET /api/users/me/monthly-usage requested by user ID: {current_user_id}. Logic: Always N months lookback.")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        abort(404, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat riwayat penggunaan.")

    # Tentukan jumlah bulan maksimal untuk dilihat ke belakang
    try:
        num_months_to_show = int(request.args.get('months', 12)) # type: ignore
    except ValueError:
        num_months_to_show = 12
    num_months_to_show = min(max(num_months_to_show, 1), 24) # Batasi 1-24 bulan

    # --- Tentukan Rentang Waktu ---
    today = date.today()
    first_day_of_current_month = today.replace(day=1)
    # Hitung tanggal awal berdasarkan parameter 'months' (mundur dari sekarang)
    # INI AKAN MENJADI TITIK AWAL LOOP GENERASI DATA
    start_month_date_for_loop = first_day_of_current_month - relativedelta(months=(num_months_to_show - 1))
    current_app.logger.debug(f"[Monthly Usage] Chart requested range: {start_month_date_for_loop.strftime('%Y-%m')} to {first_day_of_current_month.strftime('%Y-%m')} ({num_months_to_show} months)")
    # -------------------------------------------------------

    # Tentukan bulan pertama user terdaftar (untuk efisiensi query)
    user_registration_month_start = None
    if user.created_at:
        try:
            user_created_at_utc = user.created_at.astimezone(dt_timezone.utc) if user.created_at.tzinfo else user.created_at.replace(tzinfo=dt_timezone.utc)
            user_registration_date = user_created_at_utc.date()
            user_registration_month_start = user_registration_date.replace(day=1)
            current_app.logger.debug(f"[Monthly Usage] User registration month start: {user_registration_month_start.strftime('%Y-%m')}")
        except Exception as e_tz:
             current_app.logger.error(f"[Monthly Usage] Error processing user created_at for query filter: {e_tz}. Proceeding without registration date filter.", exc_info=True)
             user_registration_month_start = None

    # --- Query Database ---
    month_year_col = func.to_char(DailyUsageLog.log_date, 'YYYY-MM').label('month_year') # type: ignore
    # Tentukan tanggal mulai filter query: ambil data dari awal periode loop
    # ATAU dari bulan registrasi, mana saja yang lebih awal, untuk menangkap semua data relevan
    query_filter_start_date = min(start_month_date_for_loop, user_registration_month_start) if user_registration_month_start else start_month_date_for_loop

    stmt = select(
            month_year_col,
            func.sum(DailyUsageLog.usage_mb).label('total_usage_mb') # type: ignore
        )\
        .where(
            DailyUsageLog.user_id == user_uuid,  # type: ignore
            DailyUsageLog.log_date >= query_filter_start_date, # Query data dari tanggal yang relevan
            DailyUsageLog.log_date <= today
        )\
        .group_by(month_year_col)\
        .order_by(month_year_col.asc())

    try:
        monthly_results = db.session.execute(stmt).all()
        usage_by_month_dict: Dict[str, float] = {
            row.month_year: float(row.total_usage_mb or 0.0) for row in monthly_results
        }
        current_app.logger.debug(f"[Monthly Usage] DB query results (count: {len(usage_by_month_dict)}): {usage_by_month_dict}")
    except SQLAlchemyError as e_sql:
         current_app.logger.error(f"[Monthly Usage] Database query error for user {user_uuid}: {e_sql}", exc_info=True)
         abort(500, description="Gagal mengambil data penggunaan bulanan dari database.")
    # ----------------------

    # --- Generate Data Lengkap untuk Periode (Selalu N Bulan Terakhir) ---
    monthly_data_list: List[MonthlyUsageData] = []
    # Mulai loop dari tanggal awal periode N bulan lalu
    current_loop_date = start_month_date_for_loop
    months_processed = 0

    while current_loop_date <= first_day_of_current_month and months_processed < num_months_to_show:
        month_year_str = current_loop_date.strftime('%Y-%m')
        # Ambil data dari hasil query jika ada untuk bulan ini, jika tidak, default 0
        usage = usage_by_month_dict.get(month_year_str, 0.0)
        usage = max(0.0, usage) # Pastikan tidak negatif

        monthly_data_list.append(MonthlyUsageData(month_year=month_year_str, usage_mb=usage))

        # Maju ke bulan berikutnya
        current_loop_date += relativedelta(months=1)
        months_processed += 1

    final_data_log = {item.month_year: item.usage_mb for item in monthly_data_list}
    current_app.logger.debug(f"[Monthly Usage] Generated final data list for response (count: {len(monthly_data_list)}): {final_data_log}")
    # --------------------------------------------------------------------------

    # Kirim respons
    try:
        response_payload = MonthlyUsageResponse(monthly_data=monthly_data_list).model_dump(mode='json')
        return jsonify(response_payload), 200
    except Exception as e_resp:
         current_app.logger.error(f"[Monthly Usage] Error serializing final response for user {user_uuid}: {e_resp}", exc_info=True)
         abort(500, description="Gagal memformat data respons penggunaan bulanan.")
# -----------------------------------------------------------------------

# --- API Endpoint: GET Riwayat Transaksi Pengguna (TETAP SAMA) ---
@users_bp.route('/me/transactions', methods=['GET'])
@token_required
def get_my_transactions(current_user_id):
    current_app.logger.info(f"GET /api/users/me/transactions requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        abort(404, description="Pengguna tidak ditemukan.")
    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat riwayat transaksi.")

    try:
        page = request.args.get('page', 1, type=int) # type: ignore
        per_page = min(request.args.get('per_page', 10, type=int), 50) # type: ignore
        sort_by = request.args.get('sort_by', 'created_at') # type: ignore
        sort_order = request.args.get('sort_order', 'desc').lower() # type: ignore

        valid_sort_keys = {
            'created_at': Transaction.created_at, 'amount': Transaction.amount, # type: ignore
            'status': Transaction.status, 'updated_at': Transaction.updated_at, # type: ignore
            'package_name': Package.name, 'payment_method': Transaction.payment_method # type: ignore
        }
        sort_column = valid_sort_keys.get(sort_by, Transaction.created_at) # type: ignore
        query_order = desc(sort_column) if sort_order == 'desc' else sort_column.asc()

        query = db.session.query(Transaction, Package.name, Package.price)\
            .join(Package, Transaction.package_id == Package.id)\
            .filter(Transaction.user_id == user_uuid)\
            .order_by(query_order) # type: ignore

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        transactions_data = []
        def safe_isoformat(dt_obj: Optional[datetime]) -> Optional[str]:
            return dt_obj.isoformat() if isinstance(dt_obj, (datetime, date)) else None
        def safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
            return getattr(obj, attr, default) if obj else default

        for tx_obj, pkg_name_val, pkg_price_val in pagination.items:
            transactions_data.append({
                'id': str(tx_obj.id), 'midtrans_order_id': tx_obj.midtrans_order_id,
                'package_name': pkg_name_val or 'N/A',
                'package_price': float(pkg_price_val) if pkg_price_val is not None else None,
                'amount': float(tx_obj.amount) if tx_obj.amount is not None else None,
                'status': tx_obj.status.name if tx_obj.status else TransactionStatus.UNKNOWN.name, # type: ignore
                'payment_method': tx_obj.payment_method,
                'created_at': safe_isoformat(tx_obj.created_at),
                'updated_at': safe_isoformat(tx_obj.updated_at),
                'payment_expiry_time': safe_isoformat(safe_getattr(tx_obj, 'expiry_time')),
                'payment_settlement_time': safe_isoformat(safe_getattr(tx_obj, 'payment_time')),
                'payment_va_number': safe_getattr(tx_obj, 'va_number'),
                'payment_biller_code': safe_getattr(tx_obj, 'biller_code'),
                'payment_bill_key': safe_getattr(tx_obj, 'payment_code'), # alias untuk payment_code
                'qr_code_url': safe_getattr(tx_obj, 'qr_code_url')
            })

        response_payload = {
            'success': True, 'transactions': transactions_data,
            'pagination': {
                'page': pagination.page, 'per_page': pagination.per_page,
                'total_pages': pagination.pages, 'total_items': pagination.total,
                'has_prev': pagination.has_prev, 'has_next': pagination.has_next,
                'prev_num': pagination.prev_num if pagination.has_prev else None,
                'next_num': pagination.next_num if pagination.has_next else None
            }
        }
        return jsonify(response_payload), 200
    except SQLAlchemyError as e_sql:
         current_app.logger.error(f"[Transactions] Error database user {user_uuid}: {e_sql}", exc_info=True)
         abort(500, description="Gagal mengambil riwayat transaksi dari database.")
    except Exception as e:
        current_app.logger.error(f"[Transactions] Error proses user {user_uuid}: {e}", exc_info=True)
        abort(500, description="Gagal memproses data riwayat transaksi.")
# -----------------------------------------------------------

# --- API Endpoint Profil Pengguna (GET & PUT) (TETAP SAMA) ---
@users_bp.route('/me/profile', methods=['GET', 'PUT'])
@token_required
def handle_my_profile(current_user_id):
    user_uuid = current_user_id
    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        current_app.logger.warning(f"[Profile] User {user_uuid} dari token tidak ditemukan.")
        abort(404, description="Pengguna tidak ditemukan.")

    # GET Method
    if request.method == 'GET':
        current_app.logger.info(f"GET /api/users/me/profile by user ID: {user_uuid}")
        if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
            current_app.logger.warning(f"[Profile GET] User {user_uuid} tidak aktif/approved.")
            abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat profil.")
        try:
            # Menggunakan UserMeResponseSchema yang mewarisi UserResponseSchema (sudah pakai Enum)
            profile_data = UserProfileResponseSchema.model_validate(user)
            return jsonify(profile_data.model_dump(mode='json')), 200
        except Exception as e:
            current_app.logger.error(f"[Profile GET] Error serialisasi profil user {user_uuid}: {e}", exc_info=True)
            abort(500, description=f"Error mengambil data profil: {str(e)}")

    # PUT Method
    elif request.method == 'PUT':
        current_app.logger.info(f"PUT /api/users/me/profile by user ID: {user_uuid}")
        if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
            current_app.logger.warning(f"[Profile PUT] User {user_uuid} tidak aktif/approved.")
            abort(403, description="Akun Anda belum aktif atau belum disetujui untuk mengubah profil.")

        # PERIKSA PERAN: Hanya USER yang bisa update via endpoint ini
        if user.role != UserRole.USER: # type: ignore
            current_app.logger.warning(f"[Profile PUT] User {user_uuid} (role: {user.role}) mencoba update profil via endpoint /me/profile.")
            abort(403, description="Endpoint ini hanya untuk pengguna biasa (USER). Admin harus menggunakan endpoint/tools lain.")

        json_data = request.get_json(silent=True)
        if not json_data:
            return jsonify({"success": False, "message": "Request body tidak boleh kosong."}), 400

        try:
            # Gunakan skema yang sudah diupdate
            update_data = UserProfileUpdateRequestSchema.model_validate(json_data)
            user_updated = False

            if update_data.full_name is not None and user.full_name != update_data.full_name:
                user.full_name = update_data.full_name
                user_updated = True

            # PERUBAHAN: Logika untuk update blok dan kamar (bisa di-set menjadi NULL)
            if user.blok != update_data.blok:
                user.blok = update_data.blok
                user_updated = True
            
            if user.kamar != update_data.kamar:
                user.kamar = update_data.kamar
                user_updated = True

            if user_updated:
                db.session.commit()
                current_app.logger.info(f"[Profile PUT] Profil user {user_uuid} berhasil diupdate.")
                # PERBAIKAN: Gunakan UserMeResponseSchema untuk konsistensi respons
                resp_data = UserMeResponseSchema.model_validate(user)
                return jsonify(resp_data.model_dump(mode='json')), 200
            else:

                current_app.logger.info(f"[Profile PUT] Tidak ada perubahan data untuk user {user_uuid}.")
                # Tetap kembalikan data terbaru sebagai konfirmasi
                resp_data = UserProfileResponseSchema.model_validate(user)
                return jsonify(resp_data.model_dump(mode='json')), 200

        except ValidationError as e:
            current_app.logger.warning(f"[Profile PUT] Validasi Pydantic gagal untuk user {user_uuid}: {e.errors()}")
            return jsonify({"success": False, "message": "Data input tidak valid.", "details": e.errors()}), 422
        except SQLAlchemyError as e_sql: # Tangkap error DB lain sebelum commit
            if db.session.is_active: db.session.rollback()
            current_app.logger.error(f"[Profile PUT] Error database (sebelum commit) user {user_uuid}: {e_sql}", exc_info=True)
            abort(500, description="Kesalahan database saat memproses update profil.")
        except Exception as e:
            if db.session.is_active: db.session.rollback()
            current_app.logger.error(f"[Profile PUT] Error tidak terduga user {user_uuid}: {e}", exc_info=True)
            abort(500, description="Kesalahan internal saat update profil.")

    # Jika method bukan GET atau PUT
    return abort(405) # Method Not Allowed
# -----------------------------------------------------------

# --- API Endpoint Reset Password Hotspot (TETAP SAMA) ---
@users_bp.route('/me/reset-hotspot-password', methods=['POST'])
@token_required
def reset_my_hotspot_password(current_user_id):
    current_app.logger.info(f"POST /api/users/me/reset-hotspot-password requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid) # type: ignore
    if not user:
        current_app.logger.warning(f"[Reset Pass] User {user_uuid} dari token tidak ditemukan.")
        abort(404, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED: # type: ignore
        current_app.logger.warning(f"[Reset Pass] User {user_uuid} tidak aktif/approved.")
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk mereset password hotspot.")

    mikrotik_username = user.phone_number # Asumsi username adalah nomor telepon
    if not mikrotik_username:
        current_app.logger.error(f"[Reset Pass] User {user_uuid} tidak memiliki phone_number. Tidak bisa reset.")
        return jsonify({"success": False, "message": "Data pengguna tidak lengkap (nomor telepon tidak ada)."}), 500

    # Generate password BARU 6 digit numerik
    new_password_numeric = generate_random_password(length=6) # Memanggil fungsi yang sudah disesuaikan
    current_app.logger.info(f"[Reset Pass] Generate password numerik baru '{new_password_numeric}' untuk user {mikrotik_username} (ID: {user_uuid}).")

    mikrotik_conn_pool = None
    mt_update_success = False
    mt_update_message = "Gagal mendapatkan koneksi Mikrotik."
    try:
        mikrotik_conn_pool = get_mikrotik_connection()
        if not mikrotik_conn_pool:
            current_app.logger.error("[Reset Pass] Gagal mendapatkan Mikrotik connection pool.")
        else:
            # Fungsi update_mikrotik_user_password mungkin perlu penyesuaian jika belum menerima pool
            # atau jika menggunakan parameter yang berbeda.
            # Untuk saat ini, asumsikan update_mikrotik_user_password sudah bisa menangani ini.
            # Jika tidak, kita bisa menggunakan activate_or_update_hotspot_user.
            # Kita akan gunakan activate_or_update_hotspot_user untuk konsistensi.

            # Ambil default profile jika diperlukan oleh activate_or_update_hotspot_user
            default_profile = current_app.config.get('MIKROTIK_DEFAULT_PROFILE', 'default')
            kamar_val_for_comment = user.kamar.value if user.kamar and hasattr(user.kamar, 'value') else 'N/A'
            blok_val_for_comment = user.blok.value if user.blok and hasattr(user.blok, 'value') else 'N/A'
            comment_for_mikrotik = f"Password Reset: {user.full_name or 'N/A'} | Blk {blok_val_for_comment} Km {kamar_val_for_comment} | ID:{str(user.id)[:8]}"

            mt_update_success, mt_update_message = activate_or_update_hotspot_user( # type: ignore
                connection_pool=mikrotik_conn_pool,
                user_db_id=str(user.id),
                mikrotik_profile_name=default_profile, # Atau profile spesifik jika ada untuk user
                hotspot_password=new_password_numeric,
                comment=comment_for_mikrotik
            )
            if not mt_update_success:
                current_app.logger.error(f"[Reset Pass] Gagal update password di MikroTik untuk {mikrotik_username}: {mt_update_message}")
            else:
                current_app.logger.info(f"[Reset Pass] Berhasil update password di MikroTik untuk {mikrotik_username}")

    except NameError as ne: # Jika fungsi Mikrotik tidak terimpor
        mt_update_message = "Komponen Mikrotik tidak tersedia."
        current_app.logger.critical(f"[Reset Pass] Fungsi Mikrotik tidak tersedia: {ne}.")
    except KeyError as ke: # Jika konfigurasi Mikrotik kurang
        mt_update_message = f"Konfigurasi Mikrotik tidak lengkap ({str(ke)})."
        current_app.logger.error(f"[Reset Pass] {mt_update_message}")
    except Exception as e_mt:
        mt_update_message = f"Error koneksi/update Mikrotik: {str(e_mt)}"
        current_app.logger.error(f"[Reset Pass] Error Mikrotik untuk user {mikrotik_username}: {e_mt}", exc_info=True)

    if not mt_update_success:
         return jsonify({"success": False, "message": f"Gagal update password di sistem hotspot: {mt_update_message}"}), 500

    # Jika berhasil di Mikrotik, simpan password baru (plain text) ke DB
    try:
        user.mikrotik_password = new_password_numeric
        db.session.commit()
        current_app.logger.info(f"[Reset Pass] Berhasil update mikrotik_password (plain) di DB untuk user {user_uuid}.")
    except SQLAlchemyError as e_db:
        if db.session.is_active: db.session.rollback()
        current_app.logger.error(f"[Reset Pass] Error DB simpan password baru user {user_uuid}: {e_db}", exc_info=True)
        return jsonify({"success": True, "message": "Password hotspot telah diperbarui di sistem, tapi gagal sinkronisasi ke akun Anda. Silakan coba login hotspot dengan password baru.", "new_password_for_testing": new_password_numeric if current_app.debug else None}), 207

    # Kirim notifikasi WA
    notification_success = False
    if user.phone_number:
        try:
            username_for_wa_display = format_to_local_phone(mikrotik_username) or mikrotik_username # type: ignore
            message_body = f"Hai {user.full_name or 'Pengguna'}, Password hotspot Anda telah direset. Username: {username_for_wa_display}, Password baru: {new_password_numeric}. Harap simpan baik-baik."
            notification_success = send_whatsapp_message(user.phone_number, message_body) # type: ignore
            if not notification_success:
                current_app.logger.error(f"[Reset Pass] Fungsi send_whatsapp_message gagal mengirim notifikasi ke {user.phone_number}.")
            else:
                current_app.logger.info(f"[Reset Pass] Notifikasi reset password berhasil dikirim via WhatsApp ke {user.phone_number}")
        # ... (blok except seperti sebelumnya) ...
        except NameError as ne_wa:
             current_app.logger.error(f"[Reset Pass] Fungsi WhatsApp tidak tersedia: {ne_wa}. Notifikasi WA gagal.")
        except KeyError as ke_wa:
            current_app.logger.error(f"[Reset Pass] Konfigurasi WhatsApp tidak lengkap ({str(ke_wa)}). Tidak bisa kirim notifikasi.")
        except Exception as e_wa:
            current_app.logger.error(f"[Reset Pass] Error mengirim notifikasi WhatsApp ke {user.phone_number}: {e_wa}", exc_info=True)
    else:
        current_app.logger.info(f"[Reset Pass] User {user_uuid} tidak memiliki nomor telepon, notifikasi WhatsApp dilewati.")

    final_message = "Password hotspot (hanya angka) berhasil direset."
    if user.phone_number:
        if notification_success:
            final_message += " Password baru telah dikirim via WhatsApp."
        else:
            final_message += f" Namun, gagal mengirim notifikasi WhatsApp. Password baru Anda adalah: {new_password_numeric}"
    else:
        final_message += f" Password baru Anda adalah: {new_password_numeric}"

    return jsonify({"success": True, "message": final_message, "new_password_for_testing": new_password_numeric if current_app.debug else None}), 200

# --- API Endpoint: GET Ringkasan Pengeluaran Mingguan Pengguna ---
@users_bp.route('/me/weekly-spending', methods=['GET'])
@token_required
def get_my_weekly_spending_summary(current_user_id):
    current_app.logger.info(f"GET /api/users/me/weekly-spending requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    user = db.session.get(User, user_uuid)
    if not user:
        current_app.logger.warning(f"[WeeklySpending] User {user_uuid} dari token tidak ditemukan.")
        abort(404, description="Pengguna tidak ditemukan.")

    if not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
        current_app.logger.warning(f"[WeeklySpending] User {user_uuid} tidak aktif/approved. Status: active={user.is_active}, approval={user.approval_status}")
        abort(403, description="Akun Anda belum aktif atau belum disetujui untuk melihat ringkasan pengeluaran.")

    try:
        today = date.today()
        day_names_id = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"]
        categories = []
        daily_spending_data = []
        total_this_week = 0.0
        
        for i in range(7): # Loop dari 0 (6 hari lalu) hingga 6 (hari ini)
            current_date_in_loop = today - timedelta(days=(6 - i)) # Mulai dari 6 hari yang lalu
            categories.append(day_names_id[current_date_in_loop.weekday()])

            date_column_to_use = Transaction.payment_time 
            
            daily_total_query = db.session.query(func.sum(Transaction.amount))\
                .filter(
                    Transaction.user_id == user_uuid,
                    Transaction.status == TransactionStatus.SUCCESS,
                    func.date(date_column_to_use) == current_date_in_loop
                ).scalar()
            
            daily_total = float(daily_total_query or 0.0)
            daily_spending_data.append(daily_total)
            total_this_week += daily_total
        
        current_app.logger.debug(f"[WeeklySpending] User {user_uuid}: Categories: {categories}, SeriesData: {daily_spending_data}, Total: {total_this_week}")

        response_data = {
            "success": True,
            "categories": categories,
            "series": [{"name": "Pengeluaran", "data": daily_spending_data}],
            "total_this_week": total_this_week
        }
        return jsonify(response_data), 200

    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[WeeklySpending] Error database user {user_uuid}: {e_sql}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal mengambil data pengeluaran mingguan dari database."}), 500
    except Exception as e:
        current_app.logger.error(f"[WeeklySpending] Error proses user {user_uuid}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal memproses data pengeluaran mingguan."}), 500

# --- API Endpoint: GET Riwayat Login Pengguna ---
@users_bp.route('/me/login-history', methods=['GET'])
@token_required
def get_my_login_history(current_user_id):
    current_app.logger.info(f"GET /api/users/me/login-history requested by user ID: {current_user_id}")
    user_uuid = current_user_id

    # Validasi apakah model UserLoginHistory sudah terimpor
    if UserLoginHistory is None: # type: ignore
        current_app.logger.error("[LoginHistory] Model UserLoginHistory tidak tersedia (kemungkinan gagal import).")
        return jsonify({"success": False, "message": "Fitur riwayat login tidak tersedia saat ini karena kesalahan konfigurasi server."}), 503 # Service Unavailable

    try:
        limit_str = request.args.get('limit', '7') # Ambil sebagai string dulu
        try:
            limit = int(limit_str)
        except ValueError:
            current_app.logger.warning(f"[LoginHistory] Invalid limit parameter '{limit_str}'. Defaulting to 7.")
            limit = 7
            
        limit = min(max(limit, 1), 20) # Batasi antara 1 dan 20 untuk performa

        current_app.logger.debug(f"[LoginHistory] Fetching last {limit} login records for user {user_uuid}.")

        login_records = db.session.query(UserLoginHistory)\
            .filter(UserLoginHistory.user_id == user_uuid)\
            .order_by(UserLoginHistory.login_time.desc())\
            .limit(limit)\
            .all()
            
        current_app.logger.debug(f"[LoginHistory] Found {len(login_records)} login records for user {user_uuid}.")

        history_data = []
        for record in login_records:
            history_data.append({
                # Pastikan login_time tidak None sebelum memanggil isoformat
                "login_time": record.login_time.isoformat() if record.login_time else None,
                "ip_address": record.ip_address,
                "user_agent_string": record.user_agent_string
            })
            
        return jsonify({"success": True, "history": history_data}), 200

    except SQLAlchemyError as e_sql:
        current_app.logger.error(f"[LoginHistory] DB error for user {user_uuid}: {e_sql}", exc_info=True)
        return jsonify({"success": False, "message": "Gagal mengambil riwayat akses dari database."}), 500
    except Exception as e:
        current_app.logger.error(f"[LoginHistory] Error proses untuk user {user_uuid}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Terjadi kesalahan saat memproses riwayat akses."}), 500