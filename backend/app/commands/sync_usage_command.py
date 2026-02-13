# backend/app/commands/sync_usage_command.py
# VERSI SEMPURNA & OPTIMAL: Menghindari pemanggilan helper yang tidak perlu di dalam loop.

import click
from flask.cli import with_appcontext
import time
import logging

from app.services.hotspot_sync_service import sync_hotspot_usage_and_profiles

# Helper _handle_mikrotik_operation tidak lagi dibutuhkan di file ini
# from app.services.user_management.helpers import _handle_mikrotik_operation

logger = logging.getLogger(__name__)

@click.command('sync-usage')
@with_appcontext
def sync_usage_command():
    logger.info("Memulai sinkronisasi kuota dan profil pengguna dengan Mikrotik...")
    start_time = time.time()
    counters = sync_hotspot_usage_and_profiles()
    duration = time.time() - start_time
    logger.info("Sinkronisasi selesai dalam %.2f detik. Hasil: %s", duration, counters)