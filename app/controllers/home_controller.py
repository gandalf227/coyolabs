from datetime import datetime, timedelta

from flask import Blueprint, redirect, render_template, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from flask_login import current_user
from flask import request

from app.utils.authz import min_role_required
from app.utils.roles import is_admin_role, is_staff_role
from app.extensions import db

from app.models.material import Material
from app.models.reservation import Reservation
from app.models.lab_ticket import LabTicket
from app.models.ticket_item import TicketItem
from app.models.debt import Debt
from app.models.user import User
from app.constants import ROLE_PENDING

home_bp = Blueprint("home", __name__, url_prefix="/home")

@home_bp.route("/labs", methods=["GET"])
@min_role_required("STUDENT")
def labs_view():
    if is_admin_role(current_user.role):
        return redirect(url_for("dashboard.dashboard_home"))

    from datetime import datetime, time
    from flask import request

    date_str = request.args.get("date")
    time_str = request.args.get("time")

    if date_str:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        selected_date = datetime.now().date()

    if time_str:
        selected_time = datetime.strptime(time_str, "%H:%M").time()
    else:
        selected_time = time(11, 0)

    reservations = Reservation.query.filter(
        Reservation.date == selected_date
    ).options(
        joinedload(Reservation.user),
        joinedload(Reservation.subject_rel),
    ).all()

    return render_template(
        "home/labs.html",
        selected_date=selected_date,
        selected_time=selected_time.strftime("%H:%M"),
        reservations=reservations
    )

@home_bp.route("/", methods=["GET"])
@min_role_required("STUDENT")
def home_dashboard():
    if is_admin_role(current_user.role):
        return redirect(url_for("dashboard.dashboard_home"))

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

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

    pending_users_count = 0
    if is_staff_role(current_user.role):
        pending_users_count = User.query.filter(User.role == ROLE_PENDING).count()

    # Solo hoy y ayer
    recent_reservations = (
        Reservation.query
        .filter(Reservation.date >= yesterday)
        .order_by(Reservation.date.desc(), Reservation.start_time.desc())
        .limit(8)
        .all()
    )

    recent_tickets = (
        LabTicket.query
        .filter(LabTicket.date >= yesterday)
        .order_by(LabTicket.date.desc(), LabTicket.opened_at.desc())
        .limit(8)
        .all()
    )

    # Solo adeudos abiertos
    recent_debts = (
        Debt.query
        .filter(Debt.status == "OPEN")
        .order_by(Debt.created_at.desc())
        .limit(8)
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

    # Solo usuarios con adeudos abiertos
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

    # Labs usados solo hoy y ayer
    top_rooms = (
        db.session.query(
            Reservation.room,
            func.count(Reservation.id).label("total")
        )
        .filter(Reservation.date >= yesterday)
        .group_by(Reservation.room)
        .order_by(func.count(Reservation.id).desc())
        .limit(5)
        .all()
    )

    return render_template(
        "home/dashboard.html",
        active_page="home",
        total_inventory=total_inventory,
        reservations_today=reservations_today,
        approved_today=approved_today,
        pending_today=pending_today,
        open_tickets=open_tickets,
        closed_with_debt=closed_with_debt,
        open_debts=open_debts,
        low_stock_count=low_stock_count,
        pending_users_count=pending_users_count,
        recent_reservations=recent_reservations,
        recent_tickets=recent_tickets,
        recent_debts=recent_debts,
        top_materials=top_materials,
        top_debtors=top_debtors,
        top_rooms=top_rooms,
        is_admin=is_admin_role(current_user.role),
    )
