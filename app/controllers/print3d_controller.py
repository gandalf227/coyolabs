import os
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.print3d_job import Print3DJob
from app.services.audit_service import log_event
from app.utils.authz import min_role_required
from app.utils.roles import is_admin_role
from app.utils.statuses import Print3DJobStatus


print3d_bp = Blueprint("print3d", __name__, url_prefix="/prints3d")

ALLOWED_PRINT3D_EXTENSIONS = {"stl", "obj", "3mf", "gcode"}
MAX_PRINT3D_FILE_SIZE_BYTES = 25 * 1024 * 1024
STATUS_REQUESTED = Print3DJobStatus.REQUESTED


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


@print3d_bp.route("/my", methods=["GET"])
@min_role_required("STUDENT")
def my_jobs():
    jobs = (
        Print3DJob.query
        .filter(Print3DJob.requester_user_id == current_user.id)
        .order_by(Print3DJob.created_at.desc())
        .all()
    )
    return render_template("prints3d/my_list.html", jobs=jobs, active_page="prints3d")


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
    return render_template("prints3d/admin_list.html", jobs=jobs, active_page="prints3d")
