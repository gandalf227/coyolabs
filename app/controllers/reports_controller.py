import csv
from io import StringIO, BytesIO
from flask import Blueprint, Response, render_template, request
from flask_login import current_user

from app.models.lab import Lab
from app.models.material import Material
from app.models.debt import Debt
from app.models.logbook import LogbookEvent
from app.models.reservation import Reservation
from app.models.lost_found import LostFound
from app.models.software import Software
from app.utils.authz import min_role_required

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def csv_response(filename: str, headers: list[str], rows: list[list]):
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)

    data = buf.getvalue().encode("utf-8-sig")  # BOM para Excel
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@reports_bp.route("/", methods=["GET"])
@min_role_required("ADMIN")
def reports_home():
    labs = Lab.query.order_by(Lab.name).all()
    return render_template("reports/home.html", labs=labs)


@reports_bp.route("/inventory.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_inventory():
    lab_id = request.args.get("lab_id", type=int)

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

    fname = "inventory.csv" if not lab_id else f"inventory_lab_{lab_id}.csv"
    return csv_response(fname, headers, rows)


@reports_bp.route("/debts.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_debts():
    items = Debt.query.order_by(Debt.created_at.desc()).all()

    headers = ["id", "user_id", "material_id", "status", "reason", "amount", "created_at", "closed_at"]
    rows = []
    for d in items:
        rows.append([
            d.id, d.user_id, d.material_id, d.status, d.reason, d.amount, d.created_at, d.closed_at
        ])
    return csv_response("debts.csv", headers, rows)


@reports_bp.route("/logbook.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_logbook():
    items = LogbookEvent.query.order_by(LogbookEvent.created_at.desc()).all()

    headers = ["id", "user_id", "material_id", "action", "description", "metadata_json", "created_at"]
    rows = []
    for e in items:
        rows.append([
            e.id, e.user_id, e.material_id, e.action, e.description, e.metadata_json, e.created_at
        ])
    return csv_response("logbook.csv", headers, rows)


@reports_bp.route("/reservations.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_reservations():
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
    return csv_response("reservations.csv", headers, rows)


@reports_bp.route("/lostfound.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_lostfound():
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
    return csv_response("lostfound.csv", headers, rows)


@reports_bp.route("/software.csv", methods=["GET"])
@min_role_required("ADMIN")
def report_software():
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
    return csv_response("software.csv", headers, rows)

    
@reports_bp.route("/logbook", methods=["GET"])
@min_role_required("ADMIN")
def logbook_admin_view():
    action = (request.args.get("action") or "").strip()
    user_id = request.args.get("user_id", type=int)
    material_id = request.args.get("material_id", type=int)

    q = LogbookEvent.query

    if action:
        q = q.filter(LogbookEvent.action.ilike(f"%{action}%"))
    if user_id:
        q = q.filter(LogbookEvent.user_id == user_id)
    if material_id:
        q = q.filter(LogbookEvent.material_id == material_id)

    events = q.order_by(LogbookEvent.created_at.desc()).limit(500).all()

    return render_template(
        "reports/logbook_admin.html",
        events=events,
        action=action,
        user_id=user_id,
        material_id=material_id,
    )


@reports_bp.route("/inventory.pdf", methods=["GET"])
@min_role_required("ADMIN")
def report_inventory_pdf():
    lab_id = request.args.get("lab_id", type=int)

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
    return Response(
        bio.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

