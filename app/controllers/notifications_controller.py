from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user

from app.utils.authz import min_role_required
from app.extensions import db
from app.models.notification import Notification

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/", methods=["GET"])
@min_role_required("STUDENT")
def list_notifications():
    notifications = (
        Notification.query
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    return render_template(
        "notifications/list.html",
        notifications=notifications,
        active_page="notifications"
    )


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@min_role_required("STUDENT")
def mark_read(notif_id: int):
    notif = Notification.query.get(notif_id)

    if not notif or notif.user_id != current_user.id:
        flash("Notificación no encontrada.", "error")
        return redirect(url_for("notifications.list_notifications"))

    notif.is_read = True
    db.session.commit()

    if notif.link:
        return redirect(notif.link)

    return redirect(url_for("notifications.list_notifications"))
