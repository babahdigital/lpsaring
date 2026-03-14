from app import create_app
from app.infrastructure.gateways.mikrotik_client import get_mikrotik_connection, get_walled_garden_rules
from app.services import walled_garden_service as service


def main() -> int:
    app = create_app()
    with app.app_context():
        config = service._load_walled_garden_sync_config()
        if not config.enabled:
            print("Walled garden disabled.")
            return 0

        desired_hosts = list(config.allowed_hosts)
        desired_ips = list(config.allowed_ips)
        comment_prefix = config.comment_prefix or "lpsaring"

        with get_mikrotik_connection() as api:
            if api is None:
                print("Failed to connect to Mikrotik.")
                return 1

            if config.allowed_ip_list_names:
                derived_list_ips = service._derive_ips_from_address_lists(api, list(config.allowed_ip_list_names))
                if derived_list_ips:
                    desired_ips = sorted({*desired_ips, *derived_list_ips})

            if not desired_ips and desired_hosts:
                derived_private_ips = service._derive_private_ips_from_hosts(desired_hosts)
                if derived_private_ips:
                    desired_ips = derived_private_ips

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
        print(f"- Desired hosts total: {len(desired_hosts)}")
        print(f"- Desired IPs total: {len(desired_ips)}")
        print(f"- Missing hosts: {missing_hosts}")
        print(f"- Extra hosts: {extra_hosts}")
        print(f"- Missing IPs: {missing_ips}")
        print(f"- Extra IPs: {extra_ips}")

        if missing_hosts or extra_hosts or missing_ips or extra_ips:
            return 2

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
