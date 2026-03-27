"""Dashboard administrativo principal para ADMIN/SUPERADMIN."""

from datetime import datetime, timedelta

from flask import Blueprint, render_template
from sqlalchemy import func

from app.extensions import db
from app.models.material import Material
from app.models.reservation import Reservation
from app.models.lab_ticket import LabTicket
from app.models.ticket_item import TicketItem
from app.models.debt import Debt
from app.models.user import User
from app.utils.authz import min_role_required
from app.constants import ROLE_PENDING

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


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
    )
