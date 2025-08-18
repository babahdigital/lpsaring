from app import create_app
from app.extensions import db
from app.infrastructure.db.models import ApplicationSetting

app = create_app()

with app.app_context():
    try:
        from sqlalchemy import select
        settings = db.session.scalars(select(ApplicationSetting)).all()
        print(f"Found {len(settings)} settings:")
        for s in settings:
            print(f"- {s.setting_key}: {s.setting_value}")
    except Exception as e:
        print(f"Error: {e}")
