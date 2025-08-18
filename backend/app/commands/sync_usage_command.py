# backend/app/commands/sync_usage_command.py
import click
from flask.cli import with_appcontext
import logging

from app.tasks import dispatch_all_users_sync

logger = logging.getLogger(__name__)

@click.command('sync-users-status')
@with_appcontext
def sync_users_status_command():
    """Pemicu sinkronisasi massal via Celery."""
    click.echo("Mengirim permintaan sinkronisasi massal ke Celery...")
    try:
        dispatch_all_users_sync.delay()
        click.secho(
            "\nBerhasil! Tugas dispatcher telah dikirim ke antrian.",
            fg='green', bold=True
        )
        click.echo("Pantau log Celery Worker & Beat untuk progres.")
    except Exception as e:
        logger.error(f"Gagal kirim tugas Celery: {e}")
        click.secho(
            f"Error: pastikan Redis/Celery hidup.\nDetail: {e}",
            fg='red'
        )

# Alias kompatibilitas untuk import di app/__init__.py
sync_usage_command = sync_users_status_command