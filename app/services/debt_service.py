from flask import url_for
from sqlalchemy import and_, or_

from app.extensions import db
from app.models.debt import Debt
from app.models.lab_ticket import LabTicket
from app.models.notification import Notification
from app.models.ticket_item import TicketItem
from app.models.user import User
from app.services.audit_service import log_event
from app.utils.statuses import DebtStatus, LabTicketStatus


def user_has_open_debts(user_id: int) -> bool:
    return (
        Debt.query
        .filter(Debt.user_id == user_id, Debt.status == DebtStatus.OPEN)
        .count()
        > 0
    )


def create_debt_for_ticket(ticket: LabTicket, item: TicketItem, missing_qty: int, actor_user_id: int | None) -> Debt | None:
    existing_debt = Debt.query.filter_by(
        user_id=ticket.owner_user_id,
        material_id=item.material_id,
        status=DebtStatus.OPEN,
    ).first()
    if existing_debt:
        return None

    material_name = item.material.name if item.material else f"Material ID {item.material_id}"
    debt = Debt(
        user_id=ticket.owner_user_id,
        material_id=item.material_id,
        ticket_id=ticket.id,
        status=DebtStatus.OPEN,
        reason=f"Faltante de {missing_qty} unidad(es) en ticket #{ticket.id} - {material_name}",
    )
    db.session.add(debt)
    db.session.flush()

    log_event(
        module="DEBTS",
        action="DEBT_CREATED",
        user_id=actor_user_id,
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
    return debt


def sync_ticket_after_debt_resolution(debt: Debt) -> LabTicket | None:
    ticket_id = debt.ticket_id
    if not ticket_id:
        return None

    ticket = LabTicket.query.get(ticket_id)
    if not ticket or ticket.owner_user_id != debt.user_id or ticket.status != LabTicketStatus.CLOSED_WITH_DEBT:
        return None

    remaining_open_debts = (
        Debt.query
        .filter(Debt.user_id == debt.user_id, Debt.status == DebtStatus.OPEN)
        .filter(
            or_(
                Debt.ticket_id == ticket_id,
                and_(Debt.ticket_id.is_(None), Debt.reason.ilike(f"%ticket #{ticket_id}%")),
            )
        )
        .count()
    )
    if remaining_open_debts == 0:
        ticket.status = LabTicketStatus.CLOSED
        return ticket

    return None


def resolve_debt(debt: Debt, actor_user_id: int | None) -> dict:
    previous_status = debt.status
    debt.status = DebtStatus.PAID
    debt.closed_at = db.func.now()

    log_event(
        module="DEBTS",
        action="DEBT_CLOSED",
        user_id=actor_user_id,
        entity_label=f"Debt #{debt.id}",
        description=f"Adeudo #{debt.id} marcado como pagado",
        metadata={
            "debt_id": debt.id,
            "target_user_id": debt.user_id,
            "material_id": debt.material_id,
            "status": debt.status,
            "previous_status": previous_status,
            "new_status": debt.status,
        },
        material_id=debt.material_id,
    )

    ticket_to_close = sync_ticket_after_debt_resolution(debt)
    ticket_notification = None
    if ticket_to_close:
        log_event(
            module="DEBTS",
            action="LAB_TICKET_CORRECTED_AFTER_DEBT",
            user_id=actor_user_id,
            entity_label=f"Debt #{debt.id}",
            description=f"Ticket #{ticket_to_close.id} corregido a CLOSED tras resolver adeudo",
            metadata={
                "debt_id": debt.id,
                "ticket_id": ticket_to_close.id,
                "target_user_id": debt.user_id,
            },
            material_id=debt.material_id,
        )
        ticket_notification = Notification(
            user_id=ticket_to_close.owner_user_id,
            title="Ticket corregido",
            message=f"Tu ticket #{ticket_to_close.id} fue corregido a cerrado tras resolver el adeudo.",
            link=url_for("reservations.my_reservations"),
        )
        db.session.add(ticket_notification)

    admin_notifications = []
    admins = User.query.filter(User.role.in_(["ADMIN", "SUPERADMIN"])).all()
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            title="Adeudo resuelto",
            message=f"El adeudo #{debt.id} fue marcado como pagado.",
            link=url_for("debts.admin_list"),
        )
        db.session.add(notif)
        admin_notifications.append(notif)

    db.session.commit()
    return {
        "ticket_notification": ticket_notification,
        "admin_notifications": admin_notifications,
    }
