# backend/app/infrastructure/http/admin/promo_management_routes.py
import uuid
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.orm import selectinload
from http import HTTPStatus
from pydantic import ValidationError

from app.extensions import db
from app.infrastructure.db.models import PromoEvent, User, PromoEventStatus
from app.infrastructure.http.decorators import admin_required, super_admin_required

# Pastikan path import ini benar
from ..schemas.promo_schemas import PromoEventCreateSchema, PromoEventUpdateSchema, PromoEventResponseSchema

promo_management_bp = Blueprint("promo_management_api", __name__)


@promo_management_bp.route("/promos", methods=["POST"])
@super_admin_required
def create_promo_event(current_admin: User):
    """Membuat event promo baru. Hanya untuk Super Admin."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    try:
        data = PromoEventCreateSchema.model_validate(json_data)

        # --- PERBAIKAN: Menambahkan bonus_duration_days saat membuat event ---
        new_event = PromoEvent()
        new_event.name = data.name
        new_event.description = data.description
        new_event.event_type = data.event_type
        new_event.status = data.status
        new_event.start_date = data.start_date
        new_event.end_date = data.end_date
        new_event.bonus_value_mb = data.bonus_value_mb
        new_event.bonus_duration_days = data.bonus_duration_days
        new_event.created_by_id = current_admin.id

        db.session.add(new_event)
        db.session.commit()

        db.session.refresh(new_event, ["created_by"])

        response_schema = PromoEventResponseSchema.from_orm(new_event)
        return jsonify(response_schema.model_dump()), HTTPStatus.CREATED

    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating promo event: {e}", exc_info=True)
        return jsonify({"message": "Terjadi kesalahan internal saat membuat event."}), HTTPStatus.INTERNAL_SERVER_ERROR


@promo_management_bp.route("/promos", methods=["GET"])
@admin_required
def get_promo_events(current_admin: User):
    """Mendapatkan daftar semua event promo dengan paginasi dan filter."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("itemsPerPage", 10, type=int), 100)
        sort_by = request.args.get("sortBy", "created_at")
        sort_order = request.args.get("sortOrder", "desc")
        status_filter = request.args.get("status")

        query = db.select(PromoEvent).options(selectinload(PromoEvent.created_by))

        if status_filter:
            try:
                status_enum = PromoEventStatus(status_filter.upper())
                query = query.where(PromoEvent.status == status_enum)
            except ValueError:
                # Abaikan filter jika nilainya tidak valid
                pass

        sortable_columns = {
            "name": PromoEvent.name,
            "status": PromoEvent.status,
            "start_date": PromoEvent.start_date,
            "end_date": PromoEvent.end_date,
            "created_at": PromoEvent.created_at,
        }

        column_to_sort = sortable_columns.get(sort_by, PromoEvent.created_at)
        query = query.order_by(column_to_sort.desc() if sort_order.lower() == "desc" else column_to_sort.asc())

        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

        results = [PromoEventResponseSchema.from_orm(event).model_dump() for event in pagination.items]

        return jsonify({"items": results, "totalItems": pagination.total}), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching promo events: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil data event."}), HTTPStatus.INTERNAL_SERVER_ERROR


@promo_management_bp.route("/promos/<uuid:promo_id>", methods=["GET"])
@admin_required
def get_promo_event_by_id(current_admin: User, promo_id: uuid.UUID):
    """Mendapatkan detail satu event promo berdasarkan ID."""
    event = db.session.get(PromoEvent, promo_id)
    if not event:
        return jsonify({"message": "Event tidak ditemukan."}), HTTPStatus.NOT_FOUND

    response_schema = PromoEventResponseSchema.from_orm(event)
    return jsonify(response_schema.model_dump()), HTTPStatus.OK


@promo_management_bp.route("/promos/<uuid:promo_id>", methods=["PUT"])
@super_admin_required
def update_promo_event(current_admin: User, promo_id: uuid.UUID):
    """Memperbarui event promo. Hanya untuk Super Admin."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Request body tidak boleh kosong."}), HTTPStatus.BAD_REQUEST

    event = db.session.get(PromoEvent, promo_id)
    if not event:
        return jsonify({"message": "Event tidak ditemukan."}), HTTPStatus.NOT_FOUND

    try:
        update_data = PromoEventUpdateSchema.model_validate(json_data)

        # Loop ini akan secara otomatis menangani field baru 'bonus_duration_days'
        for key, value in update_data.model_dump(exclude_unset=True).items():
            setattr(event, key, value)

        db.session.commit()

        db.session.refresh(event, ["created_by"])
        response_schema = PromoEventResponseSchema.from_orm(event)
        return jsonify(response_schema.model_dump()), HTTPStatus.OK

    except ValidationError as e:
        return jsonify({"errors": e.errors()}), HTTPStatus.UNPROCESSABLE_ENTITY
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating promo event {promo_id}: {e}", exc_info=True)
        return jsonify(
            {"message": "Terjadi kesalahan internal saat memperbarui event."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR


@promo_management_bp.route("/promos/<uuid:promo_id>", methods=["DELETE"])
@super_admin_required
def delete_promo_event(current_admin: User, promo_id: uuid.UUID):
    """Menghapus event promo. Hanya untuk Super Admin."""
    event = db.session.get(PromoEvent, promo_id)
    if not event:
        return jsonify({"message": "Event tidak ditemukan."}), HTTPStatus.NOT_FOUND

    try:
        db.session.delete(event)
        db.session.commit()
        return "", HTTPStatus.NO_CONTENT
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting promo event {promo_id}: {e}", exc_info=True)
        return jsonify(
            {"message": "Terjadi kesalahan internal saat menghapus event."}
        ), HTTPStatus.INTERNAL_SERVER_ERROR
