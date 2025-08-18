# backend/app/infrastructure/http/user/data_routes.py
# PENYEMPURNAAN: Beralih ke Flask-JWT-Extended untuk autentikasi.

from flask import Blueprint, jsonify, request, abort, current_app
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from http import HTTPStatus
import uuid
from flask_jwt_extended import jwt_required, get_current_user # [PERBAIKAN] Impor baru

from app.extensions import db
from app.infrastructure.db.models import User, Transaction
from ..schemas.transaction_schemas import TransactionResponseSchema
# [DIHAPUS] Impor decorator lama tidak diperlukan lagi.
# from ..decorators import token_required

data_bp = Blueprint('user_data_api', __name__)

@data_bp.route('/me/transactions', methods=['GET'])
@jwt_required() # [PERBAIKAN] Menggunakan decorator standar
def get_my_transactions():
    # [PERBAIKAN] Mengambil user dengan get_current_user()
    current_user: User = get_current_user()

    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 50)
        
        query = select(Transaction).options(
            selectinload(Transaction.package)
        ).where(Transaction.user_id == current_user.id).order_by(desc(Transaction.created_at))
            
        pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)

        transactions_data = [TransactionResponseSchema.model_validate(tx).model_dump(mode='json') for tx in pagination.items]
        
        return jsonify({
            "success": True,
            'transactions': transactions_data,
            'pagination': {
                'page': pagination.page, 
                'per_page': pagination.per_page, 
                'total_pages': pagination.pages, 
                'total_items': pagination.total
            }
        }), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f"Error pada get_my_transactions: {e}", exc_info=True)
        abort(HTTPStatus.INTERNAL_SERVER_ERROR, description="Gagal mengambil riwayat transaksi.")