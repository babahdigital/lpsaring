# backend/app/commands/__init__.py

from flask import Flask

def register_commands(app: Flask):
    """
    Mengimpor dan mendaftarkan semua perintah CLI kustom.
    """
    from .user_commands import user_cli_bp
    from .seed_commands import seed_db_command
    from .sync_usage_command import sync_users_status_command
    from .simulation_commands import simulate_low_quota_command
    from .user_cli import user_test_cli
    
    app.cli.add_command(user_cli_bp)
    app.cli.add_command(seed_db_command)
    app.cli.add_command(sync_users_status_command)
    app.cli.add_command(simulate_low_quota_command)
    app.cli.add_command(user_test_cli)