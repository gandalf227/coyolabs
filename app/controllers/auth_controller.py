import re
from flask import current_app
from app.extensions import db
from app.services.email_service import send_email
from app.services.token_service import generate_verify_token, confirm_verify_token
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Si ya está logueado, no le mostramos el login
    if current_user.is_authenticated:
        return redirect(url_for("auth.me"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash("Credenciales incorrectas.")
            return redirect(url_for("auth.login"))

        # Bloqueo por verificación (FASE 2 hará el email)
        if not user.is_verified:
            flash("Cuenta no verificada. Revisa tu correo institucional.")
            return redirect(url_for("auth.login"))

        login_user(user)
        return redirect(url_for("auth.me"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
    }

EMAIL_DOMAIN = "utpn.edu.mx"
MATRICULA_RE = re.compile(r"^[0-9]+@utpn\.edu\.mx$")
ADMIN_RE = re.compile(r"^[a-zA-Z]+@utpn\.edu\.mx$")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        # Validación dominio
        if not email.endswith(f"@{EMAIL_DOMAIN}"):
            flash("Solo se permiten correos institucionales @utpn.edu.mx.")
            return redirect(url_for("auth.register"))

        # Validación patrón (matrícula o administrativo)
        if not (MATRICULA_RE.match(email) or ADMIN_RE.match(email)):
            flash("Formato de correo no válido. Usa matrícula@utpn.edu.mx o nombreadministrativo@utpn.edu.mx.")
            return redirect(url_for("auth.register"))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.")
            return redirect(url_for("auth.register"))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash("Ese correo ya está registrado. Si no verificaste tu cuenta, revisa tu correo o solicita reenvío.")
            return redirect(url_for("auth.login"))

        # Crear usuario no verificado
        user = User(email=email, role="ALUMNO", is_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Generar token y enviar email
        token = generate_verify_token(email)
        base_url = current_app.config.get("APP_BASE_URL", "http://127.0.0.1:5000")
        verify_link = f"{base_url}/auth/verify/{token}"
        print("\n=== VERIFY LINK (DEV) ===")
        print(verify_link)
        print("=== END VERIFY LINK ===\n")


        subject = "Verifica tu cuenta - Sistema de Laboratorios"
        body = (
            "Hola.\n\n"
            "Para activar tu cuenta institucional, abre este enlace:\n\n"
            f"{verify_link}\n\n"
            "Este enlace expira en 1 hora.\n"
        )

        send_email(email, subject, body)

        flash("Registro exitoso. Revisa tu correo institucional para verificar tu cuenta.")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/verify/<token>", methods=["GET"])
def verify(token):
    email = confirm_verify_token(token, max_age_seconds=3600)
    if not email:
        flash("Token inválido o expirado. Regístrate de nuevo o solicita reenvío.")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Usuario no encontrado.")
        return redirect(url_for("auth.register"))

    if user.is_verified:
        flash("Tu cuenta ya estaba verificada. Puedes iniciar sesión.")
        return redirect(url_for("auth.login"))

    user.is_verified = True
    db.session.commit()

    flash("Cuenta verificada correctamente. Ya puedes iniciar sesión.")
    return redirect(url_for("auth.login"))
