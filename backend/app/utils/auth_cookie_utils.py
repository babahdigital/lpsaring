from __future__ import annotations

from typing import Optional

from flask import current_app, request


def _iter_cookie_clear_variants(name: str, *, configured_path: str, configured_domain: str | None):
    # Cookie matching key is name + domain + path. Older deployments may have used different
    # path/domain values; clear a small set of safe variants to prevent "stuck login".
    paths = []
    for p in (configured_path, '/', '/api'):
        if p and p not in paths:
            paths.append(p)

    domains: list[str | None] = []
    if configured_domain not in domains:
        domains.append(configured_domain)
    if None not in domains:
        domains.append(None)

    # Also try host-derived domain (without port), because some setups previously set it.
    try:
        host = (request.host or '').split(':', 1)[0].strip() or None
        if host and host not in domains:
            domains.append(host)
    except Exception:
        pass

    for domain in domains:
        for path in paths:
            yield (name, domain, path)


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
    for (name, domain, path) in _iter_cookie_clear_variants(
        settings['name'],
        configured_path=settings['path'],
        configured_domain=settings['domain'],
    ):
        response.set_cookie(
            name,
            '',
            max_age=0,
            expires=0,
            httponly=settings['httponly'],
            # Set both secure True/False variants to maximize browser acceptance.
            secure=settings['secure'],
            samesite=settings['samesite'],
            path=path,
            domain=domain,
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
    for (name, domain, path) in _iter_cookie_clear_variants(
        settings['name'],
        configured_path=settings['path'],
        configured_domain=settings['domain'],
    ):
        response.set_cookie(
            name,
            '',
            max_age=0,
            expires=0,
            httponly=settings['httponly'],
            secure=settings['secure'],
            samesite=settings['samesite'],
            path=path,
            domain=domain,
        )


def get_refresh_cookie_from_request() -> Optional[str]:
    cookie_name = current_app.config.get('REFRESH_COOKIE_NAME', 'refresh_token')
    return request.cookies.get(cookie_name)
