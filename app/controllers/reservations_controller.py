from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app.extensions import db
from app.models.reservation import Reservation
from app.services.debt_service import user_has_open_debts
from app.utils.authz import min_role_required
from app.constants import ROOMS

reservations_bp = Blueprint("reservations", __name__, url_prefix="/reservations")


def parse_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_time(value: str):
    return datetime.strptime(value, "%H:%M").time()

def duration_minutes(start_t, end_t) -> int:
    dt1 = datetime.combine(datetime.today(), start_t)
    dt2 = datetime.combine(datetime.today(), end_t)
    return int((dt2 - dt1).total_seconds() / 60)



def overlaps(room: str, date_, start_t, end_t) -> bool:
    """
    True si hay solapamiento con una reserva aprobada en el mismo salón/fecha.
    Condición de solapamiento: start < existing_end AND end > existing_start
    """
    q = (Reservation.query
         .filter(Reservation.room == room)
         .filter(Reservation.date == date_)
         .filter(Reservation.status == "APPROVED")
         .filter(Reservation.start_time < end_t)
         .filter(Reservation.end_time > start_t))
    return q.count() > 0


@reservations_bp.route("/my", methods=["GET"])
@min_role_required("USER")
def my_reservations():
    res = (Reservation.query
           .filter(Reservation.user_id == current_user.id)
           .order_by(Reservation.created_at.desc())
           .all())
    return render_template("reservations/my_reservations.html", reservations=res)


@reservations_bp.route("/request", methods=["GET", "POST"])
@min_role_required("USER")
def request_reservation():
    # Bloqueo por adeudos
    if user_has_open_debts(current_user.id):
        flash("Tienes un adeudo activo. No puedes solicitar reservas.", "error")
        return redirect(url_for("reservations.my_reservations"))

    if request.method == "POST":
        room = (request.form.get("room") or "").strip()
        date_s = (request.form.get("date") or "").strip()
        start_s = (request.form.get("start_time") or "").strip()
        end_s = (request.form.get("end_time") or "").strip()
        purpose = (request.form.get("purpose") or "").strip()
        group_name = (request.form.get("group_name") or "").strip()
        teacher_name = (request.form.get("teacher_name") or "").strip()
        subject = (request.form.get("subject") or "").strip()
        signed = request.form.get("signed") == "1"


        if (
            not room
            or not date_s
            or not start_s
            or not end_s
            or not group_name
            or not teacher_name
            or not subject
            or not signed
        ):  
            flash("Faltan datos obligatorios o no confirmaste la firma.", "error")
            return redirect(url_for("reservations.request_reservation"))


        try:
            date_ = parse_date(date_s)
            start_t = parse_time(start_s)
            end_t = parse_time(end_s)
        except ValueError:
            flash("Formato de fecha u hora inválido.", "error")
            return redirect(url_for("reservations.request_reservation"))

        if end_t <= start_t:
            flash("La hora final debe ser mayor a la hora inicial.", "error")
            return redirect(url_for("reservations.request_reservation"))
        
        minutes = duration_minutes(start_t, end_t)
        if minutes > 120:
            flash("La duración máxima permitida es de 2 horas.", "error")
            return redirect(url_for("reservations.request_reservation"))


        # Validación de solapamiento solo contra APPROVED (para MVP)
        if overlaps(room, date_, start_t, end_t):
            flash("Ya existe una reserva aprobada que se empalma con ese horario.", "error")
            return redirect(url_for("reservations.request_reservation"))

        r = Reservation(
            user_id=current_user.id,
            room=room,
            date=date_,
            start_time=start_t,
            end_time=end_t,
            purpose=purpose or None,
            group_name=group_name,
            teacher_name=teacher_name,
            subject=subject,
            signed=signed,
            status="PENDING",
        )

        db.session.add(r)
        db.session.commit()

        flash("Solicitud enviada. Queda pendiente de aprobación.", "success")
        return redirect(url_for("reservations.my_reservations"))

    return render_template("reservations/request.html", rooms=ROOMS)


@reservations_bp.route("/admin", methods=["GET"])
@min_role_required("ADMIN")
def admin_queue():
    pending = (Reservation.query
               .filter(Reservation.status == "PENDING")
               .order_by(Reservation.created_at.asc())
               .all())
    return render_template("reservations/admin_queue.html", reservations=pending)


@reservations_bp.route("/admin/<int:res_id>/approve", methods=["POST"])
@min_role_required("ADMIN")
def admin_approve(res_id: int):
    r = Reservation.query.get(res_id)
    if not r:
        flash("Reserva no encontrada.", "error")
        return redirect(url_for("reservations.admin_queue"))

    # Revalidar solapamiento al aprobar (por si entraron dos solicitudes)
    if overlaps(r.room, r.date, r.start_time, r.end_time):
        flash("No se puede aprobar: se empalma con otra reserva aprobada.", "error")
        return redirect(url_for("reservations.admin_queue"))

    r.status = "APPROVED"
    r.admin_note = (request.form.get("admin_note") or "").strip() or None
    db.session.commit()

    flash("Reserva aprobada.", "success")
    return redirect(url_for("reservations.admin_queue"))


@reservations_bp.route("/admin/<int:res_id>/reject", methods=["POST"])
@min_role_required("ADMIN")
def admin_reject(res_id: int):
    r = Reservation.query.get(res_id)
    if not r:
        flash("Reserva no encontrada.", "error")
        return redirect(url_for("reservations.admin_queue"))

    r.status = "REJECTED"
    r.admin_note = (request.form.get("admin_note") or "").strip() or None
    db.session.commit()

    flash("Reserva rechazada.", "success")
    return redirect(url_for("reservations.admin_queue"))
