import csv
from io import StringIO, BytesIO
from flask import Blueprint, Response, render_template, request
from sqlalchemy import func
from app.models.lab import Lab
from app.models.material import Material
from app.models.debt import Debt
from app.models.inventory_request_ticket import InventoryRequestTicket
from app.models.critical_action_request import CriticalActionRequest
from app.models.logbook import LogbookEvent
from app.models.reservation import Reservation
from app.models.lost_found import LostFound
from app.models.software import Software
from app.utils.authz import min_role_required
from app.extensions import db

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def csv_response(filename: str, headers: list[str], rows: list[list]):
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)

    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_inventory_rows(lab_id=None):
    q = Material.query
    if lab_id:
        q = q.filter(Material.lab_id == lab_id)

    items = q.order_by(Material.lab_id, Material.location, Material.name).all()

    headers = [
        "id", "lab_id", "name", "location", "status",
        "pieces_text", "pieces_qty", "brand", "model", "code", "serial",
        "notes", "tutorial_url", "image_ref",
        "source_file", "source_sheet", "source_row",
        "created_at", "updated_at",
    ]

    rows = []
    for m in items:
        rows.append([
            m.id, m.lab_id, m.name, m.location, m.status,
            m.pieces_text, m.pieces_qty, m.brand, m.model, m.code, m.serial,
            m.notes, m.tutorial_url, m.image_ref,
            m.source_file, m.source_sheet, m.source_row,
            getattr(m, "created_at", None), getattr(m, "updated_at", None),
        ])
    return headers, rows


def build_debts_rows():
    items = Debt.query.order_by(Debt.created_at.desc()).all()
    headers = ["id", "user_id", "material_id", "status", "reason", "amount", "created_at", "closed_at"]
    rows = []
    for d in items:
        rows.append([
            d.id, d.user_id, d.material_id, d.status, d.reason, d.amount, d.created_at, d.closed_at
        ])
    return headers, rows


def build_logbook_rows():
    items = LogbookEvent.query.order_by(LogbookEvent.created_at.desc()).all()
    headers = ["id", "user_id", "material_id", "module", "entity_label", "action", "description", "metadata_json", "created_at"]
    rows = []
    for e in items:
        rows.append([
            e.id, e.user_id, e.material_id, e.module, e.entity_label, e.action, e.description, e.metadata_json, e.created_at
        ])
    return headers, rows


def build_reservations_rows():
    items = Reservation.query.order_by(Reservation.created_at.desc()).all()
    headers = [
        "id", "user_id", "room", "date", "start_time", "end_time", "status",
        "group_name", "teacher_name", "subject", "signed",
        "admin_note", "purpose", "exit_time", "teacher_comments", "created_at",
    ]
    rows = []
    for r in items:
        rows.append([
            r.id, r.user_id, r.room, r.date, r.start_time, r.end_time, r.status,
            getattr(r, "group_name", None), getattr(r, "teacher_name", None), getattr(r, "subject", None),
            getattr(r, "signed", None),
            r.admin_note, r.purpose, getattr(r, "exit_time", None), getattr(r, "teacher_comments", None),
            r.created_at,
        ])
    return headers, rows


def build_lostfound_rows():
    items = LostFound.query.order_by(LostFound.created_at.desc()).all()
    headers = [
        "id", "reported_by_user_id", "material_id", "title", "description",
        "location", "evidence_ref", "status", "admin_note", "created_at",
    ]
    rows = []
    for it in items:
        rows.append([
            it.id, it.reported_by_user_id, it.material_id, it.title, it.description,
            it.location, it.evidence_ref, it.status, it.admin_note, it.created_at,
        ])
    return headers, rows


def build_software_rows():
    items = Software.query.order_by(Software.name.asc()).all()
    headers = [
        "id", "lab_id", "name", "version", "license_type", "notes",
        "update_requested", "update_note", "created_at",
    ]
    rows = []
    for s in items:
        rows.append([
            s.id, s.lab_id, s.name, s.version, s.license_type, s.notes,
            s.update_requested, s.update_note, s.created_at,
        ])
    return headers, rows


def render_report_view(report_title, headers, rows, download_url, report_description=None, extra_meta=None):
    return render_template(
        "reports/report_view.html",
        report_title=report_title,
        columns=headers,
        rows=rows,
        download_url=download_url,
        report_description=report_description,
        extra_meta=extra_meta,
        active_page="reports",
    )


