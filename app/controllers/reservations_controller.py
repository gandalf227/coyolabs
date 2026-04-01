from datetime import datetime, timedelta
import json

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.utils.roles import ROLE_TEACHER, is_admin_role, normalize_role
from app.models.reservation_item import ReservationItem
from app.models.material import Material
from app.models.lab_ticket import LabTicket
from app.models.ticket_item import TicketItem
from app.models.debt import Debt
from app.models.notification import Notification
from app.models.subject import Subject
from app.models.teacher_academic_load import TeacherAcademicLoad
from app.models.user import User

from app.extensions import db
from app.models.reservation import Reservation
from app.services.audit_service import log_event
from app.services.debt_service import user_has_open_debts
from app.utils.authz import min_role_required
from app.utils.validators import normalize_and_validate_group_code
from app.constants import ROOMS

reservations_bp = Blueprint("reservations", __name__, url_prefix="/reservations")


def _is_professor_role(role: str | None) -> bool:
    normalized = normalize_role(role)
    return normalized == ROLE_TEACHER


def _parse_professor_subjects(raw_subjects: str | None) -> list[str]:
    if not raw_subjects:
        return []

    parts = []
    for chunk in raw_subjects.replace(";", ",").replace("\n", ",").split(","):
        subject = chunk.strip()
        if subject:
            parts.append(subject)

    unique = []
    seen = set()
    for item in parts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _professor_assignments(teacher_id: int) -> list[TeacherAcademicLoad]:
    return (
        TeacherAcademicLoad.query
        .options(joinedload(TeacherAcademicLoad.subject))
        .filter(TeacherAcademicLoad.teacher_id == teacher_id)
        .all()
    )


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
    q = (
        Reservation.query
        .filter(Reservation.room == room)
        .filter(Reservation.date == date_)
        .filter(Reservation.status == "APPROVED")
        .filter(Reservation.start_time < end_t)
        .filter(Reservation.end_time > start_t)
    )
    return q.count() > 0


def get_week_start(date_value):
    return date_value - timedelta(days=date_value.weekday())


def build_week_days(week_start):
    return [week_start + timedelta(days=i) for i in range(7)]

def apply_stock_delta(material: Material, old_delivered: int, old_returned: int, new_delivered: int, new_returned: int):
    old_outstanding = old_delivered - old_returned
    new_outstanding = new_delivered - new_returned
    delta_outstanding = new_outstanding - old_outstanding

    current_available = material.pieces_qty if material.pieces_qty is not None else 0
    new_available = current_available - delta_outstanding

    if new_available < 0:
        raise ValueError(f"Stock insuficiente para {material.name}")

    material.pieces_qty = new_available

def build_week_schedule(week_days, selected_room=None):
    week_start = week_days[0]
    week_end = week_days[-1]

    q = (
        Reservation.query
        .filter(Reservation.status == "APPROVED")
        .filter(Reservation.date >= week_start)
        .filter(Reservation.date <= week_end)
    )

    if selected_room:
        q = q.filter(Reservation.room == selected_room)
        room_list = [selected_room]
    else:
        room_list = list(ROOMS)

    reservations = q.order_by(
        Reservation.room.asc(),
        Reservation.date.asc(),
        Reservation.start_time.asc()
    ).all()

    schedule = {
        room: {day: [] for day in week_days}
        for room in room_list
    }

    for r in reservations:
        if r.room in schedule and r.date in schedule[r.room]:
            schedule[r.room][r.date].append(r)

    return schedule, room_list


@reservations_bp.route("/", methods=["GET"])
@min_role_required("STUDENT")
def reservations_home():
    if is_admin_role(current_user.role):
        return redirect(url_for("reservations.admin_queue"))

    return redirect(url_for("reservations.my_reservations"))


@reservations_bp.route("/my", methods=["GET"])
@min_role_required("STUDENT")
def my_reservations():
    reservations = (
        Reservation.query
        .options(
            joinedload(Reservation.items).joinedload(ReservationItem.material),
            joinedload(Reservation.lab_tickets)
        )
        .filter(Reservation.user_id == current_user.id)
        .order_by(Reservation.created_at.desc())
        .all()
    )

    return render_template(
        "reservations/my_reservations.html",
        reservations=reservations,
        active_page="reservations"
    )


