# backend/scripts/run_walled_garden_sync.py
from app import create_app
from app.services.walled_garden_service import sync_walled_garden


def main() -> None:
    app = create_app()
    with app.app_context():
        result = sync_walled_garden()
        print(f"Walled-garden sync result: {result}")


if __name__ == "__main__":
    main()
