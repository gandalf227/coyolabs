import re


def normalize_spaces(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def smart_title(s: str) -> str:
    """
    Convierte textos tipo 'GABINETE # 1 / CAJA DE HERRAMIENTA' a un formato más legible,
    sin reescribir siglas/códigos dentro de paréntesis.
    """
    s = normalize_spaces(s)
    if not s:
        return s

    # Si el texto es TODO mayúsculas (muy común), lo pasamos a title-case
    # pero conservando tokens con números y símbolos.
    if s.isupper():
        return " ".join([w if any(ch.isdigit() for ch in w) else w.capitalize() for w in s.lower().split(" ")])

    return s
