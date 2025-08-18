# backend/app/infrastructure/http/public_promo_routes.py

from flask import Blueprint, jsonify, current_app
from http import HTTPStatus
from sqlalchemy import select, and_, or_
from datetime import datetime, timezone

from app.extensions import db
from app.infrastructure.db.models import PromoEvent, PromoEventStatus
from .schemas.promo_schemas import PromoEventResponseSchema 

# Blueprint ini sekarang akan dipasang di bawah prefix `/api/public`
public_promo_bp = Blueprint('public_promo_api', __name__)

# PERBAIKAN: Rute ini sekarang menjadi '/active'
@public_promo_bp.route('/active', methods=['GET'])
def get_active_promos():
    """
    Endpoint ini menyediakan daftar semua promo yang sedang aktif.
    URL lengkapnya akan menjadi: /api/public/promos/active
    """
    try:
        now = datetime.now(timezone.utc)

        query = select(PromoEvent).where(
            and_(
                PromoEvent.status == PromoEventStatus.ACTIVE,
                PromoEvent.start_date <= now,
                or_(
                    PromoEvent.end_date == None,
                    PromoEvent.end_date > now
                )
            )
        )
        
        active_promos_db = db.session.scalars(query).all()

        active_promos_list = [
            {
                "id": str(promo.id),
                "name": promo.name,
                "description": promo.description,
                "event_type": promo.event_type.value,
                "status": promo.status.value,
                "start_date": promo.start_date.isoformat(),
                "end_date": promo.end_date.isoformat() if promo.end_date else None,
                "bonus_value_mb": promo.bonus_value_mb,
                "bonus_duration_days": promo.bonus_duration_days
            }
            for promo in active_promos_db
        ]

        return jsonify(active_promos_list), HTTPStatus.OK
        
    except Exception as e:
        current_app.logger.error(f"Error saat mengambil promo aktif: {e}", exc_info=True)
        return jsonify([]), HTTPStatus.INTERNAL_SERVER_ERROR