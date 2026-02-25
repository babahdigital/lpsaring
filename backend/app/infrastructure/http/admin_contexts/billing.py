from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from http import HTTPStatus

import midtransclient
import requests
from flask import current_app, jsonify, request


def _normalize_admin_payment_method(value: str | None) -> str | None:
    raw = str(value or '').strip().lower()
    if raw in {'qris', 'gopay', 'va', 'shopeepay'}:
        return raw
    return None


def _normalize_admin_va_bank(value: str | None) -> str | None:
    raw = str(value or '').strip().lower()
    if raw in {'bca', 'bni', 'bri', 'cimb', 'mandiri', 'permata'}:
        return raw
    return None


def _build_public_status_url(order_id: str) -> str:
    base = current_app.config.get('APP_PUBLIC_BASE_URL') or request.url_root
    base = str(base or '').strip() or request.url_root
    try:
        from app.services.transaction_status_link_service import generate_transaction_status_token

        token = generate_transaction_status_token(order_id)
        return f"{base.rstrip('/')}/payment/status?order_id={order_id}&t={token}"
    except Exception:
        return f"{base.rstrip('/')}/payment/status?order_id={order_id}"


def _build_admin_bill_order_id() -> str:
    prefix = str(current_app.config.get('ADMIN_BILL_ORDER_ID_PREFIX', 'BD-LPSR') or 'BD-LPSR').strip()
    if prefix == '':
        prefix = 'BD-LPSR'
    token = uuid.uuid4().hex[:12].upper()
    return f'{prefix}-{token}'


def _parse_csv_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip().lower() for p in text.split(',')]
    return [p for p in parts if p]


def _get_enabled_core_api_methods_for_admin(settings_service) -> list[str]:
    raw = settings_service.get_setting('CORE_API_ENABLED_PAYMENT_METHODS', None)
    selected = set(_parse_csv_values(raw))
    ordered = [m for m in ('qris', 'gopay', 'va', 'shopeepay') if m in selected]
    if ordered:
        return ordered
    return ['qris', 'gopay', 'va']


def _get_enabled_core_api_va_banks_for_admin(settings_service) -> list[str]:
    raw = settings_service.get_setting('CORE_API_ENABLED_VA_BANKS', None)
    selected = set(_parse_csv_values(raw))
    ordered = [b for b in ('bni', 'bca', 'bri', 'mandiri', 'permata', 'cimb') if b in selected]
    if ordered:
        return ordered
    return ['bni', 'bca', 'bri', 'mandiri', 'permata', 'cimb']


def _get_payment_provider_mode_for_admin(settings_service) -> str:
    raw = settings_service.get_setting('PAYMENT_PROVIDER_MODE', None)
    mode = str(raw or '').strip().lower()
    return 'core_api' if mode == 'core_api' else 'snap'


