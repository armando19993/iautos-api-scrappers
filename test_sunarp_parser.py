"""Pruebas del parser OCR de Sunarp. Uso: python test_sunarp_parser.py"""
from app.procesos.sunarp.parser import parse_ocr_text, tiene_datos

INLINE = """DATOS DEL VEHÍCULO
Nº PLACA: AXY340
Nº SERIE: TSMYD21S5JM358712
Nº VIN: TSMYD21S5JM358712
Nº MOTOR: M16A2148853
COLOR: TURQUESA NEGRO
MARCA: SUZUKI
MODELO: VITARA
PLACA VIGENTE: AXY340
PLACA ANTERIOR: NINGUNA
ESTADO: EN CIRCULACION
ANOTACIONES: NINGUNA
SEDE: LIMA
AÑO DE MODELO: 2018

PROPIETARIO(S):
CONDORI MOLLEHUARA, MIGUEL
MENDOZA MEJIA, LOURDES REGINA

15/10/2026 19:49:44"""

BLOCKS = """DATOS DEL VEHÍCULO
Nº PLACA:
Nº SERIE:
Nº VIN:
Nº MOTOR:
COLOR:
MARCA:
MODELO:
PLACA VIGENTE:
PLACA ANTERIOR:
ESTADO:
ANOTACIONES:
SEDE:
AÑO DE MODELO:
AXY340
TSMYD21S5JM358712
TSMYD21S5JM358712
M16A2148853
TURQUESA NEGRO
SUZUKI
VITARA
AXY340
NINGUNA
EN CIRCULACION
NINGUNA
LIMA
2018
PROPIETARIO(S):
CONDORI MOLLEHUARA, MIGUEL
MENDOZA MEJIA, LOURDES REGINA
15/10/2026 19:49:44"""

ESPERADO = {
    "Veh_EmpId": 3, "Veh_NumeroPlaca": "AXY340", "Veh_NumeroVin": "TSMYD21S5JM358712",
    "Veh_NumeroMotor": "M16A2148853", "Veh_Color": "TURQUESA NEGRO", "Veh_Marca": "SUZUKI",
    "Veh_Modelo": "VITARA", "Veh_EstadoSunarp": "EN CIRCULACION", "Veh_Sede": "LIMA",
    "Veh_Propietario1": "CONDORI MOLLEHUARA MIGUEL",
    "Veh_Propietario2": "MENDOZA MEJIA LOURDES REGINA",
    "Veh_Propietario3": "SIN INFORMACION",
}


def check(name, text, expected):
    got = parse_ocr_text(text, 3, "axy340")
    assert got == expected, f"{name}:\n got={got}\n exp={expected}"
    print("ok", name)


check("inline", INLINE, ESPERADO)
check("bloques", BLOCKS, ESPERADO)

uno = INLINE.replace("MENDOZA MEJIA, LOURDES REGINA\n", "")
check("1 propietario", uno, {**ESPERADO, "Veh_Propietario2": "SIN INFORMACION"})

cinco = INLINE.replace("MENDOZA MEJIA, LOURDES REGINA\n",
                       "MENDOZA MEJIA, LOURDES REGINA\nA B\nC D\nE F\n")
got = parse_ocr_text(cinco, 3, "AXY340")
assert got["Veh_Propietario3"] == "A B" and "Veh_Propietario4" not in got
print("ok >3 propietarios")

sin = parse_ocr_text("Captcha no resuelto\n\nPor favor resuelva el captcha antes de continuar", 3, "AXY340")
assert not tiene_datos(sin) and sin["Veh_Marca"] is None
print("ok sin datos")

# ── Fixture real de Tesseract (psm 6, spa) con nombres ficticios ──
REAL = """ee Consulta
sunarpl © Vehicular
DATOS DEL VEHÍCULO
N* PLACA: ABC123
N* SERIE: EL400016143
Ne VIN:
N* MOTOR: 262496256
COLOR: ROJO
MARCA: TOYOTA
MODELO: EL40-AEMDS COROLLA TERCEL
PLACAVIGENTE: ABC123
PLACA ANTERIOR: B05358
ESTADO: EN CIRCULACION
ANOTACIONES: — NINGUNA
SEDE: LIMA
AÑO DE MODELO:
PROPIETARIO(S):
GOMEZ GONZALES, JOSEPH
GOMEZ SICCHA, JOSEPH ALEJANDRO
SICCHA MACASSI, LUPE ELIZABETH
15/10/2026 22:52:32"""

ESPERADO_REAL = {
    "Veh_EmpId": 7, "Veh_NumeroPlaca": "ABC123", "Veh_NumeroVin": None,
    "Veh_NumeroMotor": "262496256", "Veh_Color": "ROJO", "Veh_Marca": "TOYOTA",
    "Veh_Modelo": "EL40-AEMDS COROLLA TERCEL", "Veh_EstadoSunarp": "EN CIRCULACION",
    "Veh_Sede": "LIMA",
    "Veh_Propietario1": "GOMEZ GONZALES JOSEPH",
    "Veh_Propietario2": "GOMEZ SICCHA JOSEPH ALEJANDRO",
    "Veh_Propietario3": "SICCHA MACASSI LUPE ELIZABETH",
}
got = parse_ocr_text(REAL, 7, "abc123")
assert got == ESPERADO_REAL, f"real:\n got={got}\n exp={ESPERADO_REAL}"
assert tiene_datos(got)
print("ok fixture real (VIN vacio -> None, fecha no es propietario)")

# placa vigente/anterior no pisan la placa; prefijos y minusculas tolerados
v = parse_ocr_text("n* placa: ZZZ999\nNe vin: abc\nn° Motor : m1\nplacavigente: QQQ111\nmarca: kia", 1, "AAA111")
assert v["Veh_NumeroPlaca"] == "AAA111" and v["Veh_NumeroVin"] == "ABC" and v["Veh_NumeroMotor"] == "M1" and v["Veh_Marca"] == "KIA"
print("ok etiquetas tolerantes")

# lineas vacias intercaladas entre propietarios (salida real de Tesseract psm 6 con preprocesado):
# los 3 propietarios deben leerse; la seccion termina en la fecha/hora
con_vacias = REAL
for linea in ("GOMEZ GONZALES", "GOMEZ SICCHA", "SICCHA MACASSI", "15/10/2026"):
    con_vacias = con_vacias.replace("\n" + linea, "\n\n" + linea)
got = parse_ocr_text(con_vacias, 7, "abc123")
assert got == ESPERADO_REAL, got
print("ok propietarios separados por lineas vacias")

# 2 propietarios con lineas vacias: el tercero queda SIN INFORMACION y la fecha no cuenta
v = parse_ocr_text("MARCA: X\nPROPIETARIO(S):\n\nA B, C\n\nD E, F\n\n16/10/2026 11:02:32", 1, "AAA111")
assert (v["Veh_Propietario1"], v["Veh_Propietario2"], v["Veh_Propietario3"]) == ("A B C", "D E F", "SIN INFORMACION")
print("ok 2 propietarios con lineas vacias")
