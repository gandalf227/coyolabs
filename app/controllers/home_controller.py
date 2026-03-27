from datetime import datetime, time

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.constants import ROLE_PENDING
from app.models.debt import Debt
from app.models.material import Material
from app.models.reservation import Reservation
from app.models.user import User
from app.utils.authz import min_role_required
from app.utils.roles import is_staff_role

home_bp = Blueprint("home", __name__, url_prefix="/home")


@home_bp.route("/labs", methods=["GET"])
@min_role_required("STUDENT")
def labs_view():
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

    reservations = (
        Reservation.query.filter(Reservation.date == selected_date)
        .options(
            joinedload(Reservation.user),
            joinedload(Reservation.subject_rel),
        )
        .all()
    )

    return render_template(
        "home/labs.html",
        selected_date=selected_date,
        selected_time=selected_time.strftime("%H:%M"),
        reservations=reservations,
    )


@home_bp.route("/", methods=["GET"])
@login_required
def home_dashboard():
    today = datetime.now().date()

    total_inventory = Material.query.count()

    reservations_today = Reservation.query.filter(
        Reservation.date == today
    ).count()

    approved_today = Reservation.query.filter(
        Reservation.date == today,
        Reservation.status == "APPROVED",
    ).count()

    pending_today = Reservation.query.filter(
        Reservation.date == today,
        Reservation.status == "PENDING",
    ).count()

    low_stock_count = Material.query.filter(
        Material.pieces_qty.isnot(None),
        Material.pieces_qty <= 3,
    ).count()

    my_reservations_count = Reservation.query.filter(
        Reservation.user_id == current_user.id
    ).count()

    my_open_debts_count = Debt.query.filter(
        Debt.user_id == current_user.id,
        Debt.status == "OPEN",
    ).count()

    recent_reservations = (
        Reservation.query.options(joinedload(Reservation.user))
        .order_by(Reservation.date.desc(), Reservation.start_time.desc())
        .limit(6)
        .all()
    )

    top_rooms = (
        Reservation.query.with_entities(
            Reservation.room,
            func.count(Reservation.id).label("total"),
        )
        .filter(Reservation.room.isnot(None))
        .group_by(Reservation.room)
        .order_by(func.count(Reservation.id).desc())
        .limit(5)
        .all()
    )

    pending_users_count = 0
    if is_staff_role(current_user.role):
        pending_users_count = User.query.filter(
            User.role == ROLE_PENDING
        ).count()

    return render_template(
        "home/home.html",
        active_page="home",
        total_inventory=total_inventory,
        reservations_today=reservations_today,
        approved_today=approved_today,
        pending_today=pending_today,
        low_stock_count=low_stock_count,
        my_reservations_count=my_reservations_count,
        my_open_debts_count=my_open_debts_count,
        recent_reservations=recent_reservations,
        top_rooms=top_rooms,
        pending_users_count=pending_users_count,
    )