def create_bill_impl(
    *,
    db,
    current_admin,
    settings_service,
    User,
    Package,
    Transaction,
    TransactionStatus,
    AdminActionLog,
    AdminActionType,
    TransactionEvent,
    TransactionEventSource,
    format_to_local_phone,
    get_midtrans_snap_client,
    get_midtrans_core_api_client,
    safe_parse_midtrans_datetime,
    extract_qr_code_url,
    extract_va_number,
    extract_action_url,
    send_whatsapp_message,
):
    session = db.session
    json_data = request.get_json(silent=True) or {}

    error_id = uuid.uuid4().hex[:10].upper()

    user_id_raw = json_data.get('user_id')
    package_id_raw = json_data.get('package_id')
    if not user_id_raw or not package_id_raw:
        return jsonify({'message': 'user_id dan package_id wajib diisi.'}), HTTPStatus.BAD_REQUEST

    try:
        user_id = uuid.UUID(str(user_id_raw))
        package_id = uuid.UUID(str(package_id_raw))
    except ValueError:
        return jsonify({'message': 'Format user_id/package_id tidak valid.'}), HTTPStatus.BAD_REQUEST

    try:
        user = session.get(User, user_id)
        if user is None:
            return jsonify({'message': 'User tidak ditemukan.'}), HTTPStatus.NOT_FOUND

        package = session.get(Package, package_id)
        if package is None or not getattr(package, 'is_active', True):
            return jsonify({'message': 'Paket tidak valid atau tidak aktif.'}), HTTPStatus.BAD_REQUEST

        amount = int(getattr(package, 'price', 0) or 0)
        if amount <= 0:
            return jsonify({'message': 'Harga paket tidak valid.'}), HTTPStatus.BAD_REQUEST

        payment_method = _normalize_admin_payment_method(
            json_data.get('payment_method') or json_data.get('method') or json_data.get('payment_type')
        )
        if payment_method is None:
            payment_method = 'qris'

        provider_mode = _get_payment_provider_mode_for_admin(settings_service)

        enabled_methods = _get_enabled_core_api_methods_for_admin(settings_service)
        if payment_method not in set(enabled_methods):
            return (
                jsonify(
                    {
                        'message': 'Metode pembayaran ini tidak diaktifkan di pengaturan.',
                        'payment_method': payment_method,
                        'enabled_methods': enabled_methods,
                    }
                ),
                HTTPStatus.BAD_REQUEST,
            )

        va_bank = _normalize_admin_va_bank(json_data.get('va_bank') or json_data.get('bank'))
        if payment_method == 'va' and va_bank is None:
            va_bank = 'bni'

        enabled_va_banks = _get_enabled_core_api_va_banks_for_admin(settings_service)
        if payment_method == 'va' and va_bank not in set(enabled_va_banks):
            return (
                jsonify(
                    {
                        'message': 'Bank VA ini tidak diaktifkan di pengaturan Core API.',
                        'va_bank': va_bank,
                        'enabled_va_banks': enabled_va_banks,
                    }
                ),
                HTTPStatus.BAD_REQUEST,
            )

        order_id = _build_admin_bill_order_id()
        now_utc = datetime.now(dt_timezone.utc)
        try:
            expiry_minutes = int(current_app.config.get('MIDTRANS_DEFAULT_EXPIRY_MINUTES', 15))
        except Exception:
            expiry_minutes = 15
        expiry_minutes = max(5, min(expiry_minutes, 24 * 60))
        expiry_time = now_utc + timedelta(minutes=expiry_minutes)

        try:
            from app.services.transaction_status_link_service import generate_transaction_status_token

            status_token = generate_transaction_status_token(order_id)
            base = current_app.config.get('APP_PUBLIC_BASE_URL') or request.url_root
            base = str(base or '').strip() or request.url_root
            status_url = f"{base.rstrip('/')}/payment/status?order_id={order_id}&t={status_token}"
        except Exception:
            status_token = None
            status_url = _build_public_status_url(order_id)

        tx = Transaction()
        tx.id = uuid.uuid4()
        tx.user_id = user.id
        tx.package_id = package.id
        tx.midtrans_order_id = order_id
        tx.amount = amount
        tx.status = TransactionStatus.PENDING
        tx.expiry_time = expiry_time
        tx.payment_method = payment_method
        session.add(tx)

        core = None
        snap = None
        try:
            if provider_mode == 'snap':
                snap = get_midtrans_snap_client()
            else:
                core = get_midtrans_core_api_client()
        except ValueError as e_cfg:
            session.rollback()
            return (
                jsonify(
                    {
                        'message': 'Midtrans belum dikonfigurasi di server. Pastikan SERVER KEY (dan CLIENT KEY jika diperlukan) sudah terpasang.',
                        'details': str(e_cfg),
                    }
                ),
                HTTPStatus.BAD_REQUEST,
            )

        base_payload: dict[str, object] = {
            'transaction_details': {'order_id': order_id, 'gross_amount': amount},
            'item_details': [
                {
                    'id': str(package.id),
                    'price': amount,
                    'quantity': 1,
                    'name': str(getattr(package, 'name', 'Paket'))[:100],
                }
            ],
            'customer_details': {
                'first_name': str(getattr(user, 'full_name', None) or 'Pengguna')[:50],
                'phone': format_to_local_phone(getattr(user, 'phone_number', '') or ''),
            },
            'custom_expiry': {'expiry_duration': int(expiry_minutes), 'unit': 'minute'},
        }

        def _parse_midtrans_api_response_from_message(message: str) -> dict[str, object] | None:
            try:
                marker = 'API response: `'
                if marker in message:
                    json_part = message.split(marker, 1)[1]
                    json_part = json_part.split('`', 1)[0]
                    parsed = json.loads(json_part)
                    return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
            return None

        def _apply_charge_result_to_tx(resp: object) -> None:
            try:
                tx.midtrans_notification_payload = json.dumps(resp, ensure_ascii=False)
            except Exception:
                tx.midtrans_notification_payload = None

            if not isinstance(resp, dict):
                return

            transaction_id = resp.get('transaction_id')
            if isinstance(transaction_id, str):
                tx.midtrans_transaction_id = transaction_id

            expiry_time_raw = resp.get('expiry_time')
            expiry_time_str = expiry_time_raw if isinstance(expiry_time_raw, str) else None
            if parsed := safe_parse_midtrans_datetime(expiry_time_str):
                tx.expiry_time = parsed

            tx.qr_code_url = extract_qr_code_url(resp) or tx.qr_code_url

            deeplink = extract_action_url(resp, action_name_contains='deeplink-redirect')
            if deeplink:
                tx.snap_redirect_url = deeplink

            tx.va_number = extract_va_number(resp) or tx.va_number

            bill_key = resp.get('bill_key') or resp.get('mandiri_bill_key')
            biller_code = resp.get('biller_code')
            if bill_key:
                tx.payment_code = str(bill_key).strip()
            if biller_code:
                tx.biller_code = str(biller_code).strip()

            midtrans_status = str(resp.get('transaction_status') or '').strip().lower()
            if midtrans_status == 'pending':
                tx.status = TransactionStatus.PENDING
            elif midtrans_status in ('settlement', 'capture'):
                tx.status = TransactionStatus.SUCCESS

        attempted_payment_type = payment_method
        attempted_va_bank = va_bank
        fallback_used = False

        if provider_mode == 'snap':
            snap_params: dict[str, object] = {
                'transaction_details': {'order_id': order_id, 'gross_amount': amount},
                'item_details': [
                    {
                        'id': str(package.id),
                        'price': amount,
                        'quantity': 1,
                        'name': str(getattr(package, 'name', 'Paket') or 'Paket')[:100],
                    }
                ],
                'customer_details': {
                    'first_name': str(getattr(user, 'full_name', None) or 'Pengguna')[:50],
                    'phone': format_to_local_phone(getattr(user, 'phone_number', '') or ''),
                },
                'callbacks': {
                    'finish': (
                        f"{(current_app.config.get('APP_PUBLIC_BASE_URL') or request.url_root).rstrip('/')}/payment/status"
                        + (f"?t={status_token}" if status_token else '')
                    )
                },
            }

            if payment_method == 'qris':
                enabled_payments = ['qris']
                tx.payment_method = 'qris'
            elif payment_method == 'gopay':
                enabled_payments = ['gopay']
                tx.payment_method = 'gopay'
            elif payment_method == 'shopeepay':
                enabled_payments = ['shopeepay']
                tx.payment_method = 'shopeepay'
            else:
                bank = va_bank or 'bni'
                if bank == 'mandiri':
                    enabled_payments = ['echannel']
                    tx.payment_method = 'echannel'
                    snap_params['echannel'] = {
                        'bill_info1': 'Pembayaran Hotspot',
                        'bill_info2': str(getattr(package, 'name', 'Paket') or 'Paket')[:18],
                    }
                else:
                    enabled_payments = ['bank_transfer']
                    tx.payment_method = f'{bank}_va'
                    snap_params['bank_transfer'] = {'bank': bank}

            snap_params['enabled_payments'] = enabled_payments

            try:
                snap_response = snap.create_transaction(snap_params)  # type: ignore[union-attr]
            except requests.exceptions.RequestException as e_req:
                current_app.logger.error(
                    'Midtrans network error (snap create_transaction). error_id=%s order_id=%s err=%s',
                    error_id,
                    order_id,
                    e_req,
                    exc_info=True,
                )
                session.rollback()
                return (
                    jsonify(
                        {
                            'message': 'Midtrans tidak dapat diakses saat ini. Coba lagi beberapa saat.',
                            'error_id': error_id,
                        }
                    ),
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
            except midtransclient.error_midtrans.MidtransAPIError:
                raise

            snap_token = snap_response.get('token') if isinstance(snap_response, dict) else None
            redirect_url = snap_response.get('redirect_url') if isinstance(snap_response, dict) else None
            if not snap_token and not redirect_url:
                raise ValueError('Respons Midtrans Snap tidak valid.')

            tx.snap_token = str(snap_token).strip() if snap_token else None
            tx.snap_redirect_url = str(redirect_url).strip() if redirect_url else None
            tx.qr_code_url = None
            tx.va_number = None
            tx.payment_code = None
            tx.biller_code = None
            tx.status = TransactionStatus.UNKNOWN
        else:
            try:
                if payment_method == 'qris':
                    attempted_payment_type = 'qris'
                    charge_payload = {
                        **base_payload,
                        'payment_type': 'qris',
                        'qris': {'acquirer': 'gopay'},
                    }
                    charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]

                elif payment_method == 'gopay':
                    attempted_payment_type = 'gopay'
                    charge_payload = {
                        **base_payload,
                        'payment_type': 'gopay',
                        'gopay': {'enable_callback': True, 'callback_url': status_url},
                    }
                    charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]

                elif payment_method == 'shopeepay':
                    attempted_payment_type = 'shopeepay'
                    charge_payload = {
                        **base_payload,
                        'payment_type': 'shopeepay',
                        'shopeepay': {'callback_url': status_url},
                    }
                    charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]

                else:
                    bank = va_bank or 'bni'
                    attempted_payment_type = 'va'
                    attempted_va_bank = bank
                    if bank == 'mandiri':
                        tx.payment_method = 'echannel'
                        charge_payload = {
                            **base_payload,
                            'payment_type': 'echannel',
                            'echannel': {
                                'bill_info1': 'Pembayaran Hotspot',
                                'bill_info2': str(getattr(package, 'name', 'Paket') or 'Paket')[:18],
                            },
                        }
                        charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]
                    else:
                        tx.payment_method = f'{bank}_va'
                        charge_payload = {
                            **base_payload,
                            'payment_type': 'bank_transfer',
                            'bank_transfer': {'bank': bank},
                        }
                        charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]
            except midtransclient.error_midtrans.MidtransAPIError as e_charge:
                raw_message = getattr(e_charge, 'message', '') or ''
                parsed = _parse_midtrans_api_response_from_message(raw_message) or {}
                status_message = str(parsed.get('status_message') or '').strip()
                status_message_lower = status_message.lower()
                if payment_method == 'qris' and any(
                    needle in status_message_lower
                    for needle in (
                        'payment channel is not activated',
                        'payment channel is not active',
                        'not activated',
                        'not active',
                    )
                ):
                    current_app.logger.warning(
                        'Midtrans QRIS channel not active; fallback to GoPay Dynamic QRIS. order_id=%s',
                        order_id,
                    )
                    fallback_used = True
                    tx.payment_method = 'gopay'
                    attempted_payment_type = 'gopay'
                    charge_payload = {
                        **base_payload,
                        'payment_type': 'gopay',
                        'gopay': {'enable_callback': True, 'callback_url': status_url},
                    }
                    charge_resp = core.charge(charge_payload)  # type: ignore[union-attr]
                else:
                    raise

            _apply_charge_result_to_tx(charge_resp)

        disable_super_admin_logs = str(os.getenv('DISABLE_SUPER_ADMIN_ACTION_LOGS', 'false') or '').strip().lower() in {
            '1',
            'true',
            'yes',
            'y',
            'on',
        }
        if not (disable_super_admin_logs and current_admin.is_super_admin_role):
            try:
                try:
                    from flask import has_request_context, g

                    if has_request_context():
                        g.admin_action_logged = True
                except Exception:
                    pass
                expiry_time_val = tx.expiry_time
                log_entry = AdminActionLog()
                log_entry.admin_id = current_admin.id
                log_entry.target_user_id = user.id
                log_entry.action_type = AdminActionType.CREATE_QRIS_BILL
                log_entry.details = json.dumps(
                    {
                        'order_id': order_id,
                        'user_id': str(user.id),
                        'package_id': str(package.id),
                        'package_name': str(getattr(package, 'name', '') or ''),
                        'amount': amount,
                        'payment_method': tx.payment_method,
                        'requested_payment_method': payment_method,
                        'requested_va_bank': va_bank,
                        'qr_code_url': tx.qr_code_url,
                        'expiry_time': (expiry_time_val.isoformat() if expiry_time_val is not None else None),
                    },
                    default=str,
                    ensure_ascii=False,
                )
                session.add(log_entry)
            except Exception as e:
                current_app.logger.error(f'Gagal mencatat log CREATE_QRIS_BILL: {e}', exc_info=True)

        ev = TransactionEvent()
        ev.transaction_id = tx.id
        ev.source = TransactionEventSource.APP
        ev.event_type = 'ADMIN_QRIS_BILL_CREATED'
        ev.status = tx.status
        expiry_time = tx.expiry_time
        ev.payload = json.dumps(
            {
                'order_id': order_id,
                'user_id': str(user.id),
                'package_id': str(package.id),
                'amount': amount,
                'expiry_time': expiry_time.isoformat() if expiry_time is not None else None,
                'qr_code_url': tx.qr_code_url,
                'payment_method': tx.payment_method,
                'requested_payment_method': payment_method,
                'requested_va_bank': va_bank,
            },
            ensure_ascii=False,
        )
        session.add(ev)
        session.commit()

        phone_number = getattr(user, 'phone_number', '') or ''

        pkg_quota_gb = getattr(package, 'data_quota_gb', None)
        pkg_duration_days = getattr(package, 'duration_days', None)
        if pkg_quota_gb is None:
            quota_label = '-'
        elif pkg_quota_gb == 0:
            quota_label = 'Unlimited'
        else:
            quota_label = f'{pkg_quota_gb} GB'

        duration_label = f'{pkg_duration_days} Hari' if pkg_duration_days is not None else '-'

        method_label = (
            'QRIS'
            if payment_method == 'qris'
            else ('GoPay' if payment_method == 'gopay' else ('ShopeePay' if payment_method == 'shopeepay' else 'VA'))
        )
        caption_lines = [
            '📌 *Tagihan Pembelian Paket*',
            '',
            f"Nama: *{getattr(user, 'full_name', '') or 'Pengguna'}*",
            f"Paket: *{getattr(package, 'name', '') or 'Paket'}*",
            f'Kuota: *{quota_label}*',
            f'Masa aktif: *{duration_label}*',
            f'Harga: *Rp {amount:,}*',
            f'Invoice: *{order_id}*',
        ]

        if payment_method == 'va':
            bank_key = str(va_bank or 'bni').strip().lower()
            if str(tx.payment_method or '').strip().lower() == 'echannel':
                bank_key = 'mandiri'

            bank_label_map = {
                'bca': 'BCA',
                'bni': 'BNI',
                'bri': 'BRI',
                'mandiri': 'Mandiri',
                'permata': 'Permata',
                'cimb': 'CIMB Niaga',
            }
            caption_lines.append(f"Bank: *{bank_label_map.get(bank_key, bank_key.upper() or 'VA')}*")
        else:
            caption_lines.append(f'Metode: *{method_label}*')

        if payment_method == 'va':
            bank = (va_bank or 'bni').upper()
            if (va_bank or '') == 'mandiri' or str(tx.payment_method or '') == 'echannel':
                if tx.payment_code:
                    caption_lines.append(f'Bill Key: *{tx.payment_code}*')
                if tx.biller_code:
                    caption_lines.append(f'Biller Code: *{tx.biller_code}*')
            else:
                if tx.va_number:
                    caption_lines.append(f'VA {bank}: *{tx.va_number}*')

        caption_lines.extend(
            [
                '',
                f'Status & pembayaran: {status_url}',
            ]
        )
        if provider_mode == 'snap':
            caption_lines.append('Buka link status lalu klik tombol Bayar untuk melanjutkan pembayaran.')
        else:
            if payment_method == 'qris':
                caption_lines.append('Buka link status untuk menampilkan QR dan melakukan pembayaran.')
            elif payment_method == 'gopay':
                caption_lines.append('Buka link status lalu ikuti instruksi (tombol deeplink/QR jika tersedia).')
            elif payment_method == 'shopeepay':
                caption_lines.append('Buka link status lalu ikuti instruksi (tombol deeplink/QR jika tersedia).')
            else:
                caption_lines.append('Buka link status untuk melihat detail pembayaran dan status invoice.')

        sent = send_whatsapp_message(phone_number, '\n'.join(caption_lines))

        message = 'Tagihan berhasil dibuat.'
        if not sent:
            message = 'Tagihan berhasil dibuat, namun WhatsApp gagal terkirim (cek konfigurasi WA/nomor tujuan).'

        return (
            jsonify(
                {
                    'message': message,
                    'order_id': order_id,
                    'status': tx.status.value,
                    'qr_code_url': tx.qr_code_url,
                    'payment_method': tx.payment_method,
                    'status_url': status_url,
                    'whatsapp_sent': bool(sent),
                    'va_number': tx.va_number,
                    'payment_code': tx.payment_code,
                    'biller_code': tx.biller_code,
                }
            ),
            HTTPStatus.OK,
        )

    except midtransclient.error_midtrans.MidtransAPIError as e:
        session.rollback()
        raw_message = getattr(e, 'message', '') or ''
        current_app.logger.error(f'Midtrans error saat create QRIS bill: {raw_message}')

        midtrans_status_code: str | None = None
        midtrans_status_message: str | None = None
        midtrans_error_id: str | None = None

        try:
            marker = 'API response: `'
            if marker in raw_message:
                json_part = raw_message.split(marker, 1)[1]
                json_part = json_part.split('`', 1)[0]
                parsed = json.loads(json_part)
                if isinstance(parsed, dict):
                    if isinstance(parsed.get('status_code'), str):
                        midtrans_status_code = parsed.get('status_code')
                    if isinstance(parsed.get('status_message'), str):
                        midtrans_status_message = parsed.get('status_message')
                    if isinstance(parsed.get('id'), str):
                        midtrans_error_id = parsed.get('id')
        except Exception:
            pass

        is_prod = bool(current_app.config.get('MIDTRANS_IS_PRODUCTION', False))
        env_label = 'Production' if is_prod else 'Sandbox'

        user_message = 'Gagal membuat tagihan di Midtrans.'
        if midtrans_status_message:
            user_message = f'Gagal membuat tagihan di Midtrans: {midtrans_status_message}'
            if 'Payment channel is not activated' in midtrans_status_message:
                tried = attempted_payment_type if 'attempted_payment_type' in locals() else None
                used_fallback = fallback_used if 'fallback_used' in locals() else False

                if tried == 'gopay':
                    user_message += (
                        f' (Channel GoPay/QRIS Dinamis GoPay belum aktif di Midtrans {env_label} untuk Core API. '
                        'Jika sudah aktif di Dashboard namun masih ditolak, pastikan SERVER KEY yang digunakan sesuai environment.)'
                    )
                else:
                    user_message += (
                        f' (Channel Other QRIS belum aktif di Midtrans {env_label}. '
                        'Jika Anda memakai QRIS Dinamis GoPay, channel ini bisa saja tidak diaktifkan.)'
                    )

                if used_fallback:
                    user_message += ' Sudah dicoba fallback ke GoPay Dynamic QRIS, namun masih ditolak.'

        return jsonify(
            {
                'message': user_message,
                'midtrans_status_code': midtrans_status_code,
                'midtrans_status_message': midtrans_status_message,
                'midtrans_error_id': midtrans_error_id,
                'attempted_payment_type': (attempted_payment_type if 'attempted_payment_type' in locals() else None),
                'attempted_va_bank': (attempted_va_bank if 'attempted_va_bank' in locals() else None),
                'fallback_used': (fallback_used if 'fallback_used' in locals() else None),
            }
        ), HTTPStatus.BAD_REQUEST
    except Exception as e:
        session.rollback()
        current_app.logger.error(
            'Error create bill. error_id=%s err=%s',
            error_id,
            e,
            exc_info=True,
        )
        return (
            jsonify({'message': 'Terjadi kesalahan internal.', 'error_id': error_id}),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def midtrans_selftest_impl(*, current_admin, get_midtrans_core_api_client, format_to_local_phone, extract_qr_code_url):
    json_data = request.get_json(silent=True) or {}

    payment_types_raw = json_data.get('payment_types')
    if isinstance(payment_types_raw, list) and payment_types_raw:
        payment_types = [str(x).strip().lower() for x in payment_types_raw if str(x).strip()]
    else:
        payment_types = ['qris', 'gopay']

    try:
        amount = int(json_data.get('amount') or 1000)
    except Exception:
        amount = 1000
    amount = max(1000, min(amount, 50000))

    def _parse_midtrans_api_response_from_message(message: str) -> dict[str, object] | None:
        try:
            marker = 'API response: `'
            if marker in message:
                json_part = message.split(marker, 1)[1]
                json_part = json_part.split('`', 1)[0]
                parsed = json.loads(json_part)
                return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
        return None

    core = get_midtrans_core_api_client()
    results: list[dict[str, object]] = []
    for payment_type in payment_types:
        order_id = f'MT-TEST-{payment_type.upper()}-{uuid.uuid4().hex[:10].upper()}'
        payload: dict[str, object] = {
            'payment_type': payment_type,
            'transaction_details': {'order_id': order_id, 'gross_amount': amount},
            'item_details': [
                {
                    'id': f'selftest-{payment_type}',
                    'price': amount,
                    'quantity': 1,
                    'name': f'SelfTest {payment_type}'[:100],
                }
            ],
            'customer_details': {
                'first_name': (str(getattr(current_admin, 'full_name', '') or 'Admin')[:50]),
                'phone': format_to_local_phone(str(getattr(current_admin, 'phone_number', '') or '')),
            },
        }
        if payment_type == 'gopay':
            payload['gopay'] = {'enable_callback': False}

        try:
            resp = core.charge(payload)
            if isinstance(resp, dict):
                results.append(
                    {
                        'payment_type': payment_type,
                        'order_id': order_id,
                        'ok': True,
                        'status_code': resp.get('status_code'),
                        'status_message': resp.get('status_message'),
                        'transaction_status': resp.get('transaction_status'),
                        'transaction_id': resp.get('transaction_id'),
                        'qr_code_url': extract_qr_code_url(resp),
                        'raw': resp,
                    }
                )
            else:
                results.append({'payment_type': payment_type, 'order_id': order_id, 'ok': True, 'raw': resp})
        except midtransclient.error_midtrans.MidtransAPIError as e:
            raw_message = getattr(e, 'message', '') or ''
            parsed = _parse_midtrans_api_response_from_message(raw_message) or {}
            results.append(
                {
                    'payment_type': payment_type,
                    'order_id': order_id,
                    'ok': False,
                    'error': raw_message,
                    'midtrans_status_code': parsed.get('status_code'),
                    'midtrans_status_message': parsed.get('status_message'),
                    'midtrans_error_id': parsed.get('id'),
                }
            )

    return jsonify(
        {
            'is_production': bool(current_app.config.get('MIDTRANS_IS_PRODUCTION', False)),
            'amount': amount,
            'results': results,
        }
    ), HTTPStatus.OK
