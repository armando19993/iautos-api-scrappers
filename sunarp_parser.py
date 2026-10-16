"""Parser del texto OCR de la tarjeta de identificacion vehicular de Sunarp.

Convierte ``ocr_text`` en los campos de la tabla ``vehiculo`` (prefijo ``Veh_``).
Tolera los dos layouts que puede producir Tesseract:
  - en linea:  ``Nº PLACA: AXY340`` (el prefijo "Nº" puede salir como "N*", "Ne", "N°"...)
  - en bloques: primero todas las etiquetas y luego todos los valores, en el mismo orden.
"""
import re

SIN_INFORMACION = "SIN INFORMACION"
MAX_PROPIETARIOS = 3

# Prefijo "Nº" tolerante ("N*", "Ne", "N°", "No"...): "N" + 1 caracter opcional.
# "PLACAVIGENTE" / "PLACA ANTERIOR" se reconocen antes que "PLACA".
_LABEL_RE = re.compile(
    r"^\s*(?:N[^\s:;]?\.?\s*)?"
    r"(PLACA\s*VIGENTE|PLACA\s*ANTERIOR|PLACA|SERIE|VIN|MOTOR|COLOR|MARCA|MODELO|ESTADO"
    r"|ANOTACIONES|SEDE|A[ÑN]O\s*DE\s*MODELO)"
    r"(?=[\s:;.]|$)\s*[:;.]?\s*(.*?)\s*$",
    re.IGNORECASE,
)
_OWNERS_RE = re.compile(r"^\s*PROPIETARIO\s*(?:\(\s*S\s*\))?\s*[:;.]?\s*(.*?)\s*$", re.IGNORECASE)
_DATE_RE = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}")

# etiqueta del OCR -> (columna de vehiculo, longitud maxima). Las demas etiquetas
# (SERIE, PLACA*, ANOTACIONES, AÑO DE MODELO) se reconocen pero se descartan.
_COLUMNS = {
    "VIN": ("Veh_NumeroVin", 100),
    "MOTOR": ("Veh_NumeroMotor", 100),
    "COLOR": ("Veh_Color", 100),
    "MARCA": ("Veh_Marca", 100),
    "MODELO": ("Veh_Modelo", 100),
    "ESTADO": ("Veh_EstadoSunarp", 100),
    "SEDE": ("Veh_Sede", 100),
}
_DATA_FIELDS = tuple(col for col, _ in _COLUMNS.values())


def _clean(text: str, max_len: int) -> str | None:
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text[:max_len] if text else None


def _clean_owner(text: str) -> str | None:
    return _clean(text.replace(",", " "), 255)


def parse_ocr_text(ocr_text: str, empresa_id: int, placa: str) -> dict:
    """Devuelve el dict ``vehiculo`` listo para el webhook de insercion.

    ``Veh_NumeroPlaca`` es siempre la placa consultada (es la clave del upsert),
    no la leida por OCR. Los campos vacios o ausentes quedan en ``None``.
    """
    placa = placa.strip().upper()
    lines = [ln.strip() for ln in (ocr_text or "").splitlines()]

    labels = []  # (etiqueta, valor_en_linea) en orden de aparicion
    loose = []   # lineas sin etiqueta antes de PROPIETARIO(S) (layout en bloques)
    owners = []
    owners_idx = None
    for i, line in enumerate(lines):
        if not line:
            continue
        m_own = _OWNERS_RE.match(line)
        if m_own:
            owners_idx = i
            if m_own.group(1):
                owners.append(m_own.group(1))
            break
        m = _LABEL_RE.match(line)
        if m:
            labels.append((re.sub(r"\s+", "", m.group(1)).upper(), m.group(2)))
        elif not line.upper().startswith("DATOS DEL"):
            loose.append(line)

    # Layout en bloques: ninguna etiqueta trae valor en su linea y hay tantos valores como etiquetas.
    if labels and not any(v for _, v in labels) and len(loose) == len(labels):
        labels = [(lab, val) for (lab, _), val in zip(labels, loose)]

    vehiculo = {"Veh_EmpId": empresa_id, "Veh_NumeroPlaca": placa}
    vehiculo.update({col: None for col in _DATA_FIELDS})
    for label, value in labels:
        spec = _COLUMNS.get(label)
        if spec and vehiculo[spec[0]] is None:
            vehiculo[spec[0]] = _clean(value, spec[1])

    if owners_idx is not None:
        for line in lines[owners_idx + 1:]:
            if _DATE_RE.search(line):
                break
            if not line:
                if owners:
                    break  # linea vacia tras los propietarios: fin de la seccion
                continue
            owner = _clean_owner(line)
            if owner and len(owner) >= 2:
                owners.append(line)
    names = [n for n in (_clean_owner(o) for o in owners) if n]
    if len(names) > MAX_PROPIETARIOS:
        print(f"[SunarpParser] placa={placa}: {len(names)} propietarios, se ignoran los extras: "
              f"{names[MAX_PROPIETARIOS:]}")
    names = names[:MAX_PROPIETARIOS]
    names += [SIN_INFORMACION] * (MAX_PROPIETARIOS - len(names))
    for n, name in enumerate(names, start=1):
        vehiculo[f"Veh_Propietario{n}"] = name

    return vehiculo


def tiene_datos(vehiculo: dict) -> bool:
    """False si el OCR no aporto ningun dato del vehiculo (p. ej. pagina de captcha)."""
    return any(vehiculo.get(f) for f in _DATA_FIELDS)


def puntaje(vehiculo: dict) -> int:
    """Cuantos datos utiles se leyeron (campos del vehiculo + propietarios). Sirve para
    elegir entre varias lecturas OCR del mismo documento."""
    n = sum(1 for f in _DATA_FIELDS if vehiculo.get(f))
    n += sum(1 for i in range(1, MAX_PROPIETARIOS + 1)
             if vehiculo.get(f"Veh_Propietario{i}") not in (None, SIN_INFORMACION))
    return n
