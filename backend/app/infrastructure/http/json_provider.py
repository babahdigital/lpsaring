# backend/app/infrastructure/http/json_provider.py
# File ini berfungsi untuk mengajari Flask cara mengonversi
# tipe data kustom (Enum, UUID, datetime) ke format JSON.

import json
from enum import Enum
from uuid import UUID
from datetime import datetime, date
from flask.json.provider import JSONProvider


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

        # Untuk tipe data lain, biarkan default handler yang bekerja
        return super().default(obj)
