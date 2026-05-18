"""Add performance indexes — H1 FK indexes + H2/H3/H4/H5/H7/H8 composites/partials

Sasaran:
- H1: FK columns tanpa index pada child side → seq scan saat parent dihapus.
- H2: ix_transactions_status_created_at (dashboard admin filter status + ORDER BY).
- H3: ix_transaction_events_transaction_id_event_type (idempotency lookup).
- H4: ix_user_devices_user_id_last_seen_at (ORDER BY DESC + range filter).
- H5: ix_user_quota_debts_user_id_is_paid (filter combo).
- H7: ix_admin_action_logs_created_at BRIN (purge harian).
- H8: ix_pds_pending_whatsapp partial + 3 single col.

Strategi production-safe: gunakan `CREATE INDEX CONCURRENTLY` (TIDAK lock tabel).
Alembic mengelola transaction per migration; CONCURRENTLY butuh autocommit, jadi
kita pakai `op.execute` + `op.get_context().autocommit_block()`.

Revision ID: 20260518_b_add_performance_indexes
Revises: 20260518_expand_admin_action_type_enum_v3
Create Date: 2026-05-18
"""

from alembic import op


revision = "20260518_b_add_performance_indexes"
down_revision = "20260518_expand_admin_action_type_enum_v3"
branch_labels = None
depends_on = None


# Daftar (index_name, CREATE statement, DROP statement). Drop pair untuk indexes
# yang sudah ada dan akan di-replace dengan composite (mis. ix_user_quota_debts_*
# single col → composite).
_OLD_INDEXES_TO_DROP = (
    # Replaced by ix_user_quota_debts_user_id_is_paid composite
    "ix_user_quota_debts_user_id",
    "ix_user_quota_debts_is_paid",
    # Replaced by ix_user_devices_user_id_last_seen_at composite
    "ix_user_devices_user_id",
    # Replaced by ix_transactions_status_created_at composite
    "ix_transactions_status",
    # Replaced by ix_transaction_events_transaction_id_event_type composite
    "ix_transaction_events_transaction_id",
    # Duplikat dengan UniqueConstraint uq_transactions_midtrans_order_id
    "ix_transactions_midtrans_order_id",
    # Duplikat dengan UniqueConstraint uq_users_phone_number
    "ix_users_phone_number",
)


_NEW_INDEXES = (
    # H1 — FK indexes on child side
    (
        "ix_users_blocked_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_blocked_by_id ON users (blocked_by_id)",
    ),
    (
        "ix_users_approved_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_approved_by_id ON users (approved_by_id)",
    ),
    (
        "ix_users_rejected_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_rejected_by_id ON users (rejected_by_id)",
    ),
    (
        "ix_user_quota_debts_created_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_quota_debts_created_by_id ON user_quota_debts (created_by_id)",
    ),
    (
        "ix_user_quota_debts_last_paid_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_quota_debts_last_paid_by_id "
        "ON user_quota_debts (last_paid_by_id)",
    ),
    (
        "ix_quota_mutation_ledger_actor_user_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_quota_mutation_ledger_actor_user_id "
        "ON quota_mutation_ledger (actor_user_id)",
    ),
    (
        "ix_promo_events_created_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_promo_events_created_by_id ON promo_events (created_by_id)",
    ),
    (
        "ix_refresh_tokens_replaced_by_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_refresh_tokens_replaced_by_id ON refresh_tokens (replaced_by_id)",
    ),
    (
        "ix_public_database_update_submissions_processed_by_user_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_public_database_update_submissions_processed_by_user_id "
        "ON public_database_update_submissions (processed_by_user_id)",
    ),
    # H2 — composite untuk admin dashboard transaction filtering
    (
        "ix_transactions_status_created_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_status_created_at "
        "ON transactions (status, created_at)",
    ),
    # H3 — composite untuk idempotency lookup
    (
        "ix_transaction_events_transaction_id_event_type",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transaction_events_transaction_id_event_type "
        "ON transaction_events (transaction_id, event_type)",
    ),
    # H4 — composite untuk device last_seen ORDER BY
    (
        "ix_user_devices_user_id_last_seen_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_devices_user_id_last_seen_at "
        "ON user_devices (user_id, last_seen_at DESC)",
    ),
    # H5 — composite untuk quota debt filter combo
    (
        "ix_user_quota_debts_user_id_is_paid",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_quota_debts_user_id_is_paid "
        "ON user_quota_debts (user_id, is_paid)",
    ),
    # H7 — BRIN untuk admin_action_logs.created_at (purge harian)
    (
        "ix_admin_action_logs_created_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_admin_action_logs_created_at "
        "ON admin_action_logs USING BRIN (created_at)",
    ),
    # H8 — partial pending + single col coverage
    (
        "ix_pds_pending_whatsapp",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pds_pending_whatsapp "
        "ON public_database_update_submissions (whatsapp_notified_at) "
        "WHERE approval_status = 'PENDING'",
    ),
    (
        "ix_public_database_update_submissions_approval_status",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_public_database_update_submissions_approval_status "
        "ON public_database_update_submissions (approval_status)",
    ),
    (
        "ix_public_database_update_submissions_phone_number",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_public_database_update_submissions_phone_number "
        "ON public_database_update_submissions (phone_number)",
    ),
    (
        "ix_public_database_update_submissions_created_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_public_database_update_submissions_created_at "
        "ON public_database_update_submissions (created_at)",
    ),
)


def upgrade():
    # CREATE INDEX CONCURRENTLY tidak boleh ada di transaction block.
    # Alembic auto wrap migration di transaction; pakai autocommit_block untuk skip.
    with op.get_context().autocommit_block():
        for _, create_stmt in _NEW_INDEXES:
            op.execute(create_stmt)
        # Drop indexes lama yang sudah di-replace composite.
        for old_idx in _OLD_INDEXES_TO_DROP:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {old_idx}")


def downgrade():
    with op.get_context().autocommit_block():
        # Hapus index baru
        for idx_name, _ in _NEW_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {idx_name}")
        # Recreate index lama (best-effort; tidak menjamin parity perfect dengan state sebelum upgrade)
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_quota_debts_user_id ON user_quota_debts (user_id)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_quota_debts_is_paid ON user_quota_debts (is_paid)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_user_devices_user_id ON user_devices (user_id)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_status ON transactions (status)")
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_transaction_events_transaction_id "
            "ON transaction_events (transaction_id)"
        )
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_transactions_midtrans_order_id "
            "ON transactions (midtrans_order_id)"
        )
        op.execute("CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ix_users_phone_number ON users (phone_number)")
