"""Add partial UNIQUE index + lookup index pada users.telegram_chat_id (C1/C3)

Tujuan:
- Cegah satu chat_id Telegram ter-link ke >1 user (race link concurrent / hijack).
- Speed-up lookup di webhook untuk dedup cross-user.

Strategi production-safe:
- Pakai CREATE INDEX CONCURRENTLY supaya tidak lock tabel `users`.
- Partial WHERE telegram_chat_id IS NOT NULL — NULL tidak ikut unique.
- Pasang juga regular index (non-unique) untuk eksplorasi/ORM filter umum (sudah
  di-handle implisit oleh unique partial, tapi kita biarkan UNIQUE saja sebagai
  satu-satunya — UNIQUE partial juga berfungsi sebagai lookup index).

Revision ID: 20260518_d_telegram_chat_id_unique_partial
Revises: 20260518_c_jsonb_quota_mutation_ledger
Create Date: 2026-05-18
"""

from alembic import op


revision = "20260518_d_telegram_chat_id_unique_partial"
down_revision = "20260518_c_jsonb_quota_mutation_ledger"
branch_labels = None
depends_on = None


_UNIQUE_PARTIAL_INDEX = "uq_users_telegram_chat_id_not_null"
_LOOKUP_INDEX = "ix_users_telegram_chat_id"


def upgrade() -> None:
    # Pre-check kalau index sudah ada dari run sebelumnya (idempoten) — drop dulu
    # supaya CONCURRENTLY tidak meledak duplikat.
    op.execute(f"DROP INDEX IF EXISTS {_UNIQUE_PARTIAL_INDEX};")
    op.execute(f"DROP INDEX IF EXISTS {_LOOKUP_INDEX};")

    # Alembic membungkus migration di transaction; CREATE INDEX CONCURRENTLY butuh
    # autocommit. Pakai autocommit_block helper.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
            f"{_UNIQUE_PARTIAL_INDEX} ON users (telegram_chat_id) "
            f"WHERE telegram_chat_id IS NOT NULL;"
        )
        # Lookup index — meskipun UNIQUE partial di atas sudah usable sebagai index,
        # ORM filter biasa (WHERE telegram_chat_id = ?) akan tetap memakai UNIQUE
        # partial. Kita pasang lookup index hanya kalau secara empiris UNIQUE
        # partial dilewati optimizer (rare). Untuk sekarang, satu UNIQUE partial
        # cukup → skip lookup index untuk hemat write amplification.
        # (Kalau perlu nanti: CREATE INDEX CONCURRENTLY ix_users_telegram_chat_id …)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_UNIQUE_PARTIAL_INDEX};")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_LOOKUP_INDEX};")
