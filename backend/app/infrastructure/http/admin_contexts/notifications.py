from __future__ import annotations

from http import HTTPStatus

from flask import current_app, jsonify, request
from pydantic import ValidationError
from sqlalchemy import select

from app.infrastructure.db.models import ApprovalStatus, NotificationRecipient, NotificationType, User, UserRole
from app.infrastructure.http.schemas.notification_schemas import NotificationRecipientUpdateSchema


def send_whatsapp_test_impl(*, send_whatsapp_message):
    try:
        json_data = request.get_json(silent=True) or {}
        phone_number = str(json_data.get('phone_number') or '').strip()
        message = str(json_data.get('message') or '').strip() or 'Tes WhatsApp dari panel admin hotspot.'

        if not phone_number:
            return jsonify({'message': 'Nomor WhatsApp wajib diisi.'}), HTTPStatus.BAD_REQUEST
        if len(message) > 1000:
            return jsonify({'message': 'Pesan terlalu panjang (maks 1000 karakter).'}), HTTPStatus.BAD_REQUEST

        sent = send_whatsapp_message(phone_number, message)
        if not sent:
            return jsonify({'message': 'Pengiriman WhatsApp gagal. Cek konfigurasi Fonnte/token/nomor tujuan.'}), HTTPStatus.BAD_REQUEST

        return jsonify({'message': 'Pesan WhatsApp uji coba berhasil dikirim.', 'target': phone_number}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error test-send WhatsApp admin: {e}', exc_info=True)
        return jsonify({'message': 'Gagal mengirim WhatsApp uji coba.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def send_telegram_test_impl(*, send_telegram_message):
    try:
        json_data = request.get_json(silent=True) or {}
        chat_id = str(json_data.get('chat_id') or '').strip()
        message = str(json_data.get('message') or '').strip() or 'Tes Telegram dari panel admin hotspot.'

        if not chat_id:
            return jsonify({'message': 'chat_id Telegram wajib diisi.'}), HTTPStatus.BAD_REQUEST
        if len(message) > 4000:
            return jsonify({'message': 'Pesan terlalu panjang (maks 4000 karakter).'}), HTTPStatus.BAD_REQUEST

        sent = send_telegram_message(chat_id, message)
        if not sent:
            return jsonify({'message': 'Pengiriman Telegram gagal. Cek konfigurasi bot token / chat_id.'}), HTTPStatus.BAD_REQUEST

        return jsonify({'message': 'Pesan Telegram uji coba berhasil dikirim.', 'target': chat_id}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error test-send Telegram admin: {e}', exc_info=True)
        return jsonify({'message': 'Gagal mengirim Telegram uji coba.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def send_whatsapp_broadcast_impl(*, db, send_whatsapp_message):
    try:
        json_data = request.get_json(silent=True) or {}
        target_role = str(json_data.get('target_role') or '').strip().upper()
        message = str(json_data.get('message') or '').strip()

        if target_role not in {UserRole.USER.value, UserRole.KOMANDAN.value}:
            return jsonify({'message': 'Filter role tidak valid. Gunakan USER atau KOMANDAN.'}), HTTPStatus.BAD_REQUEST
        if not message:
            return jsonify({'message': 'Pesan wajib diisi.'}), HTTPStatus.BAD_REQUEST
        if len(message) > 1000:
            return jsonify({'message': 'Pesan terlalu panjang (maks 1000 karakter).'}), HTTPStatus.BAD_REQUEST

        recipients_query = select(User).where(
            User.role == UserRole[target_role],
            User.approval_status == ApprovalStatus.APPROVED,
            User.phone_number.isnot(None),
            User.phone_number != '',
        )
        recipients = db.session.scalars(recipients_query).all()

        if not recipients:
            return jsonify(
                {
                    'message': f'Tidak ada penerima untuk role {target_role}.',
                    'target_role': target_role,
                    'total_recipients': 0,
                    'sent_count': 0,
                    'failed_count': 0,
                }
            ), HTTPStatus.OK

        sent_count = 0
        failed_numbers = []
        for user in recipients:
            phone_number = str(user.phone_number or '').strip()
            if not phone_number:
                failed_numbers.append(phone_number)
                continue
            sent = send_whatsapp_message(phone_number, message)
            if sent:
                sent_count += 1
            else:
                failed_numbers.append(phone_number)

        failed_count = len(recipients) - sent_count
        return jsonify(
            {
                'message': 'Pengiriman WhatsApp massal selesai diproses.',
                'target_role': target_role,
                'total_recipients': len(recipients),
                'sent_count': sent_count,
                'failed_count': failed_count,
                'failed_numbers': failed_numbers[:20],
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error broadcast WhatsApp admin: {e}', exc_info=True)
        return jsonify({'message': 'Gagal memproses pengiriman WhatsApp massal.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def get_notification_recipients_impl(*, db):
    notification_type_str = request.args.get('notification_type') or request.args.get('type') or 'NEW_USER_REGISTRATION'
    try:
        notification_type = NotificationType[notification_type_str.upper()]
    except KeyError:
        return jsonify({'message': f'Tipe notifikasi tidak valid: {notification_type_str}'}), HTTPStatus.BAD_REQUEST

    try:
        all_admins_query = select(User).where(User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN])).order_by(User.full_name.asc())
        all_admins = db.session.scalars(all_admins_query).all()

        subscribed_admin_ids_query = select(NotificationRecipient.admin_user_id).where(
            NotificationRecipient.notification_type == notification_type
        )
        subscribed_admin_ids = set(db.session.scalars(subscribed_admin_ids_query).all())

        response_data = []
        for admin in all_admins:
            status_data = {
                'id': str(admin.id),
                'full_name': admin.full_name,
                'phone_number': admin.phone_number,
                'is_subscribed': admin.id in subscribed_admin_ids,
            }
            response_data.append(status_data)

        return jsonify(response_data), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(
            f'Error mengambil daftar penerima notifikasi untuk tipe {notification_type.name}: {e}', exc_info=True
        )
        return jsonify({'message': 'Terjadi kesalahan internal saat mengambil data.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def update_notification_recipients_impl(*, db):
    json_data = request.get_json()
    if not json_data:
        return jsonify({'message': 'Request body tidak boleh kosong.'}), HTTPStatus.BAD_REQUEST

    try:
        update_data = NotificationRecipientUpdateSchema.model_validate(json_data)
        notification_type = update_data.notification_type

        db.session.execute(db.delete(NotificationRecipient).where(NotificationRecipient.notification_type == notification_type))

        new_recipients = []
        if update_data.subscribed_admin_ids:
            valid_admin_ids_q = select(User.id).where(
                User.id.in_(update_data.subscribed_admin_ids), User.role.in_([UserRole.ADMIN, UserRole.SUPER_ADMIN])
            )
            valid_admin_ids = db.session.scalars(valid_admin_ids_q).all()
            for admin_id in valid_admin_ids:
                recipient = NotificationRecipient()
                recipient.admin_user_id = admin_id
                recipient.notification_type = notification_type
                new_recipients.append(recipient)
            if new_recipients:
                db.session.add_all(new_recipients)

        db.session.commit()
        return jsonify({'message': 'Pengaturan notifikasi berhasil disimpan.', 'total_recipients': len(new_recipients)}), HTTPStatus.OK
    except ValidationError as e:
        return jsonify({'errors': e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Gagal memperbarui penerima notifikasi: {e}', exc_info=True)
        return jsonify({'message': 'Terjadi kesalahan internal saat menyimpan data.'}), HTTPStatus.INTERNAL_SERVER_ERROR
