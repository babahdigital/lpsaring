from __future__ import annotations

import os
import pathlib
import subprocess
from datetime import datetime, timezone as dt_timezone
from http import HTTPStatus
from typing import Callable

from flask import current_app, jsonify, request, send_file
from sqlalchemy.engine import make_url


def list_backups_impl(*, get_backup_dir: Callable[[], str]):
    try:
        backup_dir = get_backup_dir()
        items = []
        for pattern in ('*.dump', '*.sql'):
            for entry in pathlib.Path(backup_dir).glob(pattern):
                stat = entry.stat()
                items.append(
                    {
                        'name': entry.name,
                        'size_bytes': stat.st_size,
                        'created_at': datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
                    }
                )
        items.sort(key=lambda x: x['created_at'], reverse=True)
        return jsonify({'items': items}), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error mengambil daftar backup: {e}', exc_info=True)
        return jsonify({'message': 'Gagal mengambil daftar backup.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def create_backup_impl(*, get_backup_dir: Callable[[], str], build_pg_dump_command: Callable[[str], list[str]]):
    try:
        backup_dir = get_backup_dir()
        timestamp = datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'backup_{timestamp}.dump'
        output_path = os.path.join(backup_dir, filename)

        cmd = build_pg_dump_command(output_path)
        env = os.environ.copy()
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if not isinstance(db_uri, str) or not db_uri:
            raise RuntimeError('DATABASE_URL tidak disetel')
        db_url = make_url(db_uri)
        if db_url.password:
            env['PGPASSWORD'] = db_url.password

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            current_app.logger.error(f'pg_dump gagal: {result.stderr}')
            return jsonify({'message': 'Backup gagal dijalankan.'}), HTTPStatus.INTERNAL_SERVER_ERROR

        stat = pathlib.Path(output_path).stat()
        return jsonify(
            {
                'name': filename,
                'size_bytes': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
            }
        ), HTTPStatus.OK
    except FileNotFoundError:
        return jsonify({'message': 'pg_dump tidak tersedia di server.'}), HTTPStatus.BAD_REQUEST
    except RuntimeError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f'Error membuat backup: {e}', exc_info=True)
        return jsonify({'message': 'Gagal membuat backup.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def download_backup_impl(*, filename: str, get_backup_dir: Callable[[], str]):
    backup_dir = get_backup_dir()
    safe_name = pathlib.Path(filename).name
    file_path = pathlib.Path(backup_dir) / safe_name
    if not file_path.exists() or not file_path.is_file():
        return jsonify({'message': 'File backup tidak ditemukan.'}), HTTPStatus.NOT_FOUND
    return send_file(file_path, as_attachment=True)


def upload_backup_impl(*, get_backup_dir: Callable[[], str]):
    try:
        uploaded_file = request.files.get('file')
        if uploaded_file is None:
            return jsonify({'message': 'File backup wajib diunggah.'}), HTTPStatus.BAD_REQUEST

        original_name = pathlib.Path(uploaded_file.filename or '').name
        if not original_name:
            return jsonify({'message': 'Nama file tidak valid.'}), HTTPStatus.BAD_REQUEST

        extension = pathlib.Path(original_name).suffix.lower()
        if extension not in ('.dump', '.sql'):
            return jsonify({'message': 'Format file tidak didukung. Gunakan .dump atau .sql'}), HTTPStatus.BAD_REQUEST

        backup_dir = pathlib.Path(get_backup_dir())
        stem = pathlib.Path(original_name).stem
        timestamp = datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')
        save_name = f'upload_{timestamp}_{stem}{extension}'
        target_path = backup_dir / save_name
        uploaded_file.save(target_path)

        stat = target_path.stat()
        return jsonify(
            {
                'message': 'File backup berhasil diunggah.',
                'name': save_name,
                'size_bytes': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_mtime, tz=dt_timezone.utc).isoformat(),
            }
        ), HTTPStatus.OK
    except Exception as e:
        current_app.logger.error(f'Error upload backup: {e}', exc_info=True)
        return jsonify({'message': 'Gagal mengunggah file backup.'}), HTTPStatus.INTERNAL_SERVER_ERROR


def restore_backup_impl(
    *,
    db,
    get_backup_dir: Callable[[], str],
    sanitize_sql_dump_for_restore,
    build_psql_restore_command,
    build_pg_restore_command,
    build_psql_statement_command,
):
    temporary_restore_path: pathlib.Path | None = None
    try:
        json_data = request.get_json(silent=True) or {}
        filename = str(json_data.get('filename') or '').strip()
        confirm = str(json_data.get('confirm') or '').strip().upper()
        restore_mode = str(json_data.get('restore_mode') or 'merge').strip().lower()

        if not filename:
            return jsonify({'message': 'filename wajib diisi.'}), HTTPStatus.BAD_REQUEST
        if confirm != 'RESTORE':
            return jsonify({'message': 'Konfirmasi restore tidak valid.'}), HTTPStatus.BAD_REQUEST
        if restore_mode not in ('merge', 'replace_users'):
            return jsonify({'message': "restore_mode tidak valid. Gunakan 'merge' atau 'replace_users'."}), HTTPStatus.BAD_REQUEST

        backup_dir = get_backup_dir()
        safe_name = pathlib.Path(filename).name
        file_path = pathlib.Path(backup_dir) / safe_name
        extension = file_path.suffix.lower()
        if extension not in ('.dump', '.sql'):
            return jsonify({'message': 'Format file backup tidak didukung.'}), HTTPStatus.BAD_REQUEST
        if extension != '.sql' and restore_mode != 'merge':
            return jsonify({'message': "restore_mode selain 'merge' hanya didukung untuk file .sql"}), HTTPStatus.BAD_REQUEST
        if not file_path.exists() or not file_path.is_file():
            return jsonify({'message': 'File backup tidak ditemukan.'}), HTTPStatus.NOT_FOUND

        db.session.remove()
        db.engine.dispose()

        if extension == '.sql':
            sanitized_path, removed_lines = sanitize_sql_dump_for_restore(file_path)
            if removed_lines > 0:
                current_app.logger.warning(
                    'Restore SQL: %s baris warning pg_dump dihapus otomatis dari %s',
                    removed_lines,
                    safe_name,
                )
            if sanitized_path != file_path:
                temporary_restore_path = sanitized_path
            cmd = build_psql_restore_command(str(sanitized_path))
        else:
            cmd = build_pg_restore_command(str(file_path))

        env = os.environ.copy()
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
        if not isinstance(db_uri, str) or not db_uri:
            raise RuntimeError('DATABASE_URL tidak disetel')
        db_url = make_url(db_uri)
        if db_url.password:
            env['PGPASSWORD'] = db_url.password

        if extension == '.sql' and restore_mode == 'replace_users':
            pre_cmd = build_psql_statement_command('TRUNCATE TABLE public.users RESTART IDENTITY CASCADE;')
            pre_result = subprocess.run(pre_cmd, env=env, capture_output=True, text=True, check=False)
            if pre_result.returncode != 0:
                pre_stderr = (pre_result.stderr or '').strip()
                current_app.logger.error(f'Pre-clean users sebelum restore gagal: {pre_stderr}')
                return jsonify(
                    {
                        'message': 'Pre-clean data users gagal dijalankan sebelum restore.',
                        'details': pre_stderr[:500],
                    }
                ), HTTPStatus.INTERNAL_SERVER_ERROR

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            stderr_text = (result.stderr or '').strip()
            only_transaction_timeout_warning = (
                extension == '.dump' and 'unrecognized configuration parameter "transaction_timeout"' in stderr_text
            )
            unsupported_dump_version = (
                extension == '.dump' and 'unsupported version' in stderr_text.lower() and 'file header' in stderr_text.lower()
            )

            if only_transaction_timeout_warning:
                current_app.logger.warning(
                    'pg_restore selesai dengan warning kompatibilitas transaction_timeout: %s',
                    stderr_text,
                )
            elif unsupported_dump_version:
                current_app.logger.error(f'pg_restore gagal (dump version mismatch): {stderr_text}')
                return jsonify(
                    {
                        'message': 'Restore gagal: format file backup lebih baru dari versi pg_restore di server.',
                        'details': stderr_text[:500],
                        'hint': 'Buat backup ulang dari server ini (Admin → Backup) atau restore memakai pg_restore versi yang sama/lebih baru.',
                    }
                ), HTTPStatus.BAD_REQUEST
            else:
                current_app.logger.error(f'pg_restore gagal: {stderr_text}')
                return jsonify({'message': 'Restore gagal dijalankan.', 'details': stderr_text[:500]}), HTTPStatus.INTERNAL_SERVER_ERROR

        return jsonify({'message': 'Restore database berhasil dijalankan.', 'filename': safe_name, 'restore_mode': restore_mode}), HTTPStatus.OK
    except FileNotFoundError:
        return jsonify({'message': 'pg_restore/psql tidak tersedia di server.'}), HTTPStatus.BAD_REQUEST
    except RuntimeError as e:
        return jsonify({'message': str(e)}), HTTPStatus.BAD_REQUEST
    except Exception as e:
        current_app.logger.error(f'Error restore backup: {e}', exc_info=True)
        return jsonify({'message': 'Gagal menjalankan restore backup.'}), HTTPStatus.INTERNAL_SERVER_ERROR
    finally:
        if temporary_restore_path is not None:
            try:
                if temporary_restore_path.exists():
                    temporary_restore_path.unlink()
            except Exception as cleanup_error:
                current_app.logger.warning(
                    'Gagal menghapus file sementara restore %s: %s',
                    str(temporary_restore_path),
                    cleanup_error,
                )
