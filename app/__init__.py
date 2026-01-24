#app init
from flask import Flask, app

from app.models.user import User
from .config import Config
from .extensions import db, migrate, login_manager

def create_app():
    app = Flask(__name__)

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

    # Blueprints (por ahora solo auth)
    from .controllers.auth_controller import auth_bp
    app.register_blueprint(auth_bp)


    from app.controllers.inventory_controller import inventory_bp
    app.register_blueprint(inventory_bp)

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



    # Ruta de salud para verificar que el servidor está vivo
    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
