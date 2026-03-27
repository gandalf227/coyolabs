import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models.user import User
from app.services.email_service import send_email
from app.services.token_service import confirm_verify_token, generate_verify_token
from app.utils.landing import resolve_landing_endpoint
from app.utils.roles import ROLE_PENDING, infer_role_from_email


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
EMAIL_CHANGE_LIMIT_PER_HOUR = 3
INSTITUTIONAL_EMAIL_RE = re.compile(r"^(\d{8}|[a-z]+(?:\.[a-z]+)*)@utpn\.edu\.mx$")


def _render_auth(mode: str = "login"):
    """
    Renderiza la vista unificada auth/auth.html.
    mode: "login" | "register"
    """
    mode = (mode or "login").lower()
    if mode not in {"login", "register"}:
        mode = "login"
    return render_template(
        "auth/auth.html",
        mode=mode,
        pending_verify_email=session.get("pending_verify_email"),
    )


def _get_pending_verify_user() -> User | None:
    user_id = session.get("pending_verify_user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def _store_pending_verify_user(user: User) -> None:
    user_id = getattr(user, "id", None)
    email = getattr(user, "email", None)
    if not isinstance(user_id, int):
        return
    if not isinstance(email, str):
        return
    session["pending_verify_user_id"] = user_id
    session["pending_verify_email"] = email


def _bad_register_request(message: str):
    if request.is_json:
        return jsonify({"error": message}), 400

    flash(message)
    return _render_auth("register"), 400


@auth_bp.route("/", methods=["GET"])
def auth_page():
    # Si ya está logueado, no muestres la pantalla de acceso
    if current_user.is_authenticated:
        return redirect(url_for(resolve_landing_endpoint(current_user.role)))

    # permite /auth/?mode=register
    mode = request.args.get("mode", "login")
    return _render_auth(mode)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(resolve_landing_endpoint(current_user.role)))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Credenciales incorrectas.")
            return redirect(url_for("auth.auth_page", mode="login"))

        if not user.is_active:
            flash("Tu cuenta está desactivada. Contacta al administrador.")
            return redirect(url_for("auth.auth_page", mode="login"))

        if user.is_banned:
            flash("Tu cuenta está bloqueada. Contacta al administrador.")
            return redirect(url_for("auth.auth_page", mode="login"))

        # Bloqueo por verificación
        if not user.is_verified:
            _store_pending_verify_user(user)
            flash("Verifica tu correo")
            return redirect(url_for("auth.auth_page", mode="login"))

        if user.role == ROLE_PENDING:
            flash("Cuenta pendiente de aprobación por administrador.")
            return redirect(url_for("auth.auth_page", mode="login"))

        login_user(user)
        if not user.profile_completed:
            return redirect(url_for("profile.complete_profile"))
        return redirect(url_for(resolve_landing_endpoint(user.role)))

    # GET -> vista unificada
    return redirect(url_for("auth.auth_page", mode="login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for(resolve_landing_endpoint(current_user.role)))

    if request.method == "POST":
        data = (request.get_json(silent=True) or {}) if request.is_json else request.form

        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        confirm_password = (
            data.get("confirm_password")
            or data.get("confirmPassword")
            or data.get("password_confirm")
            or ""
        )

        if not confirm_password:
            return _bad_register_request("confirm_password es obligatorio.")

        if password != confirm_password:
            return _bad_register_request("Las contraseñas no coinciden.")

        inferred_role = infer_role_from_email(email)
        if inferred_role is None:
            flash(
                "Formato de correo no válido. Usa matrícula@utpn.edu.mx o nombre.apellido@utpn.edu.mx."
            )
            return redirect(url_for("auth.auth_page", mode="register"))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.")
            return redirect(url_for("auth.auth_page", mode="register"))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("Ese correo ya está registrado. Si no verificaste tu cuenta, revisa tu correo o solicita reenvío.")
            return redirect(url_for("auth.auth_page", mode="login"))

        # Crear usuario no verificado
        user = User(email=email, role=inferred_role, is_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Generar token y enviar email
        token = generate_verify_token(email, user.verify_token_version or 0)
        base_url = current_app.config.get("APP_BASE_URL", "http://127.0.0.1:5000")
        verify_link = f"{base_url}/auth/verify/{token}"

        subject = "Verifica tu cuenta - Sistema de Laboratorios"
        body = (
            "Hola.\n\n"
            "Para activar tu cuenta institucional, abre este enlace:\n\n"
            f"{verify_link}\n\n"
            "Este enlace expira en 1 hora.\n"
        )

        send_email(email, subject, body)

        _store_pending_verify_user(user)
        flash("Verifica tu correo")
        return redirect(url_for("auth.auth_page", mode="login"))

    # GET -> vista unificada
    return redirect(url_for("auth.auth_page", mode="register"))


@auth_bp.route("/verify/<token>", methods=["GET"])
def verify(token):
    token_data = confirm_verify_token(token, max_age_seconds=3600)
    if not token_data:
        flash("Token inválido o expirado")
        return redirect(url_for("auth.auth_page", mode="login"))

    email = str(token_data.get("email") or "").strip().lower()
    token_version = int(token_data.get("token_version") or 0)

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Usuario no encontrado.")
        return redirect(url_for("auth.auth_page", mode="register"))
    if token_version != (user.verify_token_version or 0):
        flash("Token inválido o expirado")
        return redirect(url_for("auth.auth_page", mode="login"))

    if user.is_verified:
        flash("Correo verificado")
        login_user(user)
        if not user.profile_completed:
            return redirect(url_for("profile.complete_profile"))
        return redirect(url_for(resolve_landing_endpoint(user.role)))

    user.is_verified = True
    user.verified_at = db.func.now()
    user.email_change_count = 0
    user.email_change_window_started_at = None
    db.session.commit()

    session.pop("pending_verify_user_id", None)
    session.pop("pending_verify_email", None)
    flash("Correo verificado")
    login_user(user)
    if not user.profile_completed:
        return redirect(url_for("profile.complete_profile"))
    return redirect(url_for(resolve_landing_endpoint(user.role)))


@auth_bp.route("/change-email", methods=["POST"])
def change_email():
    user = _get_pending_verify_user()
    if not user:
        return jsonify({"error": "No hay una cuenta pendiente de verificación en esta sesión."}), 401

    if user.is_verified:
        return jsonify({"error": "La cuenta ya está verificada. No es necesario cambiar correo."}), 400

    now = datetime.utcnow()
    window_start = user.email_change_window_started_at
    if not window_start or (now - window_start) >= timedelta(hours=1):
        user.email_change_window_started_at = now
        user.email_change_count = 0

    if (user.email_change_count or 0) >= EMAIL_CHANGE_LIMIT_PER_HOUR:
        return jsonify({"error": "Límite alcanzado: máximo 3 cambios de correo por hora."}), 429

    data = (request.get_json(silent=True) or {}) if request.is_json else request.form
    new_email = (data.get("email") or "").strip().lower()
    if not new_email:
        return jsonify({"error": "El correo es obligatorio."}), 400
    if not INSTITUTIONAL_EMAIL_RE.match(new_email):
        return jsonify(
            {"error": "Formato de correo no válido. Usa matrícula@utpn.edu.mx o nombre.apellido@utpn.edu.mx."}
        ), 400

    inferred_role = infer_role_from_email(new_email)
    if inferred_role is None:
        return jsonify(
            {"error": "Formato de correo no válido. Usa matrícula@utpn.edu.mx o nombre.apellido@utpn.edu.mx."}
        ), 400

    existing = User.query.filter(User.email == new_email, User.id != user.id).first()
    if existing:
        return jsonify({"error": "Ese correo ya está registrado en otra cuenta."}), 409

    user.email = new_email
    user.role = inferred_role
    user.is_verified = False
    user.verified_at = None
    user.verify_token_version = (user.verify_token_version or 0) + 1
    user.email_change_count = (user.email_change_count or 0) + 1

    token = generate_verify_token(user.email, user.verify_token_version)
    base_url = current_app.config.get("APP_BASE_URL", "http://127.0.0.1:5000")
    verify_link = f"{base_url}/auth/verify/{token}"

    subject = "Verifica tu cuenta - Sistema de Laboratorios"
    body = (
        "Hola.\n\n"
        "Actualizamos tu correo de acceso. Verifica tu cuenta con este enlace:\n\n"
        f"{verify_link}\n\n"
        "Este enlace expira en 1 hora.\n"
    )

    send_email(user.email, subject, body)
    db.session.commit()

    _store_pending_verify_user(user)
    return jsonify({"message": "Correo actualizado y código reenviado."}), 200


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.auth_page", mode="login"))


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
    }
