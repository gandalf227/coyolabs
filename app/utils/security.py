from functools import wraps
from flask import request, current_app, jsonify


def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("RA_API_KEY")
        provided = request.headers.get("X-API-Key")

        if not expected or not provided or provided != expected:
            return jsonify({"error": "Unauthorized"}), 401

        return fn(*args, **kwargs)

    return wrapper
