"""Dashboard administrativo principal para ADMIN/SUPERADMIN."""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.material import Material
from app.models.reservation import Reservation
from app.models.lab_ticket import LabTicket
from app.models.ticket_item import TicketItem
from app.models.debt import Debt
from app.models.notification import Notification
from app.models.user import User
from app.utils.authz import min_role_required
from app.constants import ROLE_PENDING

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


def _build_operational_snapshot(activity_limit: int = 8) -> dict:
    pending_reservations = (
        Reservation.query
        .options(joinedload(Reservation.user))
        .filter(Reservation.status == "PENDING")
        .order_by(Reservation.created_at.asc())
        .limit(activity_limit)
        .all()
    )

    active_tickets = (
        LabTicket.query
        .options(joinedload(LabTicket.owner_user), joinedload(LabTicket.reservation))
        .filter(LabTicket.status.in_(["OPEN", "READY_FOR_PICKUP"]))
        .order_by(LabTicket.opened_at.asc())
        .limit(activity_limit)
        .all()
    )

    ready_items = (
        TicketItem.query
        .options(
            joinedload(TicketItem.ticket).joinedload(LabTicket.owner_user),
            joinedload(TicketItem.material),
        )
        .filter(TicketItem.status == "READY_FOR_PICKUP")
        .order_by(TicketItem.id.desc())
        .limit(activity_limit)
        .all()
    )

    closure_requested = (
        LabTicket.query
        .options(joinedload(LabTicket.owner_user), joinedload(LabTicket.reservation))
        .filter(LabTicket.status == "CLOSURE_REQUESTED")
        .order_by(LabTicket.opened_at.asc())
        .limit(activity_limit)
        .all()
    )

    open_debts_recent = (
        Debt.query
        .options(joinedload(Debt.user), joinedload(Debt.material))
        .filter(Debt.status == "OPEN")
        .order_by(Debt.created_at.desc())
        .limit(activity_limit)
        .all()
    )

    recent_activity = (
        Notification.query
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(activity_limit)
        .all()
    )

    return {
        "counts": {
            "pending_reservations": Reservation.query.filter(Reservation.status == "PENDING").count(),
            "active_tickets": LabTicket.query.filter(LabTicket.status.in_(["OPEN", "READY_FOR_PICKUP"])).count(),
            "ready_items": TicketItem.query.filter(TicketItem.status == "READY_FOR_PICKUP").count(),
            "closure_requested_tickets": LabTicket.query.filter(LabTicket.status == "CLOSURE_REQUESTED").count(),
            "open_debts": Debt.query.filter(Debt.status == "OPEN").count(),
        },
        "pending_reservations": [
            {
                "id": r.id,
                "user": r.user.email if r.user else "-",
                "room": r.room,
                "date": str(r.date),
                "time": f"{r.start_time}-{r.end_time}",
                "link": "/reservations/admin",
            }
            for r in pending_reservations
        ],
        "active_tickets": [
            {
                "id": t.id,
                "status": t.status,
                "user": t.owner_user.email if t.owner_user else "-",
                "reservation_id": t.reservation_id,
                "room": t.room or "-",
                "link": f"/reservations/admin/tickets/{t.id}",
            }
            for t in active_tickets
        ],
        "ready_items": [
            {
                "ticket_id": item.ticket_id,
                "material": item.material.name if item.material else f"ID {item.material_id}",
                "quantity_requested": item.quantity_requested,
                "quantity_delivered": item.quantity_delivered,
                "user": item.ticket.owner_user.email if item.ticket and item.ticket.owner_user else "-",
                "link": f"/reservations/admin/tickets/{item.ticket_id}",
            }
            for item in ready_items
        ],
        "closure_requested_tickets": [
            {
                "id": t.id,
                "user": t.owner_user.email if t.owner_user else "-",
                "reservation_id": t.reservation_id,
                "room": t.room or "-",
                "link": f"/reservations/admin/tickets/{t.id}",
            }
            for t in closure_requested
        ],
        "open_debts_recent": [
            {
                "id": d.id,
                "user": d.user.email if d.user else "-",
                "material": d.material.name if d.material else "-",
                "created_at": str(d.created_at),
                "link": "/debts/admin",
            }
            for d in open_debts_recent
        ],
        "recent_activity": [
            {
                "title": n.title,
                "message": n.message,
                "created_at": str(n.created_at),
                "link": n.link or "/notifications",
            }
            for n in recent_activity
        ],
    }