@reservations_bp.route("/request", methods=["GET", "POST"])
@min_role_required("STUDENT")
def request_reservation():
    if user_has_open_debts(current_user.id):
        flash("Tienes un adeudo activo. No puedes solicitar reservas.", "error")
        return redirect(url_for("reservations.my_reservations"))

    week_start_s = (request.args.get("week_start") or "").strip()
    calendar_room = (request.args.get("calendar_room") or "").strip()

    try:
        base_date = parse_date(week_start_s) if week_start_s else datetime.today().date()
    except ValueError:
        base_date = datetime.today().date()

    week_start = get_week_start(base_date)
    week_days = build_week_days(week_start)
    week_end = week_days[-1]

    selected_calendar_room = calendar_room if calendar_room in ROOMS else ""
    week_schedule, calendar_rooms = build_week_schedule(
        week_days=week_days,
        selected_room=selected_calendar_room or None
    )

    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    is_professor = _is_professor_role(current_user.role)
    assignments = _professor_assignments(current_user.id) if is_professor else []
    professor_subjects = sorted({a.subject.name for a in assignments if a.subject})
    professor_groups_by_subject = {}
    for assignment in assignments:
        if not assignment.subject:
            continue
        professor_groups_by_subject.setdefault(assignment.subject.name, set()).add(assignment.group_code)
    professor_groups_by_subject = {
        subject_name: sorted(groups)
        for subject_name, groups in professor_groups_by_subject.items()
    }
    if is_professor and not professor_subjects:
        # fallback legacy en caso de que aún tengan datos antiguos
        professor_subjects = _parse_professor_subjects(getattr(current_user, "professor_subjects", None))

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

        if is_professor:
            group_name, group_error = normalize_and_validate_group_code(group_name)
            if group_error:
                flash(group_error, "error")
                return redirect(url_for("reservations.request_reservation"))

            if not assignments:
                flash("No tienes materias asignadas. Completa tu perfil o solicita actualización de materias.", "error")
                return redirect(url_for("reservations.request_reservation"))

            valid_assignment = next(
                (a for a in assignments if a.subject and a.subject.name.lower() == subject.lower() and a.group_code == group_name),
                None,
            )
            if not valid_assignment:
                flash("La materia/grupo seleccionados no pertenecen a tu carga académica.", "error")
                return redirect(url_for("reservations.request_reservation"))
            subject = valid_assignment.subject.name

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
        db.session.flush()

        material_ids = request.form.getlist("material_id[]")
        quantities = request.form.getlist("quantity[]")

        for i in range(len(material_ids)):
            try:
                material_id = int(material_ids[i])
                qty = int(quantities[i])
            except (ValueError, IndexError):
                continue

            if qty <= 0:
                continue

            material = Material.query.get(material_id)
            if not material:
                continue

            if material.pieces_qty is not None and qty > material.pieces_qty:
                db.session.rollback()
                flash(f"{material.name}: solo hay {material.pieces_qty} disponibles", "error")
                return redirect(url_for("reservations.request_reservation"))

            item = ReservationItem(
                reservation_id=r.id,
                material_id=material_id,
                quantity_requested=qty
            )
            db.session.add(item)

        admins = User.query.filter(User.role.in_(["ADMIN", "SUPERADMIN"])).all()

        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                title="Nueva reserva pendiente",
                message=f"El usuario {current_user.email} creó la reserva #{r.id} para {room} el {date_}.",
                link="/reservations/admin"
            )
            db.session.add(notif)

        log_event(
            module="RESERVATIONS",
            action="RESERVATION_CREATED",
            user_id=current_user.id,
            entity_label=f"Reservation #{r.id}",
            description=f"Reserva creada para {room} {date_} {start_t}-{end_t}",
            metadata={"reservation_id": r.id, "room": room, "status": "PENDING"},
        )

        db.session.commit()

        flash("Solicitud enviada. Queda pendiente de aprobación.", "success")
        return redirect(url_for("reservations.my_reservations"))

    materials = Material.query.order_by(Material.name.asc()).all()
    materials_json = json.dumps([
        {
            "id": m.id,
            "name": m.name,
            "pieces_qty": m.pieces_qty if m.pieces_qty is not None else 0
        }
        for m in materials
    ])

    return render_template(
        "reservations/request.html",
    rooms=ROOMS,
    materials=materials,
    materials_json=materials_json,
    week_days=week_days,
    week_start=week_start,
    week_end=week_end,
    week_schedule=week_schedule,
    calendar_rooms=calendar_rooms,
    selected_calendar_room=selected_calendar_room,
    prev_week=prev_week,
    next_week=next_week,
    is_professor=is_professor,
    professor_subjects=professor_subjects,
    professor_groups_by_subject=professor_groups_by_subject,
    active_page="reservations"
)

