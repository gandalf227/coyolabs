import json

from app.extensions import db
from app.models.logbook import LogbookEvent


def log_event(*, module: str, action: str, user_id: int | None = None, entity_label: str | None = None,
              description: str | None = None, metadata: dict | None = None, material_id: int | None = None) -> None:
    evt = LogbookEvent(
        user_id=user_id,
        material_id=material_id,
        action=action,
        module=(module or "").strip().upper() or None,
        entity_label=entity_label,
        description=description,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.session.add(evt)
