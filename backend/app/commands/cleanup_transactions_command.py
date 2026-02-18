# backend/app/commands/cleanup_transactions_command.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from http import HTTPStatus
from typing import Iterable

import click
from flask import current_app

from app.extensions import db
from app.infrastructure.db.models import Transaction, TransactionStatus


_TERMINAL_STATUSES: tuple[TransactionStatus, ...] = (
    TransactionStatus.EXPIRED,
    TransactionStatus.FAILED,
    TransactionStatus.CANCELLED,
)


def _parse_statuses(values: Iterable[str] | None) -> list[TransactionStatus]:
    if not values:
        return list(_TERMINAL_STATUSES)

    statuses: list[TransactionStatus] = []
    for raw in values:
        key = (raw or "").strip().upper()
        try:
            statuses.append(TransactionStatus[key])
        except Exception as exc:
            raise click.ClickException(f"Status tidak valid: {raw}") from exc
    return statuses


@click.command("cleanup-transactions")
@click.option("--older-than-days", type=int, default=30, show_default=True)
@click.option(
    "--status",
    "statuses",
    multiple=True,
    help="Status yang dibersihkan (boleh diulang). Default: EXPIRED, FAILED, CANCELLED.",
)
@click.option("--dry-run/--apply", default=True, show_default=True)
def cleanup_transactions_command(older_than_days: int, statuses: tuple[str, ...], dry_run: bool) -> None:
    """Bersihkan transaksi terminal lama agar DB tidak bengkak dan admin tidak terlihat seperti spam."""

    if older_than_days < 1:
        raise click.ClickException("older-than-days minimal 1")

    status_list = _parse_statuses(statuses)
    now_utc = datetime.now(dt_timezone.utc)
    cutoff = now_utc - timedelta(days=older_than_days)

    q = (
        db.session.query(Transaction)
        .filter(Transaction.status.in_(status_list))
        .filter(Transaction.created_at < cutoff)
    )

    total = q.count()
    click.echo(f"Found {total} transactions to cleanup (older_than_days={older_than_days}, statuses={[s.value for s in status_list]}).")

    if dry_run:
        click.echo("Dry-run: tidak ada data yang dihapus.")
        raise SystemExit(HTTPStatus.OK)

    deleted = q.delete(synchronize_session=False)
    db.session.commit()
    current_app.logger.info("cleanup-transactions deleted=%s cutoff=%s statuses=%s", deleted, cutoff.isoformat(), [s.value for s in status_list])
    click.echo(f"Deleted {deleted} transactions.")
