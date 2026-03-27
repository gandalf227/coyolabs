import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ENV = (os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")) or "development").strip().lower()

    SECRET_KEY = (os.getenv("SECRET_KEY") or "dev-secret").strip()
    SECURITY_PASSWORD_SALT = (os.getenv("SECURITY_PASSWORD_SALT") or "dev-salt").strip()

    DB_USER = (os.getenv("DB_USER") or "postgres").strip()
    DB_PASSWORD = (os.getenv("DB_PASSWORD") or "raspi").strip()
    DB_HOST = (os.getenv("DB_HOST") or "localhost").strip()
    DB_PORT = (os.getenv("DB_PORT") or "5432").strip()
    DB_NAME = (os.getenv("DB_NAME") or "lab_system").strip()

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Email (SMTP Gmail)
    MAIL_SERVER = (os.getenv("MAIL_SERVER") or "smtp.gmail.com").strip()
    MAIL_PORT = int((os.getenv("MAIL_PORT") or "587").strip())
    MAIL_USE_TLS = (os.getenv("MAIL_USE_TLS") or "true").strip().lower() == "true"
    MAIL_USE_SSL = (os.getenv("MAIL_USE_SSL") or "false").strip().lower() == "true"
    MAIL_USERNAME = (os.getenv("MAIL_USERNAME") or "").strip()
    MAIL_PASSWORD = (os.getenv("MAIL_PASSWORD") or "").strip()
    MAIL_DEFAULT_SENDER = (os.getenv("MAIL_DEFAULT_SENDER") or MAIL_USERNAME).strip()

    APP_BASE_URL = (
        os.getenv("APP_BASE_URL") or "https://pillowless-ernest-adamantly.ngrok-free.dev"
    ).strip().rstrip("/")

    RA_API_KEY = (os.getenv("RA_API_KEY") or "dev-ra-key-cambia-esto").strip()

    _INSECURE_DEFAULTS = {
        "SECRET_KEY": "dev-secret",
        "SECURITY_PASSWORD_SALT": "dev-salt",
        "RA_API_KEY": "dev-ra-key-cambia-esto",
    }

    if ENV not in {"development", "dev", "local", "test", "testing"}:
        for _name, _default in _INSECURE_DEFAULTS.items():
            if (os.getenv(_name) or _default).strip() == _default:
                raise RuntimeError(
                    f"Configuración insegura: {_name} usa valor por defecto en entorno '{ENV}'."
                )