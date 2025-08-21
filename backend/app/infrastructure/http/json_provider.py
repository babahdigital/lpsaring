# backend/app/infrastructure/http/json_provider.py
# File ini berfungsi untuk mengajari Flask cara mengonversi
# tipe data kustom (Enum, UUID, datetime) ke format JSON.

import json
from enum import Enum
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from flask.json.provider import JSONProvider
try:
    # Optional import; present in SQLAlchemy
    from sqlalchemy.engine.row import Row  # type: ignore
except Exception:  # pragma: no cover
    Row = tuple  # Fallback type to avoid NameError if SQLAlchemy internals change

class CustomJSONProvider(JSONProvider):
    """
    JSONProvider kustom yang menggunakan CustomJSONEncoder.
    """
    def dumps(self, obj, **kwargs):
        # Memberitahu Flask untuk menggunakan encoder kustom kita saat melakukan dump ke JSON
        return json.dumps(obj, **kwargs, cls=CustomJSONEncoder)

    def loads(self, s, **kwargs):
        # Untuk memuat JSON, kita bisa gunakan bawaan
        return json.loads(s, **kwargs)

class CustomJSONEncoder(json.JSONEncoder):
    """
    JSONEncoder kustom untuk menangani tipe data yang tidak dikenal oleh JSON default.
    """
    def default(self, obj):
        # Jika objek adalah sebuah Enum (seperti ApprovalStatus, UserRole)
        if isinstance(obj, Enum):
            # Kembalikan nilainya (misal: "APPROVED", bukan <ApprovalStatus.APPROVED: 'APPROVED'>)
            return obj.value
        
        # Jika objek adalah datetime atau date
        if isinstance(obj, (datetime, date)):
            # Kembalikan dalam format standar ISO 8601
            return obj.isoformat()
            
        # Jika objek adalah UUID
        if isinstance(obj, UUID):
            # Kembalikan sebagai string
            return str(obj)

        # Perbaikan: serialisasi Decimal (umum dari DB numeric/decimal)
        if isinstance(obj, Decimal):
            # Gunakan float untuk interoperabilitas API; gunakan str(obj) bila perlu presisi penuh
            return float(obj)

        # Bantuan: serialisasi SQLAlchemy Row ke dict
        try:
            if Row is not None and isinstance(obj, Row):  # type: ignore
                return dict(getattr(obj, '_mapping', {}) or {})
        except Exception:
            pass

        # Objek dengan to_dict kustom
        try:
            if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
                return obj.to_dict()  # type: ignore
        except Exception:
            pass
            
        # Untuk tipe data lain, biarkan default handler yang bekerja
        return super().default(obj)