from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flask import url_for

from app.extensions import db
from app.models.lab_ticket import LabTicket
from app.models.material import Material
from app.models.notification import Notification
from app.models.ticket_item import TicketItem
from app.models.user import User
from app.services.audit_service import log_event
from app.services.debt_service import create_debt_for_ticket
from app.utils.statuses import (
    LabTicketStatus,
    TicketItemStatus,
    is_active_lab_ticket_status,
    is_lab_ticket_closure_requested,
)


@dataclass(slots=True)
class ServiceResult:
    ok: bool
    message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, message: str | None = None, **data: Any) -> "ServiceResult":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def failure(cls, message: str, **data: Any) -> "ServiceResult":
        return cls(ok=False, message=message, data=data)


def validate_ticket_active(ticket: LabTicket | None) -> ServiceResult:
    if not ticket:
        return ServiceResult.failure("Ticket no encontrado.")
    if not is_active_lab_ticket_status(ticket.status):
        return ServiceResult.failure("Solo puedes operar tickets activos.", ticket=ticket)
    return ServiceResult.success(ticket=ticket)


def sync_ticket_ready_status(ticket: LabTicket) -> ServiceResult:
    has_ready_items = any((item.status or "").upper() == TicketItemStatus.READY_FOR_PICKUP for item in ticket.items)
    if has_ready_items and ticket.status == LabTicketStatus.OPEN:
        ticket.status = LabTicketStatus.READY_FOR_PICKUP
    elif not has_ready_items and ticket.status == LabTicketStatus.READY_FOR_PICKUP:
        ticket.status = LabTicketStatus.OPEN
    return ServiceResult.success(ticket=ticket)


def apply_ticket_item_status(item: TicketItem, delivered: int, returned: int) -> ServiceResult:
    if delivered == 0:
        item.status = TicketItemStatus.REQUESTED
    elif returned == 0:
        item.status = TicketItemStatus.DELIVERED
    elif returned < delivered:
        item.status = TicketItemStatus.MISSING
    else:
        item.status = TicketItemStatus.RETURNED
    return ServiceResult.success(item=item)


def add_material_to_ticket(ticket: LabTicket, material: Material, quantity: int, actor_user: User) -> ServiceResult:
    active_result = validate_ticket_active(ticket)
    if not active_result.ok:
        return ServiceResult.failure("No se pueden agregar materiales a un ticket cerrado.")

    if quantity <= 0:
        return ServiceResult.failure("Selecciona material y una cantidad válida.")

    if material.pieces_qty is not None and quantity > material.pieces_qty:
        return ServiceResult.failure(f"{material.name}: solo hay {material.pieces_qty} disponibles para solicitud.")

    item = TicketItem.query.filter_by(ticket_id=ticket.id, material_id=material.id).first()
    if item:
        item.quantity_requested += quantity
        if item.quantity_delivered < item.quantity_requested:
            item.status = TicketItemStatus.REQUESTED
    else:
        item = TicketItem(
            ticket_id=ticket.id,
            material_id=material.id,
            quantity_requested=quantity,
            quantity_delivered=0,
            quantity_returned=0,
            status=TicketItemStatus.REQUESTED,
        )
        db.session.add(item)

    sync_ticket_ready_status(ticket)

    admins = User.query.filter(User.role.in_(["ADMIN", "SUPERADMIN"])).all()
    notifications: list[Notification] = []
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            title="Solicitud urgente en ticket activo",
            message=f"{actor_user.email} agregó {quantity} de {material.name} al ticket #{ticket.id}.",
            link=url_for("reservations.admin_ticket_detail", ticket_id=ticket.id),
        )
        db.session.add(notif)
        notifications.append(notif)

    log_event(
        module="LAB_TICKETS",
        action="LAB_TICKET_ITEM_REQUESTED_BY_USER",
        user_id=actor_user.id,
        entity_label=f"LabTicket #{ticket.id}",
        description=f"Usuario agregó material al ticket activo #{ticket.id}",
        metadata={"ticket_id": ticket.id, "material_id": material.id, "quantity_added": quantity},
        material_id=material.id,
    )

    db.session.commit()
    return ServiceResult.success(
        notifications=notifications,
        item=item,
        ticket=ticket,
    )


