from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus

from flask import abort, current_app, make_response, render_template, request


def _format_dt_local(value: datetime | None, *, get_local_tz, with_seconds: bool = False) -> str:
    if not value:
        return '-'
    try:
        if getattr(value, 'tzinfo', None) is None:
            return '-'
        local_tz = get_local_tz()
        local_dt = value.astimezone(local_tz)
        fmt = '%d %b %Y %H:%M:%S' if with_seconds else '%d %b %Y %H:%M'
        offset_hours = int(current_app.config.get('APP_TIMEZONE_OFFSET', 8) or 8)
        sign = '+' if offset_hours >= 0 else '-'
        tz_label = current_app.config.get('APP_TIMEZONE_LABEL') or 'WITA'
        return f"{local_dt.strftime(fmt)} {tz_label} (UTC{sign}{abs(offset_hours)})"
    except Exception:
        try:
            return value.isoformat()
        except Exception:
            return '-'


def _sanitize_midtrans_payload_for_report(payload: object | None) -> object | None:
    if payload is None:
        return None

    if isinstance(payload, dict):
        sanitized: dict[object, object] = {}
        for k, v in payload.items():
            key_lower = str(k).lower()
            if any(s in key_lower for s in ('server_key', 'client_key', 'authorization', 'signature', 'token')):
                sanitized[k] = '***redacted***'
            else:
                sanitized[k] = _sanitize_midtrans_payload_for_report(v)
        return sanitized

    if isinstance(payload, list):
        return [_sanitize_midtrans_payload_for_report(v) for v in payload]

    return payload


def _compact_json_summary(payload: object | None, *, max_len: int = 180) -> str:
    if payload is None:
        return '-'
    if isinstance(payload, dict):
        text = ', '.join(f'{k}={payload.get(k)}' for k in list(payload.keys())[:6])
    else:
        text = str(payload)

    text = ' '.join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + '...'
    return text


def get_transaction_admin_report_pdf_impl(
    *,
    db,
    order_id: str,
    WEASYPRINT_AVAILABLE,
    HTML,
    get_local_tz,
    format_to_local_phone,
    Transaction,
    TransactionEvent,
    select,
    selectinload,
):
    if not WEASYPRINT_AVAILABLE or HTML is None:
        abort(HTTPStatus.NOT_IMPLEMENTED, 'Komponen PDF server tidak tersedia.')

    order_id = (order_id or '').strip()
    if not order_id:
        abort(HTTPStatus.BAD_REQUEST, 'order_id tidak boleh kosong.')

    tx = db.session.scalar(
        select(Transaction)
        .where(Transaction.midtrans_order_id == order_id)
        .options(selectinload(Transaction.user), selectinload(Transaction.package))
    )
    if tx is None:
        abort(HTTPStatus.NOT_FOUND, 'Transaksi tidak ditemukan.')

    payload: object | None = None
    if tx.midtrans_notification_payload:
        try:
            payload = json.loads(tx.midtrans_notification_payload)
        except Exception:
            payload = {'_raw': tx.midtrans_notification_payload}

    events_q = (
        select(TransactionEvent)
        .where(TransactionEvent.transaction_id == tx.id)
        .order_by(TransactionEvent.created_at.asc())
    )
    events = db.session.scalars(events_q).all()
    events_payload = []
    for ev in events:
        ev_payload: object | None = None
        if ev.payload:
            try:
                ev_payload = json.loads(ev.payload)
            except Exception:
                ev_payload = {'_raw': ev.payload}
        events_payload.append(
            {
                'created_at': ev.created_at,
                'created_at_local': _format_dt_local(ev.created_at, get_local_tz=get_local_tz, with_seconds=True),
                'source': ev.source.value,
                'event_type': ev.event_type,
                'status': ev.status.value if ev.status else None,
                'payload': ev_payload,
                'payload_summary': _compact_json_summary(ev_payload),
            }
        )

    local_tz = get_local_tz()
    user_phone_display = format_to_local_phone(tx.user.phone_number) if tx.user and tx.user.phone_number else None

    midtrans_payload_sanitized: object | None = _sanitize_midtrans_payload_for_report(payload)
    midtrans_summary: dict[str, object] | None = None
    if isinstance(midtrans_payload_sanitized, dict):
        safe_payload = dict(midtrans_payload_sanitized)
        midtrans_summary = {
            'payment_type': safe_payload.get('payment_type'),
            'transaction_status': safe_payload.get('transaction_status'),
            'status_code': safe_payload.get('status_code'),
            'status_message': safe_payload.get('status_message'),
            'transaction_id': safe_payload.get('transaction_id'),
            'acquirer': safe_payload.get('acquirer'),
            'issuer': safe_payload.get('issuer'),
            'transaction_time': safe_payload.get('transaction_time'),
            'settlement_time': safe_payload.get('settlement_time'),
            'expiry_time': safe_payload.get('expiry_time'),
            'merchant_id': safe_payload.get('merchant_id'),
        }

    context = {
        'transaction': tx,
        'user': tx.user,
        'package': tx.package,
        'status': tx.status.value,
        'report_date_local': datetime.now(local_tz),
        'tx_created_at_local': _format_dt_local(tx.created_at, get_local_tz=get_local_tz),
        'tx_updated_at_local': _format_dt_local(tx.updated_at, get_local_tz=get_local_tz),
        'tx_payment_time_local': _format_dt_local(tx.payment_time, get_local_tz=get_local_tz),
        'tx_expiry_time_local': _format_dt_local(tx.expiry_time, get_local_tz=get_local_tz),
        'user_phone_display': user_phone_display or (tx.user.phone_number if tx.user else None),
        'business_name': current_app.config.get('BUSINESS_NAME', 'LPSaring'),
        'business_address': current_app.config.get('BUSINESS_ADDRESS', ''),
        'business_phone': current_app.config.get('BUSINESS_PHONE', ''),
        'business_email': current_app.config.get('BUSINESS_EMAIL', ''),
        'midtrans_payload': midtrans_payload_sanitized,
        'midtrans_summary': midtrans_summary,
        'events': events_payload,
    }

    public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
    html_string = render_template('admin_transaction_report.html', **context)
    pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
    if not pdf_bytes:
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, 'Gagal menghasilkan file PDF.')

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename="admin-report-{order_id}.pdf"'
    return response
