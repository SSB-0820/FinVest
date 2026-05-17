from datetime import datetime, timedelta

from app.models.active_session_model import ActiveSession
from extensions.db import db


ACTIVE_WINDOW_MINUTES = 5


def cleanup_stale_sessions(now=None):
    now = now or datetime.utcnow()
    cutoff = now - timedelta(minutes=ACTIVE_WINDOW_MINUTES)
    ActiveSession.query.filter(ActiveSession.last_seen_at < cutoff).delete()


def start_active_session(user_id, session_token):
    now = datetime.utcnow()
    cleanup_stale_sessions(now)
    active = ActiveSession.query.filter_by(session_token=session_token).first()
    if active:
        active.user_id = user_id
        active.last_seen_at = now
    else:
        db.session.add(
            ActiveSession(
                user_id=user_id,
                session_token=session_token,
                last_seen_at=now,
            )
        )


def touch_active_session(user_id, session_token):
    if not user_id or not session_token:
        return
    now = datetime.utcnow()
    active = ActiveSession.query.filter_by(session_token=session_token).first()
    if active:
        active.last_seen_at = now
    else:
        db.session.add(
            ActiveSession(
                user_id=user_id,
                session_token=session_token,
                last_seen_at=now,
            )
        )


def end_active_session(session_token):
    if session_token:
        ActiveSession.query.filter_by(session_token=session_token).delete()


def count_active_sessions():
    cleanup_stale_sessions()
    db.session.flush()
    return ActiveSession.query.count()
