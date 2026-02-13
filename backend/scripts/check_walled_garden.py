import json
from typing import List

from app import create_app
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, get_walled_garden_rules
from app.services import settings_service


def _get_list_setting(key: str) -> List[str]:
    value = settings_service.get_setting(key, "[]")
    if not value:
        return []
    if isinstance(value, str):
        val = value.strip()
        if val.startswith('[') and val.endswith(']'):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                val = val.strip('[]')
        if not val:
            return []
        return [item.strip().strip('"').strip("'") for item in val.split(',') if item.strip()]
    return []


def main() -> int:
    app = create_app()
    with app.app_context():
        enabled = settings_service.get_setting('WALLED_GARDEN_ENABLED', 'False') == 'True'
        if not enabled:
            print("Walled garden disabled.")
            return 0

        desired_hosts = sorted(set(_get_list_setting('WALLED_GARDEN_ALLOWED_HOSTS')))
        desired_ips = sorted(set(_get_list_setting('WALLED_GARDEN_ALLOWED_IPS')))
        comment_prefix = settings_service.get_setting('WALLED_GARDEN_MANAGED_COMMENT_PREFIX', 'lpsaring') or 'lpsaring'

        with get_mikrotik_connection() as api:
            if api is None:
                print("Failed to connect to Mikrotik.")
                return 1

            ok, current, message = get_walled_garden_rules(api, comment_prefix=comment_prefix)
            if not ok:
                print(f"Failed to read Mikrotik rules: {message}")
                return 1

        current_hosts = current.get("hosts", [])
        current_ips = current.get("ips", [])

        missing_hosts = sorted(set(desired_hosts) - set(current_hosts))
        extra_hosts = sorted(set(current_hosts) - set(desired_hosts))
        missing_ips = sorted(set(desired_ips) - set(current_ips))
        extra_ips = sorted(set(current_ips) - set(desired_ips))

        print("Walled garden check:")
        print(f"- Missing hosts: {missing_hosts}")
        print(f"- Extra hosts: {extra_hosts}")
        print(f"- Missing IPs: {missing_ips}")
        print(f"- Extra IPs: {extra_ips}")

        if missing_hosts or extra_hosts or missing_ips or extra_ips:
            return 2

        return 0


if __name__ == '__main__':
    raise SystemExit(main())
