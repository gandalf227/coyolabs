import re

ROLE_LABELS = {
    "ADMIN": "Administrador",
    "STAFF": "Administrativo",
    "STUDENT": "Estudiante",
    "TEACHER": "Profesor",
    "SUPERADMIN": "Administrador",
    "PENDING": "Pendiente",
}

STATUS_LABELS = {
    "APPROVED": "Aprobado",
    "PENDING": "Pendiente",
    "REJECTED": "Rechazado",
    "OPEN": "Abierto",
    "CLOSED": "Cerrado",
    "IN_PROGRESS": "En curso",
    "COMPLETED": "Completado",
    "CLOSED_WITH_DEBT": "Cerrado con adeudo",
    "READY": "Listo para recoger",
    "READY_FOR_PICKUP": "Listo para recoger",
    "CLOSURE_REQUESTED": "Cierre solicitado",
    "REPORTED": "Reportado",
    "IN_STORAGE": "En resguardo",
    "RETURNED": "Devuelto",
    "PAID": "Pagado",
    "CANCELLED": "Cancelado",
    "CANCELED": "Cancelado",
}

FLASH_CATEGORY_LABELS = {
    "success": "Operación realizada correctamente",
    "error": "Ocurrió un error",
    "danger": "Ocurrió un error",
    "invalid": "Datos inválidos",
    "warning": "Atención",
    "warn": "Atención",
    "info": "Información",
}


def normalize_spaces(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def smart_title(s: str) -> str:
    s = normalize_spaces(s)
    if not s:
        return s

    if s.isupper():
        return " ".join([w if any(ch.isdigit() for ch in w) else w.capitalize() for w in s.lower().split(" ")])

    return s


def role_label(role: str | None) -> str:
    normalized = normalize_spaces(role or "").upper()
    return ROLE_LABELS.get(normalized, role or "")


def status_label(status: str | None) -> str:
    normalized = normalize_spaces(status or "").upper()
    return STATUS_LABELS.get(normalized, status or "")


def flash_category_label(category: str | None) -> str:
    normalized = normalize_spaces(category or "info").lower()
    return FLASH_CATEGORY_LABELS.get(normalized, "Información")