def request_ticket_closure(ticket: LabTicket, actor_user: User) -> ServiceResult:
    active_result = validate_ticket_active(ticket)
    if not active_result.ok:
        return ServiceResult.failure("Solo puedes solicitar cierre para tickets activos.")

    ticket.status = LabTicketStatus.CLOSURE_REQUESTED

    admins = User.query.filter(User.role.in_(["ADMIN", "SUPERADMIN"])).all()
    notifications = []
    for admin in admins:
        notif = Notification(
            user_id=admin.id,
            title="Solicitud de cierre de ticket",
            message=f"{actor_user.email} solicitó el cierre del ticket #{ticket.id}.",
            link=url_for("reservations.admin_ticket_detail", ticket_id=ticket.id),
        )
        db.session.add(notif)
        notifications.append(notif)

    log_event(
        module="LAB_TICKETS",
        action="LAB_TICKET_CLOSE_REQUESTED_BY_USER",
        user_id=actor_user.id,
        entity_label=f"LabTicket #{ticket.id}",
        description=f"Usuario solicitó cierre de ticket #{ticket.id}",
        metadata={"ticket_id": ticket.id, "reservation_id": ticket.reservation_id},
    )
    db.session.commit()

    return ServiceResult.success(
        message="Solicitud de cierre enviada.",
        ticket=ticket,
        notifications=notifications,
    )


def can_close_ticket(status: str | None) -> ServiceResult:
    can_close = is_active_lab_ticket_status(status) or is_lab_ticket_closure_requested(status)
    if not can_close:
        return ServiceResult.failure("Solo se pueden cerrar tickets activos o con cierre solicitado.", can_close=False)
    return ServiceResult.success(can_close=True)


def close_ticket(ticket: LabTicket, actor_user: User) -> ServiceResult:
    close_validation = can_close_ticket(ticket.status)
    if not close_validation.ok:
        return close_validation

    has_missing = False
    created_debt_ids: list[int] = []
    previous_ticket_status = ticket.status

    for item in ticket.items:
        missing_qty = item.quantity_delivered - item.quantity_returned
        if missing_qty > 0:
            has_missing = True
            item.status = TicketItemStatus.MISSING
            debt = create_debt_for_ticket(ticket=ticket, item=item, missing_qty=missing_qty, actor_user_id=actor_user.id)
            if debt:
                created_debt_ids.append(debt.id)

    ticket.status = LabTicketStatus.CLOSED_WITH_DEBT if has_missing else LabTicketStatus.CLOSED
    ticket.closed_by_user_id = actor_user.id
    ticket.closed_at = datetime.now()

    close_notification = Notification(
        user_id=ticket.owner_user_id,
        title="Ticket de reservación cerrado",
        message=f"Tu ticket #{ticket.id} se cerró con estado {ticket.status}.",
        link=url_for("reservations.my_reservations"),
    )
    db.session.add(close_notification)

    admin_notifications: list[Notification] = []
    if created_debt_ids:
        admins = User.query.filter(User.role.in_(["ADMIN", "SUPERADMIN"])).all()
        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                title="Adeudo generado por cierre de ticket",
                message=f"El ticket #{ticket.id} cerró con adeudo. Revisa deudor y seguimiento.",
                link=url_for("debts.admin_list"),
            )
            db.session.add(notif)
            admin_notifications.append(notif)

    log_event(
        module="LAB_TICKETS",
        action="LAB_TICKET_CLOSED",
        user_id=actor_user.id,
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

    return ServiceResult.success(
        close_notification=close_notification,
        admin_notifications=admin_notifications,
        created_debt_ids=created_debt_ids,
        ticket=ticket,
    )