@reservations_bp.route("/admin", methods=["GET"])
@min_role_required("ADMIN")
def admin_queue():
    pending = (
        Reservation.query
        .options(
            joinedload(Reservation.items).joinedload(ReservationItem.material)
        )
        .filter(Reservation.status == "PENDING")
        .order_by(Reservation.created_at.asc())
        .all()
    )
    return render_template(
        "reservations/admin_queue.html",
        reservations=pending,
        active_page="reservations"
    )


@reservations_bp.route("/admin/approved", methods=["GET"])
@min_role_required("ADMIN")
def admin_approved():
    now = datetime.now()
    today = now.date()
    current_time = now.time()

    approved = (
        Reservation.query
        .options(
            joinedload(Reservation.items).joinedload(ReservationItem.material),
            joinedload(Reservation.lab_tickets),
            joinedload(Reservation.user)
        )
        .filter(Reservation.status == "APPROVED")
        .filter(Reservation.date == today)
        .order_by(Reservation.start_time.asc())
        .all()
    )

    for r in approved:
        open_ticket = next((t for t in r.lab_tickets if t.status == "OPEN"), None)
        r.open_ticket = open_ticket

        if open_ticket:
            r.can_open_ticket = False
            r.open_ticket_reason = "open"
            continue

        open_window_start = (datetime.combine(r.date, r.start_time) - timedelta(minutes=30)).time()
        open_window_end = r.end_time

        if current_time < open_window_start:
            r.can_open_ticket = False
            r.open_ticket_reason = "too_early"
        elif current_time > open_window_end:
            r.can_open_ticket = False
            r.open_ticket_reason = "expired"
        else:
            r.can_open_ticket = True
            r.open_ticket_reason = "available"

    return render_template(
        "reservations/admin_approved.html",
        reservations=approved,
        active_page="reservations"
    )

@reservations_bp.route("/admin/approved/history", methods=["GET"])
@min_role_required("ADMIN")
def admin_approved_history():
    today = datetime.now().date()

    reservations = (
        Reservation.query
        .options(
            joinedload(Reservation.items).joinedload(ReservationItem.material),
            joinedload(Reservation.lab_tickets),
            joinedload(Reservation.user)
        )
        .filter(Reservation.status == "APPROVED")
        .filter(Reservation.date < today)
        .order_by(Reservation.date.desc(), Reservation.start_time.desc())
        .all()
    )

    return render_template(
        "reservations/admin_approved_history.html",
        reservations=reservations,
        active_page="reservations"
    )

@reservations_bp.route("/admin/<int:res_id>/approve", methods=["POST"])
@min_role_required("ADMIN")
def admin_approve(res_id: int):
    r = Reservation.query.get(res_id)

    if not r:
        flash("Reserva no encontrada.", "error")
        return redirect(url_for("reservations.admin_queue"))

    if overlaps(r.room, r.date, r.start_time, r.end_time):
        flash("No se puede aprobar: se empalma con otra reserva aprobada.", "error")
        return redirect(url_for("reservations.admin_queue"))

    r.status = "APPROVED"
    r.admin_note = (request.form.get("admin_note") or "").strip() or None
    log_event(
        module="RESERVATIONS",
        action="RESERVATION_APPROVED",
        user_id=current_user.id,
        entity_label=f"Reservation #{r.id}",
        description=f"Reserva #{r.id} aprobada",
        metadata={"reservation_id": r.id, "target_user_id": r.user_id},
    )
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
    log_event(
        module="RESERVATIONS",
        action="RESERVATION_REJECTED",
        user_id=current_user.id,
        entity_label=f"Reservation #{r.id}",
        description=f"Reserva #{r.id} rechazada",
        metadata={"reservation_id": r.id, "target_user_id": r.user_id},
    )
    db.session.commit()

    flash("Reserva rechazada.", "success")
    return redirect(url_for("reservations.admin_queue"))


