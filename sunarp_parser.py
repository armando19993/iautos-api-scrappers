"""Parser del texto OCR de la tarjeta de identificacion vehicular de Sunarp.

Convierte ``ocr_text`` en los campos de la tabla ``vehiculo`` (prefijo ``Veh_``).
Tolera los dos layouts que puede producir Tesseract:
  - en linea:  ``Nº PLACA: AXY340``
  - en bloques: primero todas las etiquetas y luego todos los valores, en el mismo orden.
"""
import re

SIN_INFORMACION = "SIN INFORMACION"
MAX_PROPIETARIOS = 3

_LABEL_RE = re.compile(
    r"^\s*(?:N[O0º°]?\.?\s*)?"
    r"(PLACA VIGENTE|PLACA ANTERIOR|PLACA|SERIE|VIN|MOTOR|COLOR|MARCA|MODELO|ESTADO"
    r"|ANOTACIONES|SEDE|A[ÑN]O DE MODELO)"
    r"\s*[:;.]?\s*(.*?)\s*$"
)
_OWNERS_RE = re.compile(r"^\s*PROPIETARIO\s*(?:\(\s*S\s*\))?\s*[:;.]?\s*(.*?)\s*$")
_DATE_RE = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}")

# etiqueta del OCR -> (columna de vehiculo, longitud maxima)
_COLUMNS = {
    "SERIE": None,  # se descarta: Veh_NumeroVin sale de VIN
    "VIN": ("Veh_NumeroVin", 100),
    "MOTOR": ("Veh_NumeroMotor", 100),
    "COLOR": ("Veh_Color", 100),
    "MARCA": ("Veh_Marca", 100),
    "MODELO": ("Veh_Modelo", 100),
    "ESTADO": ("Veh_EstadoSunarp", 100),
    "SEDE": ("Veh_Sede", 100),
}
_DATA_FIELDS = ("Veh_NumeroVin", "Veh_NumeroMotor", "Veh_Color", "Veh_Marca",
                "Veh_Modelo", "Veh_EstadoSunarp", "Veh_Sede")


def _clean(text: str, max_len: int) -> str | None:
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text[:max_len] if text else None


def _clean_owner(text: str) -> str | None:
    return _clean(text.replace(",", " "), 255)


def parse_ocr_text(ocr_text: str, empresa_id: int, placa: str) -> dict:
    """Devuelve el dict ``vehiculo`` listo para el webhook de insercion.

    ``Veh_NumeroPlaca`` es siempre la placa consultada (es la clave del upsert),
    no la leida por OCR. Los campos que no se encuentren quedan en ``None``.
    """
    placa = placa.strip().upper()
    lines = [ln.strip() for ln in (ocr_text or "").splitlines()]

    labels = []  # (etiqueta, valor_en_linea) en orden de aparicion
    loose = []   # lineas sin etiqueta antes de PROPIETARIO(S) (layout en bloques)
    owners = []
    owners_idx = None
    for i, raw in enumerate(lines):
        line = raw.upper()
        if not line:
            continue
        m_own = _OWNERS_RE.match(line)
        if m_own:
            owners_idx = i
            if m_own.group(1):
                owners.append(raw[len(raw) - len(m_own.group(1)):])
            break
        m = _LABEL_RE.match(line)
        if m:
            value = raw[len(raw) - len(m.group(2)):] if m.group(2) else ""
            labels.append((m.group(1), value))
        elif not line.startswith("DATOS DEL"):
            loose.append(raw)

    if labels and not any(v for _, v in labels) and len(loose) == len(labels):
        labels = [(lab, val) for (lab, _), val in zip(labels, loose)]

    vehiculo = {"Veh_EmpId": empresa_id, "Veh_NumeroPlaca": placa}
    vehiculo.update({col: None for col, _ in filter(None, _COLUMNS.values())})
    for label, value in labels:
        spec = _COLUMNS.get(label)
        if spec and vehiculo[spec[0]] is None:
            vehiculo[spec[0]] = _clean(value, spec[1])

    if owners_idx is not None:
        for raw in lines[owners_idx + 1:]:
            if _DATE_RE.search(raw):
                break
            owner = _clean_owner(raw)
            if owner and len(owner) >= 2:
                owners.append(raw)
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
