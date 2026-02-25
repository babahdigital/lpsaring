import math
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from http import HTTPStatus
from typing import Optional

import sqlalchemy as sa
from flask import abort, current_app, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from werkzeug.exceptions import HTTPException

from app.infrastructure.db.models import ApprovalStatus, Package, Transaction, TransactionEventSource, TransactionStatus, User, UserQuotaDebt, UserRole
from app.infrastructure.http.error_envelope import error_response


class InitiateTransactionRequestSchema(BaseModel):
    package_id: uuid.UUID
    payment_method: Optional[str] = None
    va_bank: Optional[str] = None


class InitiateTransactionResponseSchema(BaseModel):
    snap_token: Optional[str] = Field(None, alias="snap_token")
    transaction_id: uuid.UUID = Field(..., alias="id")
    order_id: str = Field(..., alias="midtrans_order_id")
    redirect_url: Optional[str] = Field(None, alias="snap_redirect_url")
    payment_method: Optional[str] = Field(None, alias="payment_method")
    midtrans_transaction_id: Optional[str] = Field(None, alias="midtrans_transaction_id")
    expiry_time: Optional[datetime] = Field(None, alias="expiry_time")
    va_number: Optional[str] = Field(None, alias="va_number")
    payment_code: Optional[str] = Field(None, alias="payment_code")
    biller_code: Optional[str] = Field(None, alias="biller_code")
    qr_code_url: Optional[str] = Field(None, alias="qr_code_url")

    model_config = ConfigDict(from_attributes=True)


class InitiateDebtSettlementResponseSchema(BaseModel):
    snap_token: Optional[str] = Field(None, alias="snap_token")
    transaction_id: uuid.UUID = Field(..., alias="id")
    order_id: str = Field(..., alias="midtrans_order_id")
    redirect_url: Optional[str] = Field(None, alias="snap_redirect_url")
    payment_method: Optional[str] = Field(None, alias="payment_method")
    midtrans_transaction_id: Optional[str] = Field(None, alias="midtrans_transaction_id")
    expiry_time: Optional[datetime] = Field(None, alias="expiry_time")
    va_number: Optional[str] = Field(None, alias="va_number")
    payment_code: Optional[str] = Field(None, alias="payment_code")
    biller_code: Optional[str] = Field(None, alias="biller_code")
    qr_code_url: Optional[str] = Field(None, alias="qr_code_url")

    model_config = ConfigDict(from_attributes=True)