@reservations_bp.route("/admin/<int:res_id>/open-ticket", methods=["POST"])
@min_role_required("ADMIN")
def admin_open_ticket(res_id: int):
    r = Reservation.query.get(res_id)
    if not r:
        flash("Reserva no encontrada.", "error")
        return redirect(url_for("reservations.admin_approved"))

    if r.status != "APPROVED":
        flash("Solo se puede abrir ticket para reservas aprobadas.", "error")
        return redirect(url_for("reservations.admin_approved"))

    existing_ticket = LabTicket.query.filter_by(reservation_id=r.id, status="OPEN").first()
    if existing_ticket:
        flash("Ya existe un ticket abierto para esta reserva.", "error")
        return redirect(url_for("reservations.admin_approved"))

    now = datetime.now()
    today = now.date()
    current_time = now.time()

    if r.date != today:
        flash("Solo se puede abrir ticket para reservas del día actual.", "error")
        return redirect(url_for("reservations.admin_approved"))

    open_window_start = (datetime.combine(r.date, r.start_time) - timedelta(minutes=30)).time()
    open_window_end = r.end_time

    if current_time < open_window_start or current_time > open_window_end:
        flash("El ticket solo puede abrirse dentro de la ventana válida de uso.", "error")
        return redirect(url_for("reservations.admin_approved"))

    ticket = LabTicket(
        reservation_id=r.id,
        owner_user_id=r.user_id,
        room=r.room,
        date=r.date,
        status="OPEN",
        opened_by_user_id=current_user.id,
        notes=f"Ticket generado desde reserva #{r.id}"
    )

    db.session.add(ticket)
    db.session.flush()

    log_event(
        module="LAB_TICKETS",
        action="LAB_TICKET_OPENED",
        user_id=current_user.id,
        entity_label=f"LabTicket #{ticket.id}",
        description=f"Ticket abierto desde reserva #{r.id}",
        metadata={"ticket_id": ticket.id, "reservation_id": r.id, "owner_user_id": r.user_id},
    )

    for reservation_item in r.items:
        ticket_item = TicketItem(
            ticket_id=ticket.id,
            material_id=reservation_item.material_id,
            quantity_requested=reservation_item.quantity_requested,
            quantity_delivered=0,
            quantity_returned=0,
            status="REQUESTED"
        )
        db.session.add(ticket_item)

    db.session.commit()

    flash("Ticket de laboratorio abierto correctamente.", "success")
    return redirect(url_for("reservations.admin_approved"))

@reservations_bp.route("/admin/tickets/<int:ticket_id>", methods=["GET"])
@min_role_required("ADMIN")
def admin_ticket_detail(ticket_id: int):
    ticket = (
        LabTicket.query
        .options(joinedload(LabTicket.items).joinedload(TicketItem.material))
        .filter(LabTicket.id == ticket_id)
        .first()
    )

    if not ticket:
        flash("Ticket no encontrado.", "error")
        return redirect(url_for("reservations.admin_approved"))

    return render_template(
        "reservations/ticket_detail.html",
        ticket=ticket,
        active_page="reservations"
    )


