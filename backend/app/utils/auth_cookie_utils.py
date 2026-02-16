from __future__ import annotations

from typing import Optional

from flask import current_app, request


def _get_access_cookie_settings() -> dict:
    return {
        'name': current_app.config.get('AUTH_COOKIE_NAME', 'auth_token'),
        'path': current_app.config.get('AUTH_COOKIE_PATH', '/'),
        'domain': current_app.config.get('AUTH_COOKIE_DOMAIN'),
        'samesite': current_app.config.get('AUTH_COOKIE_SAMESITE', 'Lax'),
        'secure': current_app.config.get('AUTH_COOKIE_SECURE', False),
        'httponly': current_app.config.get('AUTH_COOKIE_HTTPONLY', True),
        'max_age': current_app.config.get('AUTH_COOKIE_MAX_AGE_SECONDS'),
    }


def _get_refresh_cookie_settings() -> dict:
    return {
        'name': current_app.config.get('REFRESH_COOKIE_NAME', 'refresh_token'),
        'path': current_app.config.get('REFRESH_COOKIE_PATH', '/'),
        'domain': current_app.config.get('REFRESH_COOKIE_DOMAIN'),
        'samesite': current_app.config.get('REFRESH_COOKIE_SAMESITE', current_app.config.get('AUTH_COOKIE_SAMESITE', 'Lax')),
        'secure': current_app.config.get('REFRESH_COOKIE_SECURE', False),
        'httponly': current_app.config.get('REFRESH_COOKIE_HTTPONLY', True),
        'max_age': current_app.config.get('REFRESH_COOKIE_MAX_AGE_SECONDS'),
    }


def set_access_cookie(response, token: str) -> None:
    settings = _get_access_cookie_settings()
    response.set_cookie(
        settings['name'],
        token,
        max_age=settings['max_age'],
        httponly=settings['httponly'],
        secure=settings['secure'],
        samesite=settings['samesite'],
        path=settings['path'],
        domain=settings['domain'],
    )


def clear_access_cookie(response) -> None:
    settings = _get_access_cookie_settings()
    response.set_cookie(
        settings['name'],
        '',
        max_age=0,
        expires=0,
        httponly=settings['httponly'],
        secure=settings['secure'],
        samesite=settings['samesite'],
        path=settings['path'],
        domain=settings['domain'],
    )


def set_refresh_cookie(response, token: str) -> None:
    settings = _get_refresh_cookie_settings()
    response.set_cookie(
        settings['name'],
        token,
        max_age=settings['max_age'],
        httponly=settings['httponly'],
        secure=settings['secure'],
        samesite=settings['samesite'],
        path=settings['path'],
        domain=settings['domain'],
    )


def clear_refresh_cookie(response) -> None:
    settings = _get_refresh_cookie_settings()
    response.set_cookie(
        settings['name'],
        '',
        max_age=0,
        expires=0,
        httponly=settings['httponly'],
        secure=settings['secure'],
        samesite=settings['samesite'],
        path=settings['path'],
        domain=settings['domain'],
    )


def get_refresh_cookie_from_request() -> Optional[str]:
    cookie_name = current_app.config.get('REFRESH_COOKIE_NAME', 'refresh_token')
    return request.cookies.get(cookie_name)