@reports_bp.route("/", methods=["GET"])
@min_role_required("ADMIN")
def reports_home():
    labs = Lab.query.order_by(Lab.name).all()

    reservations_by_status = (
        db.session.query(Reservation.status, func.count(Reservation.id))
        .group_by(Reservation.status)
        .order_by(func.count(Reservation.id).desc())
        .all()
    )

    room_usage = (
        db.session.query(Reservation.room, func.count(Reservation.id).label("total"))
        .group_by(Reservation.room)
        .order_by(func.count(Reservation.id).desc())
        .limit(10)
        .all()
    )

    inventory_daily_by_status = (
        db.session.query(InventoryRequestTicket.status, func.count(InventoryRequestTicket.id))
        .group_by(InventoryRequestTicket.status)
        .order_by(func.count(InventoryRequestTicket.id).desc())
        .all()
    )
    recent_inventory_tickets = (
        InventoryRequestTicket.query
        .order_by(InventoryRequestTicket.request_date.desc(), InventoryRequestTicket.created_at.desc())
        .limit(10)
        .all()
    )

    open_debts_count = Debt.query.filter(Debt.status == "OPEN").count()
    open_debts_by_user = (
        db.session.query(Debt.user_id, func.count(Debt.id).label("total"))
        .filter(Debt.status == "OPEN")
        .group_by(Debt.user_id)
        .order_by(func.count(Debt.id).desc())
        .limit(10)
        .all()
    )

    critical_actions_by_status = (
        db.session.query(CriticalActionRequest.status, func.count(CriticalActionRequest.id))
        .group_by(CriticalActionRequest.status)
        .order_by(func.count(CriticalActionRequest.id).desc())
        .all()
    )

    logbook_by_module = (
        db.session.query(func.coalesce(LogbookEvent.module, "SIN_MODULO"), func.count(LogbookEvent.id))
        .group_by(func.coalesce(LogbookEvent.module, "SIN_MODULO"))
        .order_by(func.count(LogbookEvent.id).desc())
        .all()
    )

    reservations_total = sum(total for _, total in reservations_by_status)
    inventory_daily_total = sum(total for _, total in inventory_daily_by_status)

    return render_template(
        "reports/home.html",
        labs=labs,
        reservations_by_status=reservations_by_status,
        room_usage=room_usage,
        inventory_daily_by_status=inventory_daily_by_status,
        recent_inventory_tickets=recent_inventory_tickets,
        open_debts_count=open_debts_count,
        open_debts_by_user=open_debts_by_user,
        critical_actions_by_status=critical_actions_by_status,
        logbook_by_module=logbook_by_module,
        reservations_total=reservations_total,
        inventory_daily_total=inventory_daily_total,
        active_page="reports",
    )


