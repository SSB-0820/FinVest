from datetime import datetime

from flask import session

from extensions.mongo import insert_document


def log_activity(action, details="", user_id=None, user_name=None, user_email=None):
    resolved_user_id = user_id if user_id is not None else session.get("user_id")
    resolved_user_name = user_name or session.get("username") or "Unknown User"
    resolved_user_email = user_email or session.get("email") or "unknown@example.com"

    insert_document(
        "activity_logs",
        {
            "user_id": resolved_user_id,
            "user_name": resolved_user_name,
            "user_email": resolved_user_email,
            "action": action,
            "details": details,
            "created_at": datetime.utcnow().isoformat(),
        },
    )