@dashboard_bp.route("/", methods=["GET"])
@min_role_required("ADMIN")
def dashboard_home():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    total_inventory = Material.query.count()

    reservations_today = Reservation.query.filter(
        Reservation.date == today
    ).count()

    approved_today = Reservation.query.filter(
        Reservation.date == today,
        Reservation.status == "APPROVED"
    ).count()

    pending_today = Reservation.query.filter(
        Reservation.date == today,
        Reservation.status == "PENDING"
    ).count()

    open_tickets = LabTicket.query.filter(
        LabTicket.status == "OPEN"
    ).count()

    closed_with_debt = LabTicket.query.filter(
        LabTicket.status == "CLOSED_WITH_DEBT"
    ).count()

    open_debts = Debt.query.filter(
        Debt.status == "OPEN"
    ).count()

    low_stock_count = Material.query.filter(
        Material.pieces_qty.isnot(None),
        Material.pieces_qty <= 3
    ).count()
    pending_users_count = User.query.filter(User.role == ROLE_PENDING).count()

    weekly_reservations = Reservation.query.filter(
        Reservation.date >= week_start,
        Reservation.date <= week_end
    ).count()

    recent_reservations = (
        Reservation.query
        .order_by(Reservation.created_at.desc())
        .limit(5)
        .all()
    )

    recent_tickets = (
        LabTicket.query
        .order_by(LabTicket.opened_at.desc())
        .limit(5)
        .all()
    )

    recent_debts = (
        Debt.query
        .order_by(Debt.created_at.desc())
        .limit(5)
        .all()
    )

    top_materials = (
        db.session.query(
            Material.name,
            func.coalesce(func.sum(TicketItem.quantity_requested), 0).label("total")
        )
        .join(TicketItem, TicketItem.material_id == Material.id)
        .group_by(Material.id, Material.name)
        .order_by(func.sum(TicketItem.quantity_requested).desc())
        .limit(5)
        .all()
    )

    top_debtors = (
        db.session.query(
            User.email,
            func.count(Debt.id).label("total_open")
        )
        .join(Debt, Debt.user_id == User.id)
        .filter(Debt.status == "OPEN")
        .group_by(User.id, User.email)
        .order_by(func.count(Debt.id).desc())
        .limit(5)
        .all()
    )

    top_rooms = (
        db.session.query(
            Reservation.room,
            func.count(Reservation.id).label("total")
        )
        .group_by(Reservation.room)
        .order_by(func.count(Reservation.id).desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard/home.html",
        active_page="dashboard",
        total_inventory=total_inventory,
        reservations_today=reservations_today,
        approved_today=approved_today,
        pending_today=pending_today,
        open_tickets=open_tickets,
        closed_with_debt=closed_with_debt,
        open_debts=open_debts,
        low_stock_count=low_stock_count,
        pending_users_count=pending_users_count,
        weekly_reservations=weekly_reservations,
        recent_reservations=recent_reservations,
        recent_tickets=recent_tickets,
        recent_debts=recent_debts,
        top_materials=top_materials,
        top_debtors=top_debtors,
        top_rooms=top_rooms,
        ops_snapshot=_build_operational_snapshot(),
    )


@dashboard_bp.route("/ops-feed", methods=["GET"])
@min_role_required("ADMIN")
def dashboard_ops_feed():
    return jsonify(_build_operational_snapshot())
