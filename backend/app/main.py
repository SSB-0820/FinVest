from app import create_app
from app.services.admin_service import seed_default_admin
from app.services.schema_service import ensure_automation_schema
from extensions.db import db

app = create_app()

with app.app_context():
    db.create_all()
    ensure_automation_schema()
    seed_default_admin()

if __name__ == "__main__":
    app.run(debug=True)
