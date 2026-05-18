"""Convert quota_mutation_ledger.{before_state,after_state,event_details} to JSONB (H6)

Sasaran:
- `sa.JSON` di PostgreSQL maps ke type `json` — tidak support operator @> ?, ?,
  ?|, GIN index, dll. Untuk query/analytics, JSONB jauh lebih efisien.
- 3 kolom di quota_mutation_ledger di-rewrite ke JSONB.

⚠️  PERINGATAN PRODUKSI:
- Tabel ~842k rows (1122 MB di production per 2026-05-18).
- `ALTER COLUMN TYPE` dengan `USING ... ::jsonb` melakukan FULL TABLE REWRITE
  dengan AccessExclusiveLock. Estimasi: 30-120 detik downtime untuk SELECT/INSERT
  pada tabel ini.
- Strategi: lakukan di maintenance window. Pre-deploy backup workflow sudah
  menyediakan safety net.

Alternatif zero-downtime (TIDAK dipakai di sini untuk kesederhanaan):
- Tambah kolom *_jsonb baru, dual-write app, backfill batch, swap nama, drop lama.
  Butuh app-side feature flag + 2x deploy. Defer untuk Phase 2 kalau perlu.

Revision ID: 20260518_c_jsonb_quota_mutation_ledger
Revises: 20260518_b_add_performance_indexes
Create Date: 2026-05-18
"""

from alembic import op


revision = "20260518_c_jsonb_quota_mutation_ledger"
down_revision = "20260518_b_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # Set statement_timeout untuk transaksi ini agar tidak hang berlarut-larut.
    # 5 menit cukup untuk 1.1 GB table di disk SSD.
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute("SET LOCAL lock_timeout = '60s'")

    op.execute(
        """
        ALTER TABLE quota_mutation_ledger
          ALTER COLUMN before_state TYPE jsonb USING before_state::jsonb,
          ALTER COLUMN after_state  TYPE jsonb USING after_state::jsonb,
          ALTER COLUMN event_details TYPE jsonb USING event_details::jsonb
        """
    )


def downgrade():
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute("SET LOCAL lock_timeout = '60s'")
    op.execute(
        """
        ALTER TABLE quota_mutation_ledger
          ALTER COLUMN before_state TYPE json USING before_state::json,
          ALTER COLUMN after_state  TYPE json USING after_state::json,
          ALTER COLUMN event_details TYPE json USING event_details::json
        """
    )