def initiate_transaction_impl(
    *,
    current_user_id: uuid.UUID,
    db,
    get_demo_package_ids,
    is_demo_user_eligible,
    get_payment_provider_mode,
    normalize_payment_method,
    normalize_va_bank,
    get_core_api_enabled_payment_methods,
    get_core_api_enabled_va_banks,
    is_core_api_method_enabled,
    is_core_api_va_bank_enabled,
    tx_has_snap_initiation_data,
    tx_has_core_initiation_data,
    tx_matches_requested_core_payment,
    log_transaction_event,
    generate_transaction_status_token,
    should_allow_call,
    get_midtrans_snap_client,
    get_midtrans_core_api_client,
    build_core_api_charge_payload,
    is_qr_payment_type,
    extract_qr_code_url,
    extract_va_number,
    extract_action_url,
    record_success,
    record_failure,
    format_to_local_phone,
):
    req_data_dict = request.get_json(silent=True) or {}
    try:
        req_data = InitiateTransactionRequestSchema.model_validate(req_data_dict)
    except ValidationError as e:
        return error_response(
            "Input tidak valid.",
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            details=e.errors(),
        )

    session = db.session
    try:
        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        package = session.query(Package).get(req_data.package_id)
        demo_package_ids = get_demo_package_ids()
        is_demo_package = package is not None and package.id in demo_package_ids
        can_use_demo_package = is_demo_package and is_demo_user_eligible(user)

        if not package or (not package.is_active and not can_use_demo_package):
            abort(HTTPStatus.BAD_REQUEST, description="Paket tidak valid atau tidak aktif.")

        try:
            debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
        except Exception:
            debt_total_mb = 0.0
        try:
            package_quota_gb = float(getattr(package, "data_quota_gb", 0) or 0)
        except Exception:
            package_quota_gb = 0.0
        package_quota_mb = int(package_quota_gb * 1024) if package_quota_gb and package_quota_gb > 0 else 0
        if (
            bool(getattr(user, "is_unlimited_user", False)) is False
            and getattr(user, "role", None) == UserRole.USER
            and debt_total_mb > 0
            and package_quota_mb > 0
        ):
            required_mb = int(math.ceil(debt_total_mb))
            if package_quota_mb <= required_mb:
                required_gb = round(required_mb / 1024.0, 2)
                abort(
                    HTTPStatus.BAD_REQUEST,
                    description=(
                        "Paket terlalu kecil karena Anda memiliki tunggakan kuota. "
                        f"Total tunggakan: {required_mb} MB (~{required_gb} GB). "
                        "Silakan pilih paket yang lebih besar agar sisa kuota menjadi positif."
                    ),
                )

        gross_amount = int(package.price or 0)

        provider_mode = get_payment_provider_mode()
        requested_method = normalize_payment_method(getattr(req_data, "payment_method", None))
        requested_va_bank = normalize_va_bank(getattr(req_data, "va_bank", None))

        enabled_core_methods: list[str] = []
        enabled_core_va_banks: list[str] = []
        if provider_mode == "core_api":
            enabled_core_methods = get_core_api_enabled_payment_methods()
            enabled_core_va_banks = get_core_api_enabled_va_banks()

            if requested_method is not None and not is_core_api_method_enabled(requested_method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            if requested_method == "va" and requested_va_bank is not None:
                if not is_core_api_va_bank_enabled(requested_va_bank, enabled_core_va_banks):
                    abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

        now_utc = datetime.now(dt_timezone.utc)

        existing_tx = (
            session.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .filter(Transaction.package_id == package.id)
            .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
            .filter(sa.or_(Transaction.expiry_time.is_(None), Transaction.expiry_time > now_utc))
            .order_by(Transaction.created_at.desc())
            .first()
        )
        if existing_tx:
            can_reuse = tx_has_snap_initiation_data(existing_tx) if provider_mode == "snap" else tx_has_core_initiation_data(existing_tx)
            if can_reuse and provider_mode == "core_api":
                if not tx_matches_requested_core_payment(
                    existing_tx,
                    requested_method=requested_method,
                    requested_va_bank=requested_va_bank,
                ):
                    existing_tx.status = TransactionStatus.CANCELLED
                    log_transaction_event(
                        session=session,
                        transaction=existing_tx,
                        source=TransactionEventSource.APP,
                        event_type="CANCELLED_BY_NEW_INITIATE",
                        status=existing_tx.status,
                        payload={
                            "order_id": existing_tx.midtrans_order_id,
                            "requested_method": requested_method,
                            "requested_va_bank": requested_va_bank,
                            "reason": "requested_payment_mismatch",
                        },
                    )
                    session.commit()
                    can_reuse = False

            if can_reuse:
                log_transaction_event(
                    session=session,
                    transaction=existing_tx,
                    source=TransactionEventSource.APP,
                    event_type="INITIATE_REUSED_EXISTING",
                    status=existing_tx.status,
                    payload={
                        "order_id": existing_tx.midtrans_order_id,
                        "package_id": str(existing_tx.package_id),
                        "amount": int(existing_tx.amount or 0),
                        "expiry_time": existing_tx.expiry_time.isoformat() if existing_tx.expiry_time else None,
                        "provider_mode": provider_mode,
                        "snap_token_present": bool(existing_tx.snap_token),
                        "redirect_url": existing_tx.snap_redirect_url,
                        "qr_code_url_present": bool(getattr(existing_tx, "qr_code_url", None)),
                        "va_number_present": bool(getattr(existing_tx, "va_number", None)),
                        "reason": "existing_active_transaction",
                    },
                )
                session.commit()
                response_data = InitiateTransactionResponseSchema.model_validate(existing_tx, from_attributes=True)
                payload = response_data.model_dump(by_alias=False, exclude_none=True)
                payload["provider_mode"] = provider_mode
                try:
                    base_callback_url = (
                        current_app.config.get("APP_PUBLIC_BASE_URL")
                        or current_app.config.get("FRONTEND_URL")
                        or current_app.config.get("APP_LINK_USER")
                    )
                    if base_callback_url:
                        status_token = generate_transaction_status_token(existing_tx.midtrans_order_id)
                        payload["status_token"] = status_token
                        payload["status_url"] = (
                            f"{str(base_callback_url).rstrip('/')}/payment/status?order_id={existing_tx.midtrans_order_id}&t={status_token}"
                        )
                except Exception:
                    pass
                return jsonify(payload), HTTPStatus.OK

        order_prefix = str(current_app.config.get("MIDTRANS_ORDER_ID_PREFIX", "BD-LPSR")).strip()
        order_prefix = order_prefix.strip("-")
        if not order_prefix:
            order_prefix = "BD-LPSR"
        order_id = f"{order_prefix}-{uuid.uuid4().hex[:12].upper()}"
        status_token = generate_transaction_status_token(order_id)

        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        local_expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        new_transaction = Transaction()
        new_transaction.id = uuid.uuid4()
        new_transaction.user_id = user.id
        new_transaction.package_id = package.id
        new_transaction.midtrans_order_id = order_id
        new_transaction.amount = gross_amount
        new_transaction.status = TransactionStatus.UNKNOWN
        new_transaction.expiry_time = local_expiry_time

        base_callback_url = (
            current_app.config.get("APP_PUBLIC_BASE_URL")
            or current_app.config.get("FRONTEND_URL")
            or current_app.config.get("APP_LINK_USER")
        )
        if not base_callback_url:
            current_app.logger.error("APP_PUBLIC_BASE_URL/FRONTEND_URL/APP_LINK_USER belum dikonfigurasi.")
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="APP_PUBLIC_BASE_URL belum dikonfigurasi.")
        finish_url_base = f"{base_callback_url.rstrip('/')}/payment/finish"

        status_url = f"{base_callback_url.rstrip('/')}/payment/status?order_id={order_id}&t={status_token}"
        finish_url_base_with_token = f"{finish_url_base}?t={status_token}"
        finish_url = status_url

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Midtrans sementara tidak tersedia.")

        snap_token: str | None = None
        redirect_url: str | None = None

        if provider_mode == "snap":
            snap_params = {
                "transaction_details": {"order_id": order_id, "gross_amount": gross_amount},
                "item_details": [{"id": str(package.id), "price": gross_amount, "quantity": 1, "name": package.name[:100]}],
                "customer_details": {
                    "first_name": user.full_name or "Pengguna",
                    "phone": format_to_local_phone(user.phone_number),
                },
                "callbacks": {"finish": finish_url_base_with_token},
            }

            snap = get_midtrans_snap_client()
            snap_response = snap.create_transaction(snap_params)
            record_success("midtrans")

            snap_token = snap_response.get("token")
            redirect_url = snap_response.get("redirect_url")
            if not snap_token and not redirect_url:
                raise ValueError("Respons Midtrans tidak valid.")

            new_transaction.snap_token = snap_token
            new_transaction.snap_redirect_url = redirect_url
            new_transaction.status = TransactionStatus.UNKNOWN
        else:
            method = requested_method or (enabled_core_methods[0] if enabled_core_methods else "qris")
            if enabled_core_methods and not is_core_api_method_enabled(method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            va_bank = requested_va_bank
            if method == "va":
                if enabled_core_va_banks:
                    if va_bank is None:
                        va_bank = "bni" if "bni" in enabled_core_va_banks else enabled_core_va_banks[0]
                    elif not is_core_api_va_bank_enabled(va_bank, enabled_core_va_banks):
                        abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

            core_api = get_midtrans_core_api_client()
            charge_payload = build_core_api_charge_payload(
                order_id=order_id,
                gross_amount=gross_amount,
                item_id=str(package.id),
                item_name=str(package.name or "Paket"),
                customer_name=str(user.full_name or "Pengguna"),
                customer_phone=(format_to_local_phone(user.phone_number) or ""),
                expiry_minutes=expiry_minutes,
                finish_url=finish_url,
                method=method,
                va_bank=va_bank,
            )

            charge_response = core_api.charge(charge_payload)
            record_success("midtrans")

            payment_type = str(charge_response.get("payment_type") or "").strip().lower() or None
            midtrans_trx_id = charge_response.get("transaction_id")

            new_transaction.midtrans_transaction_id = str(midtrans_trx_id).strip() if midtrans_trx_id else None
            new_transaction.snap_token = None
            new_transaction.snap_redirect_url = None
            new_transaction.status = TransactionStatus.PENDING

            if method == "va":
                bank = va_bank or "bni"
                if bank == "mandiri" or payment_type == "echannel":
                    new_transaction.payment_method = "echannel"
                    bill_key = charge_response.get("bill_key") or charge_response.get("mandiri_bill_key")
                    biller_code = charge_response.get("biller_code")
                    new_transaction.payment_code = str(bill_key).strip() if bill_key else None
                    new_transaction.biller_code = str(biller_code).strip() if biller_code else None
                else:
                    new_transaction.payment_method = f"{bank}_va"
                    new_transaction.va_number = extract_va_number(charge_response)
            else:
                new_transaction.payment_method = payment_type or method

            if method in {"gopay", "shopeepay"}:
                deeplink = extract_action_url(charge_response, action_name_contains="deeplink-redirect")
                if deeplink:
                    new_transaction.snap_redirect_url = deeplink

            if is_qr_payment_type(payment_type or method):
                new_transaction.qr_code_url = extract_qr_code_url(charge_response)
            else:
                new_transaction.qr_code_url = None

        expiry_time = new_transaction.expiry_time

        log_transaction_event(
            session=session,
            transaction=new_transaction,
            source=TransactionEventSource.APP,
            event_type="INITIATED",
            status=new_transaction.status,
            payload={
                "order_id": order_id,
                "package_id": str(package.id),
                "amount": gross_amount,
                "expiry_time": expiry_time.isoformat() if expiry_time is not None else None,
                "provider_mode": provider_mode,
                "requested_method": requested_method,
                "requested_va_bank": requested_va_bank,
                "snap_token_present": bool(snap_token),
                "redirect_url": redirect_url,
                "finish_url": finish_url,
                "qr_code_url_present": bool(getattr(new_transaction, "qr_code_url", None)),
                "va_number_present": bool(getattr(new_transaction, "va_number", None)),
            },
        )

        session.add(new_transaction)
        session.commit()

        response_data = InitiateTransactionResponseSchema.model_validate(new_transaction, from_attributes=True)
        payload = response_data.model_dump(by_alias=False, exclude_none=True)
        payload["provider_mode"] = provider_mode
        payload["status_token"] = status_token
        payload["status_url"] = status_url
        return jsonify(payload), HTTPStatus.OK

    except HTTPException:
        raise
    except Exception as e:
        record_failure("midtrans")
        db.session.rollback()
        current_app.logger.error(f"Error di initiate_transaction: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
    finally:
        db.session.remove()


def initiate_debt_settlement_transaction_impl(
    *,
    current_user_id: uuid.UUID,
    db,
    log_transaction_event,
    get_payment_provider_mode,
    normalize_payment_method,
    normalize_va_bank,
    get_core_api_enabled_payment_methods,
    get_core_api_enabled_va_banks,
    is_core_api_method_enabled,
    is_core_api_va_bank_enabled,
    estimate_debt_rp_for_mb,
    estimate_user_debt_rp,
    get_debt_order_prefixes,
    encode_uuid_base64url,
    encode_uuid_base32,
    tx_has_snap_initiation_data,
    tx_has_core_initiation_data,
    get_primary_debt_order_prefix,
    generate_transaction_status_token,
    should_allow_call,
    get_midtrans_snap_client,
    get_midtrans_core_api_client,
    build_core_api_charge_payload,
    extract_va_number,
    extract_action_url,
    is_qr_payment_type,
    extract_qr_code_url,
    record_success,
    record_failure,
    format_to_local_phone,
):
    session = db.session
    try:
        req_data = request.get_json(silent=True) or {}
        manual_debt_id_raw = req_data.get("manual_debt_id")
        manual_debt_id: uuid.UUID | None = None
        if manual_debt_id_raw is not None:
            try:
                manual_debt_id = uuid.UUID(str(manual_debt_id_raw))
            except Exception:
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="manual_debt_id tidak valid.")

        provider_mode = get_payment_provider_mode()
        requested_method = normalize_payment_method(req_data.get("payment_method"))
        requested_va_bank = normalize_va_bank(req_data.get("va_bank"))

        enabled_core_methods: list[str] = []
        enabled_core_va_banks: list[str] = []
        if provider_mode == "core_api":
            enabled_core_methods = get_core_api_enabled_payment_methods()
            enabled_core_va_banks = get_core_api_enabled_va_banks()

            if requested_method is not None and not is_core_api_method_enabled(requested_method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            if requested_method == "va" and requested_va_bank is not None:
                if not is_core_api_va_bank_enabled(requested_va_bank, enabled_core_va_banks):
                    abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

        user = session.get(User, current_user_id)
        if not user or not user.is_active or user.approval_status != ApprovalStatus.APPROVED:
            abort(HTTPStatus.FORBIDDEN, description="Akun Anda belum aktif atau disetujui untuk melakukan transaksi.")

        if bool(getattr(user, "is_unlimited_user", False)):
            abort(HTTPStatus.BAD_REQUEST, description="Pengguna unlimited tidak memiliki tunggakan kuota.")

        debt_total_mb = float(getattr(user, "quota_debt_total_mb", 0) or 0)
        if debt_total_mb <= 0:
            abort(HTTPStatus.BAD_REQUEST, description="Tidak ada tunggakan kuota untuk dilunasi.")

        manual_item = None
        manual_item_remaining_mb = 0.0
        if manual_debt_id is not None:
            manual_item = (
                session.query(UserQuotaDebt)
                .filter(UserQuotaDebt.id == manual_debt_id)
                .filter(UserQuotaDebt.user_id == user.id)
                .first()
            )
            if manual_item is None:
                abort(HTTPStatus.NOT_FOUND, description="Hutang manual tidak ditemukan.")
            try:
                amount = int(getattr(manual_item, "amount_mb", 0) or 0)
                paid = int(getattr(manual_item, "paid_mb", 0) or 0)
            except Exception:
                amount = 0
                paid = 0
            manual_item_remaining_mb = float(max(0, amount - paid))
            if manual_item_remaining_mb <= 0:
                abort(HTTPStatus.BAD_REQUEST, description="Hutang manual tersebut sudah lunas.")

        gross_amount = int((estimate_debt_rp_for_mb(manual_item_remaining_mb) if manual_debt_id is not None else estimate_user_debt_rp(user)) or 0)
        if gross_amount <= 0:
            abort(
                HTTPStatus.SERVICE_UNAVAILABLE,
                description="Estimasi tunggakan belum tersedia. Silakan hubungi admin atau coba lagi nanti.",
            )

        now_utc = datetime.now(dt_timezone.utc)
        try:
            expiry_minutes = int(current_app.config.get("MIDTRANS_DEFAULT_EXPIRY_MINUTES", 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        local_expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        debt_prefixes = get_debt_order_prefixes()
        debt_like_filters = [Transaction.midtrans_order_id.like(f"{p}-%") for p in debt_prefixes]

        existing_tx_query = (
            session.query(Transaction)
            .filter(Transaction.user_id == user.id)
            .filter(sa.or_(*debt_like_filters))
            .filter(Transaction.status.in_([TransactionStatus.UNKNOWN, TransactionStatus.PENDING]))
            .filter(sa.or_(Transaction.expiry_time.is_(None), Transaction.expiry_time > now_utc))
            .order_by(Transaction.created_at.desc())
        )

        if manual_debt_id is not None:
            manual_uuid = str(manual_debt_id)
            manual_hex = str(getattr(manual_debt_id, "hex", "") or "").upper()
            manual_b64 = encode_uuid_base64url(manual_debt_id)
            manual_b32 = encode_uuid_base32(manual_debt_id)
            manual_like_filters: list[sa.ColumnElement[bool]] = []
            for p in debt_prefixes:
                manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_uuid}%"))
                if manual_hex:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_hex}%"))
                if manual_b64:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_b64}%"))
                if manual_b32:
                    manual_like_filters.append(Transaction.midtrans_order_id.like(f"{p}-{manual_b32}%"))
            existing_tx_query = existing_tx_query.filter(sa.or_(*manual_like_filters))

        existing_tx = existing_tx_query.first()
        if existing_tx:
            can_reuse = tx_has_snap_initiation_data(existing_tx) if provider_mode == "snap" else tx_has_core_initiation_data(existing_tx)
            if can_reuse:
                response_data = InitiateDebtSettlementResponseSchema.model_validate(existing_tx, from_attributes=True)
                payload = response_data.model_dump(by_alias=False, exclude_none=True)
                payload["provider_mode"] = provider_mode
                try:
                    status_token = generate_transaction_status_token(existing_tx.midtrans_order_id)
                    base_callback_url = (
                        current_app.config.get("APP_PUBLIC_BASE_URL")
                        or current_app.config.get("FRONTEND_URL")
                        or current_app.config.get("APP_LINK_USER")
                        or ""
                    )
                    if base_callback_url:
                        payload["status_token"] = status_token
                        payload["status_url"] = (
                            f"{str(base_callback_url).rstrip('/')}/payment/status?order_id={existing_tx.midtrans_order_id}&t={status_token}"
                        )
                except Exception:
                    pass
                return jsonify(payload), HTTPStatus.OK

        debt_prefix = get_primary_debt_order_prefix()
        if manual_debt_id is not None:
            manual_core = encode_uuid_base64url(manual_debt_id)
            order_id = f"{debt_prefix}-{manual_core}~{uuid.uuid4().hex[:4].upper()}"
        else:
            order_id = f"{debt_prefix}-{uuid.uuid4().hex[:12].upper()}"

        status_token = generate_transaction_status_token(order_id)

        new_transaction = Transaction()
        new_transaction.id = uuid.uuid4()
        new_transaction.user_id = user.id
        new_transaction.package_id = None
        new_transaction.midtrans_order_id = order_id
        new_transaction.amount = int(gross_amount)
        new_transaction.status = TransactionStatus.UNKNOWN
        new_transaction.expiry_time = local_expiry_time

        base_callback_url = (
            current_app.config.get("APP_PUBLIC_BASE_URL")
            or current_app.config.get("FRONTEND_URL")
            or current_app.config.get("APP_LINK_USER")
        )
        if not base_callback_url:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="APP_PUBLIC_BASE_URL belum dikonfigurasi.")
        finish_url_base = f"{base_callback_url.rstrip('/')}/payment/finish"
        status_url = f"{base_callback_url.rstrip('/')}/payment/status?order_id={order_id}&purpose=debt&t={status_token}"
        finish_url_base_with_token = f"{finish_url_base}?t={status_token}"
        finish_url = status_url

        if not should_allow_call("midtrans"):
            abort(HTTPStatus.SERVICE_UNAVAILABLE, description="Midtrans sementara tidak tersedia.")

        item_name = "Pelunasan Tunggakan Kuota" if manual_debt_id is None else "Pelunasan Hutang Manual"

        snap_token: str | None = None
        redirect_url: str | None = None

        if provider_mode == "snap":
            snap_params = {
                "transaction_details": {"order_id": order_id, "gross_amount": int(gross_amount)},
                "item_details": [
                    {
                        "id": "DEBT_SETTLEMENT",
                        "price": int(gross_amount),
                        "quantity": 1,
                        "name": item_name[:100],
                    }
                ],
                "customer_details": {
                    "first_name": user.full_name or "Pengguna",
                    "phone": format_to_local_phone(user.phone_number),
                },
                "callbacks": {"finish": finish_url_base_with_token},
            }

            snap = get_midtrans_snap_client()
            snap_response = snap.create_transaction(snap_params)
            record_success("midtrans")

            snap_token = snap_response.get("token")
            redirect_url = snap_response.get("redirect_url")
            if not snap_token and not redirect_url:
                raise ValueError("Respons Midtrans tidak valid.")

            new_transaction.snap_token = snap_token
            new_transaction.snap_redirect_url = redirect_url
            new_transaction.status = TransactionStatus.UNKNOWN
        else:
            method = requested_method or (enabled_core_methods[0] if enabled_core_methods else "qris")
            if enabled_core_methods and not is_core_api_method_enabled(method, enabled_core_methods):
                abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Metode pembayaran tidak tersedia.")

            va_bank = requested_va_bank
            if method == "va":
                if enabled_core_va_banks:
                    if va_bank is None:
                        va_bank = "bni" if "bni" in enabled_core_va_banks else enabled_core_va_banks[0]
                    elif not is_core_api_va_bank_enabled(va_bank, enabled_core_va_banks):
                        abort(HTTPStatus.UNPROCESSABLE_ENTITY, description="Bank VA tidak tersedia.")

            core_api = get_midtrans_core_api_client()
            charge_payload = build_core_api_charge_payload(
                order_id=order_id,
                gross_amount=int(gross_amount),
                item_id="DEBT_SETTLEMENT",
                item_name=item_name,
                customer_name=str(user.full_name or "Pengguna"),
                customer_phone=(format_to_local_phone(user.phone_number) or ""),
                expiry_minutes=expiry_minutes,
                finish_url=finish_url,
                method=method,
                va_bank=va_bank,
            )
            charge_response = core_api.charge(charge_payload)
            record_success("midtrans")

            payment_type = str(charge_response.get("payment_type") or "").strip().lower() or None
            midtrans_trx_id = charge_response.get("transaction_id")
            new_transaction.midtrans_transaction_id = str(midtrans_trx_id).strip() if midtrans_trx_id else None
            new_transaction.snap_token = None
            new_transaction.snap_redirect_url = None
            new_transaction.status = TransactionStatus.PENDING

            if method == "va":
                bank = va_bank or "bni"
                if bank == "mandiri" or payment_type == "echannel":
                    new_transaction.payment_method = "echannel"
                    bill_key = charge_response.get("bill_key") or charge_response.get("mandiri_bill_key")
                    biller_code = charge_response.get("biller_code")
                    new_transaction.payment_code = str(bill_key).strip() if bill_key else None
                    new_transaction.biller_code = str(biller_code).strip() if biller_code else None
                else:
                    new_transaction.payment_method = f"{bank}_va"
                    new_transaction.va_number = extract_va_number(charge_response)
            else:
                new_transaction.payment_method = payment_type or method

            if method in {"gopay", "shopeepay"}:
                deeplink = extract_action_url(charge_response, action_name_contains="deeplink-redirect")
                if deeplink:
                    new_transaction.snap_redirect_url = deeplink

            if is_qr_payment_type(payment_type or method):
                new_transaction.qr_code_url = extract_qr_code_url(charge_response)
            else:
                new_transaction.qr_code_url = None

        expiry_time = new_transaction.expiry_time

        log_transaction_event(
            session=session,
            transaction=new_transaction,
            source=TransactionEventSource.APP,
            event_type="DEBT_INITIATED",
            status=new_transaction.status,
            payload={
                "order_id": order_id,
                "amount": int(gross_amount),
                "debt_total_mb": float(debt_total_mb),
                "expiry_time": expiry_time.isoformat() if expiry_time is not None else None,
                "provider_mode": provider_mode,
                "requested_method": requested_method,
                "requested_va_bank": requested_va_bank,
                "snap_token_present": bool(snap_token),
                "redirect_url": redirect_url,
                "finish_url": finish_url,
                "qr_code_url_present": bool(getattr(new_transaction, "qr_code_url", None)),
                "va_number_present": bool(getattr(new_transaction, "va_number", None)),
            },
        )

        session.add(new_transaction)
        session.commit()

        response_data = InitiateDebtSettlementResponseSchema.model_validate(new_transaction, from_attributes=True)
        payload = response_data.model_dump(by_alias=False, exclude_none=True)
        payload["provider_mode"] = provider_mode
        payload["status_token"] = status_token
        payload["status_url"] = status_url
        return jsonify(payload), HTTPStatus.OK
    except HTTPException:
        raise
    except Exception as e:
        record_failure("midtrans")
        session.rollback()
        current_app.logger.error("Error di initiate_debt_settlement_transaction: %s", e, exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description=str(e))
    finally:
        db.session.remove()
