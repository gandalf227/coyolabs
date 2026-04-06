import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.print3d_job import Print3DJob
from app.services.audit_service import log_event
from app.utils.authz import min_role_required
from app.utils.roles import is_admin_role
from app.utils.statuses import Print3DJobStatus, PRINT3D_ALLOWED_STATUSES, PRINT3D_ALLOWED_TRANSITIONS


print3d_bp = Blueprint("print3d", __name__, url_prefix="/prints3d")

ALLOWED_PRINT3D_EXTENSIONS = {"stl", "obj", "3mf", "gcode"}
MAX_PRINT3D_FILE_SIZE_BYTES = 25 * 1024 * 1024
STATUS_REQUESTED = Print3DJobStatus.REQUESTED


def _normalize_print3d_status(raw_status: str | None) -> str:
    return (raw_status or "").strip().upper()


def _can_transition_status(current_status: str, next_status: str) -> bool:
    allowed = PRINT3D_ALLOWED_TRANSITIONS.get(current_status, set())
    return next_status in allowed


def _status_badge_class(status: str | None) -> str:
    normalized = _normalize_print3d_status(status)
    if normalized in {Print3DJobStatus.READY, Print3DJobStatus.DELIVERED}:
        return "status-ok"
    if normalized == Print3DJobStatus.CANCELED:
        return "status-bad"
    if normalized == Print3DJobStatus.IN_PROGRESS:
        return "status-neutral"
    return "status-warn"


def _save_print3d_file(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None, "Debes adjuntar un archivo para la impresión 3D."

    raw_name = secure_filename(file_storage.filename or "")
    if "." not in raw_name:
        return None, None, "El archivo debe incluir una extensión válida (.stl, .obj, .3mf, .gcode)."

    ext = raw_name.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_PRINT3D_EXTENSIONS:
        return None, None, "Tipo de archivo no permitido. Usa STL, OBJ, 3MF o GCODE."

    file_storage.stream.seek(0, os.SEEK_END)
    size_bytes = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size_bytes <= 0:
        return None, None, "El archivo adjunto está vacío."
    if size_bytes > MAX_PRINT3D_FILE_SIZE_BYTES:
        return None, None, "El archivo supera el tamaño máximo permitido (25 MB)."

    uploads_rel_dir = os.path.join("uploads", "prints3d")
    uploads_abs_dir = os.path.join(current_app.root_path, "static", uploads_rel_dir)
    os.makedirs(uploads_abs_dir, exist_ok=True)

    unique_name = f"{uuid4().hex}.{ext}"
    abs_path = os.path.join(uploads_abs_dir, unique_name)
    file_storage.save(abs_path)

    return f"{uploads_rel_dir}/{unique_name}", raw_name, None


def _parse_decimal_field(raw_value: str, field_label: str) -> tuple[Decimal | None, str | None]:
    value = (raw_value or "").strip()
    if not value:
        return None, f"{field_label} es obligatorio."
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError):
        return None, f"{field_label} debe ser numérico."
    if parsed < 0:
        return None, f"{field_label} no puede ser negativo."
    return parsed, None


@print3d_bp.route("/my", methods=["GET"])
@min_role_required("STUDENT")
def my_jobs():
    jobs = (
        Print3DJob.query
        .filter(Print3DJob.requester_user_id == current_user.id)
        .order_by(Print3DJob.created_at.desc())
        .all()
    )
    return render_template(
        "prints3d/my_list.html",
        jobs=jobs,
        active_page="prints3d",
        status_badge_class=_status_badge_class,
    )


@print3d_bp.route("/new", methods=["GET", "POST"])
@min_role_required("STUDENT")
def new_job():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        file_storage = request.files.get("model_file")

        if not title:
            flash("El título de la solicitud es obligatorio.", "error")
            return redirect(url_for("print3d.new_job"))

        file_ref, original_filename, file_error = _save_print3d_file(file_storage)
        if file_error:
            flash(file_error, "error")
            return redirect(url_for("print3d.new_job"))

        file_size_bytes = int(file_storage.content_length or 0)
        if file_size_bytes <= 0:
            file_storage.stream.seek(0, os.SEEK_END)
            file_size_bytes = int(file_storage.stream.tell())
            file_storage.stream.seek(0)

        job = Print3DJob(
            requester_user_id=current_user.id,
            title=title,
            description=description or None,
            file_ref=file_ref,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            status=STATUS_REQUESTED,
        )
        db.session.add(job)
        db.session.flush()

        log_event(
            module="PRINT3D",
            action="PRINT3D_REQUEST_CREATED",
            user_id=current_user.id,
            entity_label=f"Print3DJob #{job.id}",
            description=f"Solicitud 3D creada: {job.title}",
            metadata={"job_id": job.id, "status": job.status},
        )
        db.session.commit()

        flash("Solicitud de impresión 3D creada correctamente.", "success")
        return redirect(url_for("print3d.my_jobs"))

    return render_template("prints3d/new.html", active_page="prints3d")


