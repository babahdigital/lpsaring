# backend/app/infrastructure/http/public_promo_routes.py
from flask import Blueprint, jsonify, current_app
from sqlalchemy import select, or_
from http import HTTPStatus
import datetime

from app.extensions import db
from app.infrastructure.db.models import PromoEvent, PromoEventStatus
from .schemas.promo_schemas import PromoEventResponseSchema

public_promo_bp = Blueprint('public_promo_api', __name__, url_prefix='/api/public/promos')

@public_promo_bp.route('/active', methods=['GET'])
def get_active_promos():
    """
    [PERBAIKAN] Mendapatkan SEMUA event promo yang sedang aktif untuk ditampilkan ke publik.
    Mengembalikan array (list) dari promo.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Query untuk mencari semua event yang statusnya ACTIVE, sudah dimulai,
        # dan belum berakhir (atau tidak memiliki tanggal akhir).
        query = select(PromoEvent).where(
            PromoEvent.status == PromoEventStatus.ACTIVE,
            PromoEvent.start_date <= now,
            or_(
                PromoEvent.end_date == None,
                PromoEvent.end_date >= now
            )
        ).order_by(PromoEvent.created_at.desc())
        
        active_events = db.session.execute(query).scalars().all()
        
        # [PENYEMPURNAAN] Mengembalikan array, bahkan jika kosong.
        # Ini memudahkan penanganan di sisi frontend.
        if not active_events:
            return jsonify([]), HTTPStatus.OK
            
        # Gunakan skema response yang ada, tapi kecualikan info 'created_by' untuk publik.
        response_data = [
            PromoEventResponseSchema.from_orm(event).model_dump(exclude={'created_by'}) 
            for event in active_events
        ]
        return jsonify(response_data), HTTPStatus.OK

    except Exception as e:
        current_app.logger.error(f"Error fetching active promos: {e}", exc_info=True)
        return jsonify({"message": "Gagal mengambil informasi promo."}), HTTPStatus.INTERNAL_SERVER_ERROR