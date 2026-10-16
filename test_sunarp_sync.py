"""Pruebas del flujo SINCRONO de Sunarp (pool simulado, sin red). Uso: python test_sunarp_sync.py"""
import httpx
from fastapi.testclient import TestClient

import api
import webhook
from test_sunarp_parser import REAL

LLAMADAS_HTTP = []


def _prohibido(*a, **k):
    LLAMADAS_HTTP.append(a)
    raise AssertionError("no debe haber llamadas HTTP al webhook")


class FakePool:
    def __init__(self, result):
        self.result = result

    def consultar(self, placa, timeout=30):
        return dict(self.result, placa=placa)


def ok_result(**extra):
    return {"success": True, "ocr_text": REAL, "result_image_base64": "data:image/png;base64,AAA",
            "raw_response": {"x": 1}, "tiempo_segundos": 3.4, **extra}


def get(c, pool, placa="ABC123"):
    api._get_sunarp_pool = lambda: pool
    return c.get(f"/sunarp/{placa}", params={"empresaId": 3}).json()


c = TestClient(api.app)
api.SUNARP_WEBHOOK_ENABLED = False
api.send_sunarp_webhook = _prohibido
httpx.Client = _prohibido  # cualquier cliente HTTP nuevo falla el test

# 1. exito con el fixture ABC123, webhook apagado
r = get(c, FakePool(ok_result()))
assert r["success"] is True and r["operacion"] == "datos_vehiculo" and r["empresaId"] == 3
assert r["vehiculo"] == {
    "Veh_NumeroPlaca": "ABC123", "Veh_NumeroVin": None, "Veh_NumeroMotor": "262496256",
    "Veh_Color": "ROJO", "Veh_Marca": "TOYOTA", "Veh_Modelo": "EL40-AEMDS COROLLA TERCEL",
    "Veh_EstadoSunarp": "EN CIRCULACION", "Veh_Sede": "LIMA",
    "Veh_Propietario1": "GOMEZ GONZALES JOSEPH", "Veh_Propietario2": "GOMEZ SICCHA JOSEPH ALEJANDRO",
    "Veh_Propietario3": "SICCHA MACASSI LUPE ELIZABETH",
}, r["vehiculo"]
assert "Veh_EmpId" not in r["vehiculo"] and "vehiculoId" not in r and "webhook" not in r
for k in ("placa", "result_image_base64", "ocr_text", "raw_response", "tiempo_segundos"):
    assert r.get(k), k
assert LLAMADAS_HTTP == []
print("ok sync exito, webhook apagado, sin llamadas HTTP")

# 1b. POST /sunarp y WEBHOOK_SUNARP_URL vacia: no hace falta configurarla
webhook.WEBHOOK_SUNARP_URL = ""
api._get_sunarp_pool = lambda: FakePool(ok_result())
r = c.post("/sunarp", json={"placa": "abc123", "empresaId": 3, "platemId": 9}).json()
assert r["success"] is True and r["vehiculo"]["Veh_NumeroPlaca"] == "ABC123" and "vehiculoId" not in r
print("ok POST /sunarp sin WEBHOOK_SUNARP_URL")

# 2. fallos: success false, imagen y raw_response conservados, operacion/vehiculo null
casos = {
    "OCR vacío": ok_result(ocr_text=""),
    "Texto OCR sin datos de vehículo": ok_result(ocr_text="Captcha no resuelto"),
    "Tesseract no instalado": ok_result(ocr_text="", ocr_error="Tesseract no instalado o no encontrado"),
    "Datos de vehículo incompletos": ok_result(ocr_text="N* MOTOR: 1\nMARCA: TOYOTA\nCOLOR: ROJO"),
}
for esperado, res in casos.items():
    r = get(c, FakePool(res))
    assert r["success"] is False and esperado in r["error"], (esperado, r.get("error"))
    assert r["operacion"] is None and r["vehiculo"] is None and r["empresaId"] == 3
    assert r["result_image_base64"] and r["raw_response"] == {"x": 1}
    assert "vehiculoId" not in r
    print("ok fallo:", esperado)

r = get(c, FakePool({"success": False, "error": "HTTP 404"}))
assert r["success"] is False and r["operacion"] is None and r["vehiculo"] is None and r["error"] == "HTTP 404"
print("ok fallo del scraping")
assert LLAMADAS_HTTP == []

# 3. con el flag en true se comporta como antes (INSERT + vehiculoId)
enviados = []
api.SUNARP_WEBHOOK_ENABLED = True
api.send_sunarp_webhook = lambda payload, retries=0: (enviados.append(payload) or {"success": True, "vehiculoId": 39958})
r = get(c, FakePool(ok_result()))
assert r["success"] is True and r["vehiculoId"] == 39958 and "operacion" not in r
assert enviados[0]["operacion"] == "insertar_vehiculo" and enviados[0]["vehiculo"]["Veh_EmpId"] == 3
print("ok flag true: INSERT + vehiculoId")

# 4. async no cambia: con el flag apagado igual intenta el webhook y, sin URL, solo falla y lo registra
api.SUNARP_WEBHOOK_ENABLED = False
api.send_sunarp_webhook = webhook.send_sunarp_webhook  # real, sin URL -> {"webhook_error": ...}
api._get_sunarp_pool = lambda: FakePool(ok_result())
r = api._procesar_sunarp("ABC123", 3, None)
assert r["success"] is False and "WEBHOOK_SUNARP_URL no configurada" in r["error"] and r["vehiculoId"] is None
assert r["ocr_text"] and r["result_image_base64"]
print("ok async (sin cambios): intenta el webhook, registra el error")
