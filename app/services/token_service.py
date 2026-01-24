from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app


def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config["SECRET_KEY"]
    salt = current_app.config["SECURITY_PASSWORD_SALT"]
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)


def generate_verify_token(email: str) -> str:
    s = _serializer()
    return s.dumps({"email": email})


def confirm_verify_token(token: str, max_age_seconds: int = 3600) -> str | None:
    s = _serializer()
    try:
        data = s.loads(token, max_age=max_age_seconds)
        return data.get("email")
    except (SignatureExpired, BadSignature):
        return None
