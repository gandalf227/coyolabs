import json
from flask import Blueprint, jsonify, request, abort
from flask_login import current_user


from app.extensions import db
from app.models.material import Material
from app.models.logbook import LogbookEvent
from app.utils.security import api_key_required

from app.models.user import User
from app.services.debt_service import user_has_open_debts
from app.utils.authz import min_role_required 





api_bp = Blueprint("api", __name__, url_prefix="/api")


def material_to_dict(m: Material) -> dict:
    return {
        "id": m.id,
        "lab": m.lab.name if m.lab else None,
        "lab_id": m.lab_id,
        "name": m.name,
        "location": m.location,
        "status": m.status,
        "pieces_text": m.pieces_text,
        "pieces_qty": m.pieces_qty,
        "brand": m.brand,
        "model": m.model,
        "code": m.code,
        "serial": m.serial,
        "image_ref": m.image_ref,
        "tutorial_url": m.tutorial_url,
        "notes": m.notes,
    }


@api_bp.route("/materials/<int:material_id>", methods=["GET"])
@api_key_required
def get_material(material_id: int):
    m = Material.query.get(material_id)
    if not m:
        return jsonify({"error": "Material no encontrado"}), 404
    return jsonify(material_to_dict(m)), 200


@api_bp.route("/materials", methods=["GET"])
@api_key_required
def search_materials():
    lab_id = request.args.get("lab_id", type=int)
    q = (request.args.get("q") or "").strip()

    query = Material.query
    if lab_id:
        query = query.filter(Material.lab_id == lab_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Material.name.ilike(like)) |
            (Material.location.ilike(like)) |
            (Material.code.ilike(like)) |
            (Material.serial.ilike(like))
        )

    # límite para no devolver miles de filas
    materials = query.order_by(Material.id.desc()).limit(200).all()
    return jsonify([material_to_dict(m) for m in materials]), 200


@api_bp.route("/ra/events", methods=["POST"])
@api_key_required
def ra_event():
    """
    Body JSON esperado:
    {
      "material_id": 123,        # opcional
      "event_type": "scan|view|open",
      "metadata": { ... }        # opcional
    }
    """
    data = request.get_json(silent=True) or {}
    material_id = data.get("material_id")
    event_type = (data.get("event_type") or "").strip().lower()
    metadata = data.get("metadata")


    user_email = (data.get("user_email") or "").strip().lower()

    if not user_email:
        return jsonify({"error": "user_email es requerido para eventos RA"}), 400

    user = User.query.filter_by(email=user_email).first()
    if not user:
        return jsonify({"error": "usuario no existe"}), 404

    if user_has_open_debts(user.id):
        return jsonify({"error": "usuario con adeudo activo, RA bloqueada"}), 403




    if event_type not in {"scan", "view", "open"}:
        return jsonify({"error": "event_type inválido. Usa: scan, view, open"}), 400

    # Validar material si viene
    if material_id is not None:
        m = Material.query.get(material_id)
        if not m:
            return jsonify({"error": "material_id no existe"}), 400

    evt = LogbookEvent(
        user_id=user.id,
        material_id=material_id,
        action=f"RA_{event_type.upper()}",
        description="Evento generado desde RA",
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
    )

    db.session.add(evt)
    db.session.commit()

    return jsonify({"ok": True, "event_id": evt.id}), 201

@api_bp.route("/ra/materials/<int:material_id>", methods=["GET"])
@api_key_required
def ra_get_material(material_id: int):
    m = Material.query.get(material_id)
    if not m:
        return jsonify({"error": "Material no encontrado"}), 404
    return jsonify(material_to_dict(m)), 200

