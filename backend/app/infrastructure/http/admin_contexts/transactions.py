from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus

import sqlalchemy as sa
from flask import abort, current_app, jsonify, make_response, render_template, request


def get_transactions_list_impl(
    *,
    db,
    parse_local_date_range_to_utc,
    get_phone_number_variations,
    User,
    Transaction,
    selectinload,
    or_,
    desc,
):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('itemsPerPage', 10, type=int), 100)
        sort_by = request.args.get('sortBy', 'created_at')
        sort_order = request.args.get('sortOrder', 'desc')
        search_query = request.args.get('search', '').strip()
        user_id_filter = request.args.get('user_id')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        query = db.select(Transaction).options(selectinload(Transaction.user), selectinload(Transaction.package))

        if search_query:
            query = query.outerjoin(User, Transaction.user_id == User.id)

        if user_id_filter:
            try:
                user_uuid = uuid.UUID(user_id_filter)
                query = query.where(Transaction.user_id == user_uuid)
            except ValueError:
                return jsonify({'message': 'Invalid user_id format.'}), HTTPStatus.BAD_REQUEST

        if start_date_str and end_date_str:
            try:
                start_utc, end_utc = parse_local_date_range_to_utc(start_date_str, end_date_str)
                query = query.where(Transaction.created_at >= start_utc)
                query = query.where(Transaction.created_at < end_utc)
            except ValueError:
                return jsonify({'message': 'Format tanggal tidak valid.'}), HTTPStatus.BAD_REQUEST
        elif start_date_str or end_date_str:
            return jsonify({'message': 'start_date dan end_date harus diisi keduanya.'}), HTTPStatus.BAD_REQUEST

        if search_query:
            search_term = f'%{search_query}%'
            phone_variations = get_phone_number_variations(search_query)
            query = query.where(
                or_(
                    Transaction.midtrans_order_id.ilike(search_term),
                    User.full_name.ilike(search_term),
                    User.phone_number.in_(phone_variations)
                    if phone_variations
                    else User.phone_number.ilike(search_term),
                )
            )

        sortable_columns = {
            'created_at': Transaction.created_at,
            'amount': Transaction.amount,
            'status': Transaction.status,
        }
        if sort_by in sortable_columns:
            query = query.order_by(
                desc(sortable_columns[sort_by]) if sort_order == 'desc' else sortable_columns[sort_by]
            )
        else:
            query = query.order_by(desc(Transaction.created_at))

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
        transactions_data = [
            {
                'id': str(tx.id),
                'order_id': tx.midtrans_order_id,
                'amount': float(tx.amount),
                'status': tx.status.value,
                'created_at': tx.created_at.isoformat(),
                'midtrans_transaction_id': tx.midtrans_transaction_id,
                'payment_method': tx.payment_method,
                'payment_time': tx.payment_time.isoformat() if tx.payment_time else None,
                'expiry_time': tx.expiry_time.isoformat() if tx.expiry_time else None,
                'user': {
                    'full_name': tx.user.full_name if tx.user else 'N/A',
                    'phone_number': tx.user.phone_number if tx.user else 'N/A',
                },
                'package_name': tx.package.name if tx.package else 'N/A',
            }
            for tx in pagination.items
        ]

        return jsonify({'items': transactions_data, 'totalItems': pagination.total}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error mengambil daftar transaksi: {e}', exc_info=True)
        return jsonify({'message': 'Terjadi kesalahan internal.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def get_transaction_detail_impl(*, db, order_id: str, Transaction, TransactionEvent, select, selectinload, json_module):
    try:
        order_id = (order_id or '').strip()
        if not order_id:
            return jsonify({'message': 'order_id tidak boleh kosong.'}), HTTPStatus.BAD_REQUEST

        tx = db.session.scalar(
            select(Transaction)
            .where(Transaction.midtrans_order_id == order_id)
            .options(selectinload(Transaction.user), selectinload(Transaction.package))
        )

        if tx is None:
            return jsonify({'message': 'Transaksi tidak ditemukan.'}), HTTPStatus.NOT_FOUND

        payload: object | None = None
        if tx.midtrans_notification_payload:
            try:
                payload = json_module.loads(tx.midtrans_notification_payload)
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
                    ev_payload = json_module.loads(ev.payload)
                except Exception:
                    ev_payload = {'_raw': ev.payload}
            events_payload.append(
                {
                    'id': str(ev.id),
                    'created_at': ev.created_at.isoformat() if ev.created_at else None,
                    'source': ev.source.value,
                    'event_type': ev.event_type,
                    'status': ev.status.value if ev.status else None,
                    'payload': ev_payload,
                }
            )

        return (
            jsonify(
                {
                    'id': str(tx.id),
                    'order_id': tx.midtrans_order_id,
                    'amount': float(tx.amount),
                    'status': tx.status.value,
                    'created_at': tx.created_at.isoformat(),
                    'updated_at': tx.updated_at.isoformat() if tx.updated_at else None,
                    'midtrans_transaction_id': tx.midtrans_transaction_id,
                    'payment_method': tx.payment_method,
                    'payment_time': tx.payment_time.isoformat() if tx.payment_time else None,
                    'expiry_time': tx.expiry_time.isoformat() if tx.expiry_time else None,
                    'va_number': tx.va_number,
                    'payment_code': tx.payment_code,
                    'biller_code': tx.biller_code,
                    'qr_code_url': tx.qr_code_url,
                    'user': {
                        'full_name': tx.user.full_name if tx.user else 'N/A',
                        'phone_number': tx.user.phone_number if tx.user else 'N/A',
                    },
                    'package_name': tx.package.name if tx.package else 'N/A',
                    'midtrans_notification_payload': payload,
                    'events': events_payload,
                }
            ),
            HTTPStatus.OK,
        )
    except Exception as e:
        current_app.logger.error(f'Error mengambil detail transaksi {order_id}: {e}', exc_info=True)
        return jsonify({'message': 'Terjadi kesalahan internal.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def export_transactions_impl(
    *,
    db,
    WEASYPRINT_AVAILABLE,
    HTML,
    parse_local_date_range_to_utc,
    get_local_tz,
    estimate_debt_rp_from_cheapest_package,
    format_to_local_phone,
    Package,
    Transaction,
    TransactionStatus,
    User,
    UserRole,
    ApprovalStatus,
    func,
    select,
    desc,
):
    try:
        fmt = str(request.args.get('format', '') or '').strip().lower()
        start_date_str = str(request.args.get('start_date', '') or '').strip()
        end_date_str = str(request.args.get('end_date', '') or '').strip()
        user_id_filter = request.args.get('user_id')
        group_by = str(request.args.get('group_by', 'daily') or 'daily').strip().lower()
        if group_by not in ('daily', 'monthly', 'yearly', 'none'):
            return jsonify({'message': 'group_by tidak valid. Gunakan daily|monthly|yearly|none.'}), HTTPStatus.BAD_REQUEST

        if fmt and fmt != 'pdf':
            return jsonify({'message': 'format tidak valid. Gunakan pdf.'}), HTTPStatus.BAD_REQUEST
        fmt = 'pdf'
        if not start_date_str or not end_date_str:
            return jsonify({'message': 'start_date dan end_date wajib diisi.'}), HTTPStatus.BAD_REQUEST

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'message': 'Format tanggal tidak valid. Gunakan YYYY-MM-DD.'}), HTTPStatus.BAD_REQUEST

        if end_date < start_date:
            return jsonify({'message': 'end_date tidak boleh lebih kecil dari start_date.'}), HTTPStatus.BAD_REQUEST

        start_dt, end_dt = parse_local_date_range_to_utc(start_date_str, end_date_str)

        base_filters = [
            Transaction.status == TransactionStatus.SUCCESS,
            Transaction.created_at >= start_dt,
            Transaction.created_at < end_dt,
        ]

        if user_id_filter:
            try:
                user_uuid = uuid.UUID(str(user_id_filter))
                base_filters.append(Transaction.user_id == user_uuid)
            except ValueError:
                return jsonify({'message': 'Invalid user_id format.'}), HTTPStatus.BAD_REQUEST

        totals_row = db.session.execute(
            select(
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            ).where(*base_filters)
        ).one()

        total_success = int(totals_row[0] or 0)
        total_amount = int(totals_row[1] or 0)

        package_rows = db.session.execute(
            select(
                Package.name,
                func.count(Transaction.id).label('qty'),
                func.coalesce(func.sum(Transaction.amount), 0).label('revenue'),
            )
            .join(Package, Transaction.package_id == Package.id)
            .where(*base_filters)
            .group_by(Package.name)
            .order_by(desc('revenue'), desc('qty'), Package.name.asc())
        ).all()

        method_rows = db.session.execute(
            select(
                Transaction.payment_method,
                func.count(Transaction.id).label('qty'),
                func.coalesce(func.sum(Transaction.amount), 0).label('revenue'),
            )
            .where(*base_filters)
            .group_by(Transaction.payment_method)
            .order_by(desc('revenue'), desc('qty'))
        ).all()

        period_rows = []
        if group_by != 'none':
            try:
                offset_hours = int(current_app.config.get('APP_TIMEZONE_OFFSET', 8) or 8)
            except Exception:
                offset_hours = 8
            offset_hours = max(-12, min(offset_hours, 14))
            local_created = Transaction.created_at + sa.text(f"INTERVAL '{offset_hours} hours'")

            if group_by == 'daily':
                period_expr = func.date(local_created)
            elif group_by == 'monthly':
                period_expr = func.date_trunc('month', local_created)
            else:
                period_expr = func.date_trunc('year', local_created)

            period_rows = db.session.execute(
                select(
                    period_expr.label('period'),
                    func.count(Transaction.id).label('qty'),
                    func.coalesce(func.sum(Transaction.amount), 0).label('revenue'),
                )
                .where(*base_filters)
                .group_by(period_expr)
                .order_by(period_expr.asc())
            ).all()

        purchased_num = sa.cast(User.total_quota_purchased_mb, sa.Numeric)
        used_num = sa.cast(User.total_quota_used_mb, sa.Numeric)
        auto_debt_raw = sa.func.greatest(sa.cast(0, sa.Numeric), used_num - purchased_num)
        manual_debt_raw = sa.cast(func.coalesce(User.manual_debt_mb, 0), sa.Numeric)

        debt_not_applicable = sa.or_(
            User.role == UserRole.KOMANDAN,
            User.is_unlimited_user.is_(True),
        )

        auto_debt = sa.case((debt_not_applicable, sa.cast(0, sa.Numeric)), else_=auto_debt_raw)
        manual_debt_num = sa.case((debt_not_applicable, sa.cast(0, sa.Numeric)), else_=manual_debt_raw)
        total_debt = auto_debt + manual_debt_num

        debt_users = db.session.execute(
            select(
                User.full_name,
                User.phone_number,
                auto_debt.label('auto_debt_mb'),
                manual_debt_num.label('manual_debt_mb'),
                total_debt.label('total_debt_mb'),
            )
            .where(
                User.role.in_([UserRole.USER, UserRole.KOMANDAN]),
                User.is_active.is_(True),
                User.approval_status == ApprovalStatus.APPROVED,
                total_debt > 0,
            )
            .order_by(total_debt.desc(), User.full_name.asc())
            .limit(100)
        ).all()

        if not WEASYPRINT_AVAILABLE or HTML is None:
            return jsonify({'message': 'Komponen PDF server tidak tersedia.'}), HTTPStatus.NOT_IMPLEMENTED

        local_tz = get_local_tz()

        period_summaries = []
        if group_by != 'none':
            for row in period_rows:
                period = row[0]
                if group_by == 'daily':
                    label = period.strftime('%d-%m-%Y') if hasattr(period, 'strftime') else str(period)
                elif group_by == 'monthly':
                    label = period.strftime('%Y-%m') if hasattr(period, 'strftime') else str(period)
                else:
                    label = period.strftime('%Y') if hasattr(period, 'strftime') else str(period)
                period_summaries.append({'period': label, 'qty': int(row[1] or 0), 'revenue': int(row[2] or 0)})

        debt_items = [
            {
                'full_name': r[0],
                'phone_number': format_to_local_phone(r[1] or '') or (r[1] or ''),
                'debt_total_mb': float(r[4] or 0),
                'debt_auto_mb': float(r[2] or 0),
                'debt_manual_mb': float(r[3] or 0),
            }
            for r in debt_users
        ]

        ref_packages = []
        try:
            ref_packages = (
                db.session.execute(
                    select(Package)
                    .where(Package.is_active.is_(True))
                    .where(Package.data_quota_gb.is_not(None))
                    .where(Package.data_quota_gb > 0)
                    .where(Package.price.is_not(None))
                    .where(Package.price > 0)
                    .order_by(Package.data_quota_gb.asc(), Package.price.asc())
                )
                .scalars()
                .all()
            )
        except Exception:
            ref_packages = []

        def _pick_ref_pkg_for_mb(value_mb: float):
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
            return ref_packages[-1] if ref_packages else None

        total_debt_mb_sum = float(sum(float(item.get('debt_total_mb') or 0) for item in debt_items))
        total_ref_pkg = _pick_ref_pkg_for_mb(total_debt_mb_sum)
        cheapest_pkg_price = int(getattr(total_ref_pkg, 'price', 0) or 0) if total_ref_pkg else None
        cheapest_pkg_quota_gb = float(getattr(total_ref_pkg, 'data_quota_gb', 0) or 0) if total_ref_pkg else None
        cheapest_pkg_name = str(getattr(total_ref_pkg, 'name', '') or '') or None if total_ref_pkg else None
        est_total = estimate_debt_rp_from_cheapest_package(
            debt_mb=total_debt_mb_sum,
            cheapest_package_price_rp=cheapest_pkg_price,
            cheapest_package_quota_gb=cheapest_pkg_quota_gb,
            cheapest_package_name=cheapest_pkg_name,
        )
        estimated_debt_total_rp = int(est_total.estimated_rp_rounded or 0)
        for item in debt_items:
            item_ref = _pick_ref_pkg_for_mb(float(item.get('debt_total_mb') or 0))
            est = estimate_debt_rp_from_cheapest_package(
                debt_mb=float(item.get('debt_total_mb') or 0),
                cheapest_package_price_rp=int(getattr(item_ref, 'price', 0) or 0) if item_ref else None,
                cheapest_package_quota_gb=float(getattr(item_ref, 'data_quota_gb', 0) or 0) if item_ref else None,
                cheapest_package_name=str(getattr(item_ref, 'name', '') or '') or None if item_ref else None,
            )
            item['debt_estimated_rp'] = int(est.estimated_rp_rounded or 0)

        context = {
            'start_date': start_date_str,
            'end_date': end_date_str,
            'start_date_display': start_date.strftime('%d-%m-%Y'),
            'end_date_display': end_date.strftime('%d-%m-%Y'),
            'generated_at': datetime.now(local_tz),
            'total_success': total_success,
            'total_amount': total_amount,
            'estimated_debt_total_rp': estimated_debt_total_rp,
            'estimated_revenue_plus_debt_rp': int(total_amount or 0) + int(estimated_debt_total_rp or 0),
            'estimate_base_package_name': cheapest_pkg_name,
            'group_by': group_by,
            'period_summaries': period_summaries,
            'packages': [
                {'rank': idx, 'name': r[0], 'qty': int(r[1] or 0), 'revenue': int(r[2] or 0)}
                for idx, r in enumerate(package_rows, start=1)
            ],
            'methods': [
                {'method': (r[0] or '(unknown)'), 'qty': int(r[1] or 0), 'revenue': int(r[2] or 0)} for r in method_rows
            ],
            'debt_users': debt_items,
            'business_name': current_app.config.get('BUSINESS_NAME', 'LPSaring'),
        }

        public_base_url = current_app.config.get('APP_PUBLIC_BASE_URL', request.url_root)
        html_string = render_template('admin_sales_report.html', **context)
        pdf_bytes = HTML(string=html_string, base_url=public_base_url).write_pdf()
        if not pdf_bytes:
            abort(HTTPStatus.INTERNAL_SERVER_ERROR, 'Gagal menghasilkan file PDF.')
        resp = make_response(pdf_bytes)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = (
            f'attachment; filename="laporan-transaksi-{start_date_str}-to-{end_date_str}.pdf"'
        )
        return resp
    except Exception as e:
        current_app.logger.error(f'Error export transaksi: {e}', exc_info=True)
        return jsonify({'message': 'Terjadi kesalahan internal.'}), HTTPStatus.INTERNAL_SERVER_ERROR
