"""Merge all remaining heads into single lineage

Revision ID: 20250810_02
Revises: 670f6e3a2fc3, d38b5d05c996, 15dbcd2c8f16
Create Date: 2025-08-10

Purpose:
- Menyatukan tiga head terpisah (merge awal audit+enum, re-add trusted_mac, add blocking_reason)
- Tidak melakukan perubahan schema baru; hanya konsolidasi graph.

Catatan:
- Jangan ubah migrasi historis yang sudah terlanjur di-deploy; gunakan merge ini agar alembic_version kembali single row.
- Upgrade/downgrade pass-through (no-op) untuk menjaga idempotensi.
"""
from alembic import op  # noqa: F401  (future-proof if edit needed)
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20250810_02"
down_revision = ("670f6e3a2fc3", "d38b5d05c996", "15dbcd2c8f16")
branch_labels = None
depends_on = None


def upgrade():
    # No-op merge.
    pass


def downgrade():
    # Revert merge (tidak menghapus schema) – Alembic akan kembali melihat tiga head.
    pass
