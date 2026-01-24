from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from app.extensions import db
from app.models.lost_found import LostFound
from app.models.material import Material
from app.utils.authz import min_role_required


lostfound_bp = Blueprint("lostfound", __name__, url_prefix="/lostfound")


@lostfound_bp.route("/", methods=["GET"])
@min_role_required("USER")
def list_items():
    status = (request.args.get("status") or "").strip().upper()

    q = LostFound.query
    if status in {"REPORTED", "IN_STORAGE", "RETURNED"}:
        q = q.filter(LostFound.status == status)

    items = q.order_by(LostFound.created_at.desc()).all()
    return render_template("lostfound/list.html", items=items, status=status)


@lostfound_bp.route("/<int:item_id>", methods=["GET"])
@min_role_required("USER")
def detail(item_id: int):
    item = LostFound.query.get(item_id)
    if not item:
        abort(404)
    return render_template("lostfound/detail.html", item=item)


@lostfound_bp.route("/admin/new", methods=["GET", "POST"])
@min_role_required("ADMIN")
def admin_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        description = (request.form.get("description") or "").strip()
        location = (request.form.get("location") or "").strip()
        evidence_ref = (request.form.get("evidence_ref") or "").strip()
        material_id = request.form.get("material_id")

        if not title:
            flash("El título es obligatorio.", "error")
            return redirect(url_for("lostfound.admin_new"))

        mat = None
        if material_id:
            try:
                material_id_int = int(material_id)
                mat = Material.query.get(material_id_int)
                if not mat:
                    flash("material_id no existe.", "error")
                    return redirect(url_for("lostfound.admin_new"))
            except ValueError:
                flash("material_id inválido.", "error")
                return redirect(url_for("lostfound.admin_new"))

        item = LostFound(
            reported_by_user_id=getattr(current_user, "id", None),
            material_id=mat.id if mat else None,
            title=title,
            description=description or None,
            location=location or None,
            evidence_ref=evidence_ref or None,
            status="REPORTED",
        )

        db.session.add(item)
        db.session.commit()

        flash("Registro creado.", "success")
        return redirect(url_for("lostfound.detail", item_id=item.id))

    return render_template("lostfound/admin_new.html")


@lostfound_bp.route("/admin/<int:item_id>/status", methods=["POST"])
@min_role_required("ADMIN")
def admin_set_status(item_id: int):
    item = LostFound.query.get(item_id)
    if not item:
        abort(404)

    new_status = (request.form.get("status") or "").strip().upper()
    admin_note = (request.form.get("admin_note") or "").strip()

    if new_status not in {"REPORTED", "IN_STORAGE", "RETURNED"}:
        flash("Status inválido.", "error")
        return redirect(url_for("lostfound.detail", item_id=item.id))

    item.status = new_status
    item.admin_note = admin_note or None
    db.session.commit()

    flash("Estado actualizado.", "success")
    return redirect(url_for("lostfound.detail", item_id=item.id))
