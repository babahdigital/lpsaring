"""Fix FK constraints missing ON DELETE SET NULL

- promo_events.created_by_id: NO ACTION -> SET NULL
- users.blocked_by_id: NO ACTION -> SET NULL
- users.approved_by_id: NO ACTION -> SET NULL
- users.rejected_by_id: NO ACTION -> SET NULL

Without these, db.session.delete(user) raises IntegrityError if
the user is referenced by promo_events or by other users'
blocked_by/approved_by/rejected_by columns.

Revision ID: 20260326_fix_fk_ondelete_set_null
Revises: 20260319_d_backfill_price_rp_from_note
Create Date: 2026-03-26

"""

from alembic import op

revision = "20260326_fix_fk_ondelete_set_null"
down_revision = "20260319_d_backfill_price_rp_from_note"
branch_labels = None
depends_on = None


def _replace_fk(table, column, fk_name, ref_table="users", ref_col="id", ondelete="SET NULL"):
    """Drop old FK and recreate with ondelete clause."""
    op.drop_constraint(fk_name, table, type_="foreignkey")
    op.create_foreign_key(fk_name, table, ref_table, [column], [ref_col], ondelete=ondelete)


def upgrade():
    # promo_events.created_by_id — no named FK in original migration, discover name
    # Original migration: ForeignKey("users.id") without name — PG auto-generates name
    # Use batch mode for safety on both named and auto-named FKs
    with op.batch_alter_table("promo_events") as batch_op:
        batch_op.drop_constraint("promo_events_created_by_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "promo_events_created_by_id_fkey",
            "users", ["created_by_id"], ["id"], ondelete="SET NULL",
        )

    # users self-referencing FKs
    _replace_fk("users", "blocked_by_id", "fk_users_blocked_by_id_users", ondelete="SET NULL")
    _replace_fk("users", "approved_by_id", "fk_users_approved_by_id_users", ondelete="SET NULL")
    _replace_fk("users", "rejected_by_id", "fk_users_rejected_by_id_users", ondelete="SET NULL")


def downgrade():
    # Revert to NO ACTION (PostgreSQL default)
    with op.batch_alter_table("promo_events") as batch_op:
        batch_op.drop_constraint("promo_events_created_by_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "promo_events_created_by_id_fkey",
            "users", ["created_by_id"], ["id"],
        )

    _replace_fk("users", "blocked_by_id", "fk_users_blocked_by_id_users", ondelete="NO ACTION")
    _replace_fk("users", "approved_by_id", "fk_users_approved_by_id_users", ondelete="NO ACTION")
    _replace_fk("users", "rejected_by_id", "fk_users_rejected_by_id_users", ondelete="NO ACTION")
