# backend/app/commands/user_cli.py
import click
from flask.cli import AppGroup

# Impor perintah dari file-file yang sudah dipecah
from .user.create import create_user
# --- [PENAMBAHAN] Impor perintah set_password ---
from .user.manage import approve_user, reject_user, delete_user, set_password
from .user.view import list_users, search_user, check_quota

# Membuat grup perintah baru 'user'
user_cli_bp = AppGroup('user', help='Manajemen pengguna melalui command-line.')

# Mendaftarkan setiap perintah ke dalam grup
user_cli_bp.add_command(create_user, "create")
user_cli_bp.add_command(approve_user, "approve")
user_cli_bp.add_command(reject_user, "reject")
user_cli_bp.add_command(delete_user, "delete")
user_cli_bp.add_command(list_users, "list")
user_cli_bp.add_command(search_user, "search")
user_cli_bp.add_command(check_quota, "quota")
# --- [PENAMBAHAN] Daftarkan perintah set-password ---
user_cli_bp.add_command(set_password, "set-password")