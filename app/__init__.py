#app init
from flask import Flask, app, redirect, request, url_for
from app.utils.roles import is_admin_role, is_staff_role

from app.models.user import User
from .config import Config
from .extensions import db, migrate, login_manager

from app.models.notification import Notification
from flask_login import current_user



def create_app():
    app = Flask(__name__)

    app.jinja_env.globals.update(is_admin_role=is_admin_role, is_staff_role=is_staff_role)

    from app.utils.text import smart_title, normalize_spaces

    app.jinja_env.filters["smart_title"] = smart_title
    app.jinja_env.filters["normalize_spaces"] = normalize_spaces


    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    # IMPORTAR MODELOS PARA QUE ALEMBIC LOS DETECTE
    from .models.user import User  # noqa: F401
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from . import models  # noqa: F401

    from app.controllers.home_controller import home_bp
    app.register_blueprint(home_bp)

    from app.controllers.dashboard_controller import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.controllers.notifications_controller import notifications_bp
    app.register_blueprint(notifications_bp)

    from .controllers.auth_controller import auth_bp
    app.register_blueprint(auth_bp)
    from app.controllers.profile_controller import profile_bp
    app.register_blueprint(profile_bp)

    from app.controllers.inventory_controller import inventory_bp
    app.register_blueprint(inventory_bp)
    from app.controllers.inventory_requests_controller import inventory_requests_bp
    app.register_blueprint(inventory_requests_bp)

    from app.controllers.api_controller import api_bp
    app.register_blueprint(api_bp)

    from app.controllers.debts_controller import debts_bp
    app.register_blueprint(debts_bp)

    from app.controllers.reservations_controller import reservations_bp
    app.register_blueprint(reservations_bp)

    from app.controllers.lostfound_controller import lostfound_bp
    app.register_blueprint(lostfound_bp)

    from app.controllers.software_controller import software_bp
    app.register_blueprint(software_bp)

    from app.controllers.reports_controller import reports_bp
    app.register_blueprint(reports_bp)

    from app.controllers.ra_client_controller import ra_client_bp
    app.register_blueprint(ra_client_bp)

    from app.controllers.users_controller import users_bp
    app.register_blueprint(users_bp)

    from app.controllers.forum_controller import forum_bp
    app.register_blueprint(forum_bp)
    # Ruta de salud para verificar que el servidor está vivo
    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated:
            notifs = (
                Notification.query
                .filter_by(user_id=current_user.id)
                .order_by(Notification.created_at.desc())
                .limit(5)
                .all()
            )

            unread = sum(1 for n in notifs if not n.is_read)

            return dict(
                header_notifications=notifs,
                header_unread_notifications=unread
            )

        return dict(header_notifications=[], header_unread_notifications=0)

    @app.before_request
    def enforce_profile_completion():
        if not current_user.is_authenticated:
            return None

        if not getattr(current_user, "is_verified", False):
            return None

        if getattr(current_user, "profile_completed", False):
            return None

        endpoint = request.endpoint or ""
        allowed_endpoints = {
            "profile.complete_profile",
            "auth.logout",
            "static",
        }

        if endpoint in allowed_endpoints:
            return None

        return redirect(url_for("profile.complete_profile"))

    return app
