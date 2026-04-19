from flask import Blueprint, flash, redirect, render_template, session, url_for

from app.models.notification_model import Notification
from app.services.notification_service import sync_notifications
from app.utils.decorators import login_required
from extensions.db import db

notifications = Blueprint("notifications", __name__)


@notifications.route("/notifications")
@login_required
def notification_list():
    sync_notifications(session["user_id"])
    items = (
        Notification.query.filter_by(user_id=session["user_id"])
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    return render_template(
        "dashboard/notifications.html",
        active_page="notifications",
        notifications=items,
    )


@notifications.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_notification_read(notification_id):
    item = Notification.query.filter_by(
        id=notification_id, user_id=session["user_id"]
    ).first_or_404()
    item.is_read = True
    db.session.commit()
    flash("Notification marked as read")
    return redirect(url_for("notifications.notification_list"))


@notifications.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=session["user_id"], is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()
    flash("All notifications marked as read")
    return redirect(url_for("notifications.notification_list"))
