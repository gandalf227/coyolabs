import re

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app.utils.roles import is_admin_role
from app.utils.authz import min_role_required
from app.utils.permission_required import permission_required

from app.extensions import db
from app.models.debt import Debt
from app.models.user import User
from app.models.material import Material
from app.models.lab_ticket import LabTicket
from app.models.notification import Notification
from app.services.audit_service import log_event
from app.services.notification_realtime_service import publish_notification_created


debts_bp = Blueprint("debts", __name__, url_prefix="/debts")


def _log_debt_event(action: str, debt: Debt, description: str, metadata: dict | None = None) -> None:
    payload = {
        "debt_id": debt.id,
        "target_user_id": debt.user_id,
        "material_id": debt.material_id,
        "status": debt.status,
    }
    if metadata:
        payload.update(metadata)

    log_event(
        module="DEBTS",
        action=action,
        user_id=getattr(current_user, "id", None),
        entity_label=f"Debt #{debt.id}",
        description=description,
        metadata=payload,
        material_id=debt.material_id,
    )


def _extract_ticket_id_from_reason(reason: str | None) -> int | None:
    if not reason:
        return None
    match = re.search(r"ticket\s*#(\d+)", reason, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


# -------------------------
# HOME
# -------------------------
@debts_bp.route("/", methods=["GET"])
@min_role_required("STUDENT")
def debts_home():
    if is_admin_role(current_user.role):
        return redirect(url_for("debts.admin_list"))

    return redirect(url_for("debts.my_debts"))


# -------------------------
# VER ADEUDOS PROPIOS
# -------------------------
@debts_bp.route("/my", methods=["GET"])
@min_role_required("STUDENT")
@permission_required("debts.view_own")
def my_debts():
    debts = (
        Debt.query
        .filter(Debt.user_id == current_user.id)
        .order_by(Debt.created_at.desc())
        .all()
    )

    return render_template(
        "debts/my_debts.html",
        debts=debts,
        active_page="debts"
    )


# -------------------------
# VER TODOS LOS ADEUDOS
# STAFF = SOLO VER
# -------------------------
@debts_bp.route("/admin", methods=["GET"])
@min_role_required("STAFF")
@permission_required("debts.view_all")
def admin_list():
    debts = Debt.query.order_by(Debt.created_at.desc()).limit(200).all()

    return render_template(
        "debts/admin_list.html",
        debts=debts,
        active_page="debts"
    )


# -------------------------
# CREAR ADEUDO (SOLO ADMIN REAL)
# -------------------------
@debts_bp.route("/admin/create", methods=["GET", "POST"])
@min_role_required("ADMIN")
@permission_required("debts.create")
def admin_create():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        material_id = request.form.get("material_id", type=int)
        reason = (request.form.get("reason") or "").strip()

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("No existe un usuario con ese correo.", "error")
            return redirect(url_for("debts.admin_create"))

        material = None
        if material_id:
            material = Material.query.get(material_id)
            if not material:
                flash("material_id no existe.", "error")
                return redirect(url_for("debts.admin_create"))

        debt = Debt(
            user_id=user.id,
            material_id=material.id if material else None,
            status="OPEN",
            reason=reason or None,
        )

        db.session.add(debt)
        db.session.flush()

        _log_debt_event(
            action="DEBT_CREATED",
            debt=debt,
            description=f"Adeudo creado para {user.email}",
            metadata={"reason": debt.reason},
        )
        db.session.commit()

        flash("Adeudo creado.", "success")
        return redirect(url_for("debts.admin_list"))

    return render_template("debts/admin_create.html", active_page="debts")


# -------------------------
# CERRAR ADEUDO
# -------------------------
@debts_bp.route("/admin/<int:debt_id>/close", methods=["POST"])
@min_role_required("ADMIN")
@permission_required("debts.close")
def admin_close(debt_id: int):
    debt = Debt.query.get(debt_id)

    if not debt:
        flash("Adeudo no encontrado.", "error")
        return redirect(url_for("debts.admin_list"))

    previous_status = debt.status
    debt.status = "PAID"
    debt.closed_at = db.func.now()

    _log_debt_event(
        action="DEBT_CLOSED",
        debt=debt,
        description=f"Adeudo #{debt.id} marcado como pagado",
        metadata={"previous_status": previous_status, "new_status": debt.status},
    )

    ticket_to_close = None
    ticket_id = _extract_ticket_id_from_reason(debt.reason)
    if ticket_id:
        ticket = LabTicket.query.get(ticket_id)
        if ticket and ticket.owner_user_id == debt.user_id and ticket.status == "CLOSED_WITH_DEBT":
            remaining_open_debts = (
                Debt.query
                .filter(Debt.user_id == debt.user_id, Debt.status == "OPEN")
                .filter(Debt.reason.ilike(f"%ticket #{ticket_id}%"))
                .count()
            )
            if remaining_open_debts == 0:
                ticket.status = "CLOSED"
                ticket_to_close = ticket

    ticket_notification = None
    if ticket_to_close:
        _log_debt_event(
            action="LAB_TICKET_CORRECTED_AFTER_DEBT",
            debt=debt,
            description=f"Ticket #{ticket_to_close.id} corregido a CLOSED tras resolver adeudo",
            metadata={"ticket_id": ticket_to_close.id},
        )
        ticket_notification = Notification(
            user_id=ticket_to_close.owner_user_id,
            title="Ticket corregido",
            message=f"Tu ticket #{ticket_to_close.id} fue corregido a cerrado tras resolver el adeudo.",
            link=url_for("reservations.my_reservations"),
        )
        db.session.add(ticket_notification)

    db.session.commit()
    if ticket_notification:
        publish_notification_created(ticket_notification)

    flash("Adeudo marcado como pagado.", "success")
    return redirect(url_for("debts.admin_list"))