@print3d_bp.route("/<int:job_id>/download", methods=["GET"])
@min_role_required("STUDENT")
def download_file(job_id: int):
    job = Print3DJob.query.get_or_404(job_id)
    if job.requester_user_id != current_user.id and not is_admin_role(current_user.role):
        abort(403)

    if not job.file_ref:
        abort(404)

    ref_norm = os.path.normpath(job.file_ref)
    expected_prefix = os.path.join("uploads", "prints3d")
    if not ref_norm.startswith(expected_prefix):
        abort(404)

    rel_dir, filename = os.path.split(ref_norm)
    abs_dir = os.path.join(current_app.root_path, "static", rel_dir)
    abs_path = os.path.join(abs_dir, filename)

    if not os.path.isfile(abs_path):
        abort(404)

    log_event(
        module="PRINT3D",
        action="PRINT3D_FILE_DOWNLOADED",
        user_id=current_user.id,
        entity_label=f"Print3DJob #{job.id}",
        description="Descarga de archivo 3D",
        metadata={"job_id": job.id},
    )
    db.session.commit()

    return send_from_directory(abs_dir, filename, as_attachment=True, download_name=job.original_filename)


@print3d_bp.route("/admin", methods=["GET"])
@min_role_required("ADMIN")
def admin_list():
    jobs = (
        Print3DJob.query
        .order_by(Print3DJob.created_at.desc())
        .all()
    )
    return render_template(
        "prints3d/admin_list.html",
        jobs=jobs,
        active_page="prints3d",
        status_badge_class=_status_badge_class,
        print3d_statuses=[
            Print3DJobStatus.REQUESTED,
            Print3DJobStatus.QUOTED,
            Print3DJobStatus.IN_PROGRESS,
            Print3DJobStatus.READY,
            Print3DJobStatus.DELIVERED,
            Print3DJobStatus.CANCELED,
        ],
    )


@print3d_bp.route("/admin/<int:job_id>/quote", methods=["POST"])
@min_role_required("ADMIN")
def admin_set_quote(job_id: int):
    job = Print3DJob.query.get_or_404(job_id)

    grams, grams_error = _parse_decimal_field(request.form.get("grams_estimated"), "Gramos estimados")
    if grams_error:
        flash(grams_error, "error")
        return redirect(url_for("print3d.admin_list"))

    price, price_error = _parse_decimal_field(request.form.get("price_per_gram"), "Precio por gramo")
    if price_error:
        flash(price_error, "error")
        return redirect(url_for("print3d.admin_list"))

    grams = grams.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    price = price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (grams * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    job.grams_estimated = grams
    job.price_per_gram = price
    job.total_estimated = total

    previous_status = _normalize_print3d_status(job.status)
    if previous_status == Print3DJobStatus.REQUESTED:
        job.status = Print3DJobStatus.QUOTED

    log_event(
        module="PRINT3D",
        action="PRINT3D_QUOTE_UPDATED",
        user_id=current_user.id,
        entity_label=f"Print3DJob #{job.id}",
        description="Cotización 3D actualizada por administración",
        metadata={
            "job_id": job.id,
            "grams_estimated": str(grams),
            "price_per_gram": str(price),
            "total_estimated": str(total),
            "status": job.status,
        },
    )

    if previous_status != job.status:
        log_event(
            module="PRINT3D",
            action="PRINT3D_STATUS_CHANGED",
            user_id=current_user.id,
            entity_label=f"Print3DJob #{job.id}",
            description=f"Estado de impresión 3D cambiado de {previous_status} a {job.status}",
            metadata={"job_id": job.id, "from": previous_status, "to": job.status, "reason": "quote_updated"},
        )

    db.session.commit()

    flash("Cotización guardada correctamente.", "success")
    return redirect(url_for("print3d.admin_list"))


@print3d_bp.route("/admin/<int:job_id>/status", methods=["POST"])
@min_role_required("ADMIN")
def admin_set_status(job_id: int):
    job = Print3DJob.query.get_or_404(job_id)

    target_status = _normalize_print3d_status(request.form.get("status"))
    current_status = _normalize_print3d_status(job.status)

    if target_status not in PRINT3D_ALLOWED_STATUSES:
        flash("Estado de impresión 3D no válido.", "error")
        return redirect(url_for("print3d.admin_list"))

    if current_status == target_status:
        flash("El trabajo ya se encuentra en ese estado.", "info")
        return redirect(url_for("print3d.admin_list"))

    if not _can_transition_status(current_status, target_status):
        flash("Transición de estado no permitida para este trabajo.", "error")
        return redirect(url_for("print3d.admin_list"))

    job.status = target_status

    log_event(
        module="PRINT3D",
        action="PRINT3D_STATUS_CHANGED",
        user_id=current_user.id,
        entity_label=f"Print3DJob #{job.id}",
        description=f"Estado de impresión 3D cambiado de {current_status} a {target_status}",
        metadata={"job_id": job.id, "from": current_status, "to": target_status},
    )
    db.session.commit()

    flash("Estado actualizado correctamente.", "success")
    return redirect(url_for("print3d.admin_list"))