@reports_bp.route("/inventory.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_inventory():
    lab_id = request.args.get("lab_id", type=int)
    headers, rows = build_inventory_rows(lab_id=lab_id)
    fname = "inventory.csv" if not lab_id else f"inventory_lab_{lab_id}.csv"
    return csv_response(fname, headers, rows)


@reports_bp.route("/view/inventory", methods=["GET"])
@min_role_required("ADMIN")
def report_inventory_view():
    lab_id = request.args.get("lab_id", type=int)
    headers, rows = build_inventory_rows(lab_id=lab_id)

    report_title = "Inventario general"
    extra_meta = None
    if lab_id:
        lab = Lab.query.get(lab_id)
        report_title = f"Inventario - {lab.name if lab else f'Lab {lab_id}'}"
        extra_meta = f"Lab ID: {lab_id}"

    return render_report_view(
        report_title=report_title,
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + request.path.replace("/view/inventory", "/inventory.csv") + (f"?lab_id={lab_id}" if lab_id else ""),
        report_description="Vista completa del inventario.",
        extra_meta=extra_meta,
    )


@reports_bp.route("/debts.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_debts():
    headers, rows = build_debts_rows()
    return csv_response("debts.csv", headers, rows)


@reports_bp.route("/view/debts", methods=["GET"])
@min_role_required("ADMIN")
def report_debts_view():
    headers, rows = build_debts_rows()
    return render_report_view(
        report_title="Adeudos",
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + "/reports/debts.csv",
        report_description="Vista completa de los adeudos registrados.",
    )


@reports_bp.route("/logbook.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_logbook():
    headers, rows = build_logbook_rows()
    return csv_response("logbook.csv", headers, rows)


@reports_bp.route("/view/logbook", methods=["GET"])
@min_role_required("ADMIN")
def report_logbook_view():
    headers, rows = build_logbook_rows()
    return render_report_view(
        report_title="Bitácora",
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + "/reports/logbook.csv",
        report_description="Vista completa de la bitácora.",
    )


@reports_bp.route("/reservations.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_reservations():
    headers, rows = build_reservations_rows()
    return csv_response("reservations.csv", headers, rows)


@reports_bp.route("/view/reservations", methods=["GET"])
@min_role_required("ADMIN")
def report_reservations_view():
    headers, rows = build_reservations_rows()
    return render_report_view(
        report_title="Reservaciones",
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + "/reports/reservations.csv",
        report_description="Vista completa de reservaciones.",
    )


@reports_bp.route("/lostfound.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_lostfound():
    headers, rows = build_lostfound_rows()
    return csv_response("lostfound.csv", headers, rows)


@reports_bp.route("/view/lostfound", methods=["GET"])
@min_role_required("ADMIN")
def report_lostfound_view():
    headers, rows = build_lostfound_rows()
    return render_report_view(
        report_title="Objetos perdidos",
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + "/reports/lostfound.csv",
        report_description="Vista completa de objetos perdidos.",
    )


@reports_bp.route("/software.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_software():
    headers, rows = build_software_rows()
    return csv_response("software.csv", headers, rows)


@reports_bp.route("/view/software", methods=["GET"])
@min_role_required("ADMIN")
def report_software_view():
    headers, rows = build_software_rows()
    return render_report_view(
        report_title="Software",
        headers=headers,
        rows=rows,
        download_url=request.url_root.rstrip("/") + "/reports/software.csv",
        report_description="Vista completa del software registrado.",
    )


@reports_bp.route("/logbook", methods=["GET"])
@min_role_required("ADMIN")
def logbook_admin_view():
    action = (request.args.get("action") or "").strip()
    module = (request.args.get("module") or "").strip()
    user_id = request.args.get("user_id", type=int)
    material_id = request.args.get("material_id", type=int)

    q = LogbookEvent.query

    if action:
        q = q.filter(LogbookEvent.action.ilike(f"%{action}%"))
    if module:
        q = q.filter(LogbookEvent.module.ilike(f"%{module}%"))
    if user_id:
        q = q.filter(LogbookEvent.user_id == user_id)
    if material_id:
        q = q.filter(LogbookEvent.material_id == material_id)

    events = q.order_by(LogbookEvent.created_at.desc()).limit(500).all()

    return render_template(
        "reports/logbook_admin.html",
        events=events,
        action=action,
        module=module,
        user_id=user_id,
        material_id=material_id,
        active_page="reports",
    )


@reports_bp.route("/inventory.pdf", methods=["GET"])
@min_role_required("ADMIN")
def report_inventory_pdf():
    lab_id = request.args.get("lab_id", type=int)
    download = request.args.get("download", default=0, type=int)

    q = Material.query
    if lab_id:
        q = q.filter(Material.lab_id == lab_id)

    items = q.order_by(Material.lab_id, Material.location, Material.name).all()

    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=letter)
    width, height = letter

    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    title = "Reporte de Inventario"
    if lab_id:
        title += f" (Lab ID: {lab_id})"
    c.drawString(40, y, title)

    y -= 25
    c.setFont("Helvetica", 9)
    c.drawString(40, y, "ID | Lab | Ubicación | Código | Nombre | Estado")
    y -= 15

    for m in items:
        line = f"{m.id} | {m.lab_id} | {m.location or ''} | {m.code or ''} | {m.name or ''} | {m.status or ''}"
        if len(line) > 140:
            line = line[:140] + "..."
        c.drawString(40, y, line)
        y -= 12

        if y < 60:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 9)

    c.save()
    bio.seek(0)

    filename = "inventory.pdf" if not lab_id else f"inventory_lab_{lab_id}.pdf"
    disposition = "attachment" if download == 1 else "inline"

    return Response(
        bio.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
