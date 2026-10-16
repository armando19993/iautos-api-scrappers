"""Pruebas del parser OCR de Sunarp. Uso: python test_sunarp_parser.py"""
from sunarp_parser import parse_ocr_text, tiene_datos

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
