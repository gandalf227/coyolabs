from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user

from app.utils.roles import is_admin_role
from app.utils.authz import min_role_required
from app.utils.permission_required import permission_required

from app.extensions import db
from app.models.debt import Debt
from app.models.user import User
from app.models.material import Material


debts_bp = Blueprint("debts", __name__, url_prefix="/debts")


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

    debt.status = "PAID"
    db.session.commit()

    flash("Adeudo marcado como pagado.", "success")
    return redirect(url_for("debts.admin_list"))