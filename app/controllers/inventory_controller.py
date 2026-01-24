from math import ceil
from flask import Blueprint, render_template, request, abort


from app.models.lab import Lab
from app.models.material import Material
from app.utils.authz import min_role_required



inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@inventory_bp.route("/", methods=["GET"])
@min_role_required("USER")
def inventory_list():
    lab_id = request.args.get("lab_id", type=int)
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", type=int) or 1

    PER_PAGE = 50
    if page < 1:
        page = 1

    labs = Lab.query.order_by(Lab.name).all()

    query = Material.query
    if lab_id:
        query = query.filter(Material.lab_id == lab_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Material.name.ilike(like)) |
            (Material.location.ilike(like)) |
            (Material.code.ilike(like)) |
            (Material.serial.ilike(like)) |
            (Material.notes.ilike(like))
        )

    # Orden usable
    query = query.order_by(Material.lab_id, Material.location, Material.name)

    total = query.count()
    total_pages = max(1, ceil(total / PER_PAGE))

    if page > total_pages:
        page = total_pages

    materials = query.offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    return render_template(
        "inventory/inventory_list.html",
        labs=labs,
        materials=materials,
        selected_lab=lab_id,
        q=q,
        page=page,
        total=total,
        total_pages=total_pages,
        per_page=PER_PAGE,
    )


@inventory_bp.route("/materials/<int:material_id>", methods=["GET"])
@min_role_required("USER")
def material_detail(material_id: int):
    m = Material.query.get(material_id)
    if not m:
        abort(404)
    return render_template("inventory/material_detail.html", material=m)

@inventory_bp.route("/admin-check", methods=["GET"])
@min_role_required("ADMIN")
def admin_check():
    return "OK: ADMIN access", 200