@reservations_bp.route("/admin/tickets/items/<int:item_id>/update", methods=["POST"])
@min_role_required("ADMIN")
def admin_ticket_item_update(item_id: int):
    item = TicketItem.query.get(item_id)
    if not item:
        flash("Ítem del ticket no encontrado.", "error")
        return redirect(url_for("reservations.admin_approved"))

    try:
        delivered = int(request.form.get("quantity_delivered") or 0)
        returned = int(request.form.get("quantity_returned") or 0)
    except ValueError:
        flash("Las cantidades deben ser números válidos.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    if delivered < 0 or returned < 0:
        flash("Las cantidades no pueden ser negativas.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    if delivered > item.quantity_requested:
        flash("No puedes entregar más de lo solicitado.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    if returned > delivered:
        flash("No puedes devolver más de lo entregado.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    material = item.material
    if not material:
        flash("Material no encontrado.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    try:
        apply_stock_delta(
            material=material,
            old_delivered=item.quantity_delivered,
            old_returned=item.quantity_returned,
            new_delivered=delivered,
            new_returned=returned
        )
    except ValueError:
        flash(f"Stock insuficiente para {material.name}. Disponibles actuales: {material.pieces_qty}.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))

    item.quantity_delivered = delivered
    item.quantity_returned = returned
    item.notes = (request.form.get("notes") or "").strip() or None

    if delivered == 0:
        item.status = "REQUESTED"
    elif returned == 0:
        item.status = "DELIVERED"
    elif returned < delivered:
        item.status = "MISSING"
    else:
        item.status = "RETURNED"

    db.session.commit()

    flash("Ítem del ticket actualizado.", "success")
    return redirect(url_for("reservations.admin_ticket_detail", ticket_id=item.ticket_id))


@reservations_bp.route("/admin/tickets/<int:ticket_id>/close", methods=["POST"])
@min_role_required("ADMIN")
def admin_ticket_close(ticket_id: int):
    ticket = (
        LabTicket.query
        .options(joinedload(LabTicket.items).joinedload(TicketItem.material))
        .filter(LabTicket.id == ticket_id)
        .first()
    )

    if not ticket:
        flash("Ticket no encontrado.", "error")
        return redirect(url_for("reservations.admin_approved"))

    if ticket.status != "OPEN":
        flash("Solo se pueden cerrar tickets abiertos.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket.id))

    has_missing = False
    created_debt_ids: list[int] = []
    previous_ticket_status = ticket.status

    for item in ticket.items:
        missing_qty = item.quantity_delivered - item.quantity_returned

        if missing_qty > 0:
            has_missing = True
            item.status = "MISSING"

            existing_debt = Debt.query.filter_by(
                user_id=ticket.owner_user_id,
                material_id=item.material_id,
                status="OPEN"
            ).first()

            if not existing_debt:
                material_name = item.material.name if item.material else f"Material ID {item.material_id}"
                debt = Debt(
                    user_id=ticket.owner_user_id,
                    material_id=item.material_id,
                    status="OPEN",
                    reason=f"Faltante de {missing_qty} unidad(es) en ticket #{ticket.id} - {material_name}"
                )
                db.session.add(debt)
                db.session.flush()
                created_debt_ids.append(debt.id)
                log_event(
                    module="DEBTS",
                    action="DEBT_CREATED",
                    user_id=current_user.id,
                    entity_label=f"Debt #{debt.id}",
                    description=f"Adeudo generado automáticamente por faltante en ticket #{ticket.id}",
                    metadata={
                        "debt_id": debt.id,
                        "ticket_id": ticket.id,
                        "target_user_id": ticket.owner_user_id,
                        "material_id": item.material_id,
                        "missing_qty": missing_qty,
                        "origin": "LAB_TICKET_CLOSE",
                    },
                    material_id=item.material_id,
                )

    ticket.status = "CLOSED_WITH_DEBT" if has_missing else "CLOSED"
    ticket.closed_by_user_id = current_user.id
    ticket.closed_at = datetime.now()
    log_event(
        module="LAB_TICKETS",
        action="LAB_TICKET_CLOSED",
        user_id=current_user.id,
        entity_label=f"LabTicket #{ticket.id}",
        description=f"Ticket #{ticket.id} cerrado con estado {ticket.status}",
        metadata={
            "ticket_id": ticket.id,
            "owner_user_id": ticket.owner_user_id,
            "previous_status": previous_ticket_status,
            "new_status": ticket.status,
            "created_debt_ids": created_debt_ids,
        },
    )

    db.session.commit()

    flash("Ticket cerrado correctamente.", "success")
    return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket.id))

@reservations_bp.route("/admin/tickets/<int:ticket_id>/update-all", methods=["POST"])
@min_role_required("ADMIN")
def admin_ticket_update_all(ticket_id: int):
    item_ids = request.form.getlist("item_id[]")
    delivered_list = request.form.getlist("quantity_delivered[]")
    returned_list = request.form.getlist("quantity_returned[]")
    notes_list = request.form.getlist("notes[]")

    try:
        for i in range(len(item_ids)):
            try:
                item_id = int(item_ids[i])
                delivered = int(delivered_list[i])
                returned = int(returned_list[i])
            except (ValueError, IndexError):
                continue

            item = TicketItem.query.get(item_id)
            if not item:
                continue

            if delivered < 0 or returned < 0:
                flash("Las cantidades no pueden ser negativas.", "error")
                db.session.rollback()
                return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

            if delivered > item.quantity_requested:
                flash(f"No puedes entregar más de lo solicitado en {item.material.name if item.material else 'el material'}.", "error")
                db.session.rollback()
                return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

            if returned > delivered:
                flash(f"No puedes devolver más de lo entregado en {item.material.name if item.material else 'el material'}.", "error")
                db.session.rollback()
                return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

            material = item.material
            if not material:
                flash("Uno de los materiales del ticket no existe.", "error")
                db.session.rollback()
                return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

            old_delivered = item.quantity_delivered
            old_returned = item.quantity_returned

            try:
                apply_stock_delta(
                    material=material,
                    old_delivered=old_delivered,
                    old_returned=old_returned,
                    new_delivered=delivered,
                    new_returned=returned
                )
            except ValueError:
                flash(f"Stock insuficiente para {material.name}. Disponibles actuales: {material.pieces_qty}.", "error")
                db.session.rollback()
                return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

            item.quantity_delivered = delivered
            item.quantity_returned = returned
            item.notes = (notes_list[i] or "").strip() or None

            if delivered == 0:
                item.status = "REQUESTED"
            elif returned == 0:
                item.status = "DELIVERED"
            elif returned < delivered:
                item.status = "MISSING"
            else:
                item.status = "RETURNED"

        db.session.commit()
        flash("Todos los materiales actualizados correctamente.", "success")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))

    except Exception:
        db.session.rollback()
        flash("No se pudieron actualizar los materiales del ticket.", "error")
        return redirect(url_for("reservations.admin_ticket_detail", ticket_id=ticket_id))
