# backend/app/infrastructure/http/helpers/request_parsers.py
from __future__ import annotations

from typing import Type, Dict, Tuple, Union
from flask import request, jsonify, current_app
from pydantic import ValidationError
from http import HTTPStatus

JsonResponse = Tuple["flask.wrappers.Response", int]        # type: ignore

def parse_json_and_validate(
    schema_cls: Type,                    # Pydantic model class
    aliases: Dict[str, str] | None = None,
    log_prefix: str = ""
) -> Union[object, JsonResponse]:
    """
    Baca body JSON, terapkan alias field, lalu validasi dgn `schema_cls`.
    Jika sukses -> objek model. Jika gagal -> (response, status).
    """
    try:
        json_data = request.get_json(silent=True)
        if not json_data:
            current_app.logger.warning(f"{log_prefix}Body kosong/bukan JSON")
            return (
                jsonify({"success": False,
                         "message": "Request body tidak boleh kosong & harus JSON."}),
                HTTPStatus.BAD_REQUEST,
            )

        # Terapkan alias agar frontend tetap bisa kirim camelCase
        if aliases:
            for src, dest in aliases.items():
                if src in json_data and dest not in json_data:
                    json_data[dest] = json_data[src]

        validated = schema_cls.model_validate(json_data)
        return validated

    except ValidationError as ve:
        current_app.logger.warning(f"{log_prefix}Payload invalid: {ve.errors()}")
        return (
            jsonify({"success": False,
                     "message": "Data input tidak valid.",
                     "details": ve.errors()}),
            HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    except Exception as ex:
        # Jika error dari validator custom (TypeError/ValueError) perlakukan sebagai 422
        if isinstance(ex, (TypeError, ValueError)):
            current_app.logger.warning(f"{log_prefix}Payload invalid (runtime validator): {ex}")
            return (
                jsonify({"success": False,
                         "message": str(ex)}),
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        current_app.logger.warning(f"{log_prefix}Parse JSON error: {ex}", exc_info=True)
        return (
            jsonify({"success": False,
                     "message": "Format request tidak valid."}),
            HTTPStatus.BAD_REQUEST,
        )