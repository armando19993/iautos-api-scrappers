import threading
from typing import Optional

from app.compartido.webhook import send_sunarp_webhook
from app.core.config import SUNARP_SYNC_WAIT_SECONDS, SUNARP_WEBHOOK_ENABLED, WEBHOOK_SUNARP_INSERT_RETRIES
from app.procesos.sunarp.parser import parse_ocr_text, tiene_datos
from app.procesos.sunarp.pool import _get_sunarp_pool


def consultar_sincrono(placa: str, empresaId: int) -> dict:
    """Flujo de POST /sunarp. Con SUNARP_WEBHOOK_ENABLED registra el vehiculo y devuelve su Veh_Id;
    si no, solo devuelve los datos. Lanza TimeoutError si no hay cliente libre a tiempo."""
    if SUNARP_WEBHOOK_ENABLED:
        return _procesar_sunarp(placa, empresaId, SUNARP_SYNC_WAIT_SECONDS)
    return _consultar_sunarp_datos(placa, empresaId, SUNARP_SYNC_WAIT_SECONDS)

_VEHICULO_CAMPOS = (
    "Veh_NumeroPlaca", "Veh_NumeroVin", "Veh_NumeroMotor", "Veh_Color", "Veh_Marca", "Veh_Modelo",
    "Veh_EstadoSunarp", "Veh_Sede", "Veh_Propietario1", "Veh_Propietario2", "Veh_Propietario3",
)


def _consultar_sunarp_datos(placa: str, empresaId: int, acquire_timeout: Optional[float]) -> dict:
    """Flujo sincrono con el webhook apagado: scraping/OCR + parseo, SIN llamar al webhook ni
    devolver `vehiculoId`. Lanza TimeoutError si no hay cliente libre dentro de `acquire_timeout`."""
    result = _get_sunarp_pool().consultar(placa, timeout=acquire_timeout)
    if not result.get("placa"):
        result["placa"] = placa
    result["empresaId"] = empresaId
    result["operacion"] = None
    result["vehiculo"] = None

    def _fail(msg: str):
        result["success"] = False
        result["error"] = msg
        return result

    if not result.get("success"):
        return result
    ocr_error = result.pop("ocr_error", None)
    if ocr_error:
        return _fail(ocr_error)  # Tesseract no instalado
    ocr_text = result.get("ocr_text") or ""
    if not ocr_text.strip():
        return _fail("OCR vacío: no se pudo leer la tarjeta vehicular")
    parsed = parse_ocr_text(ocr_text, empresaId, placa)
    if not tiene_datos(parsed):
        return _fail("Texto OCR sin datos de vehículo")
    if not (parsed["Veh_NumeroPlaca"] and parsed["Veh_Marca"] and parsed["Veh_Modelo"]):
        return _fail("Datos de vehículo incompletos: falta marca o modelo")
    result["operacion"] = "datos_vehiculo"
    result["vehiculo"] = {k: parsed[k] for k in _VEHICULO_CAMPOS}
    return result


def _procesar_sunarp(placa: str, empresaId: int, acquire_timeout: Optional[float]) -> dict:
    """Flujo completo Sunarp: scraping/OCR, parseo,
    INSERT por webhook y `vehiculoId` = Veh_Id. Lanza TimeoutError si no hay cliente libre
    dentro de `acquire_timeout` (None = esperar)."""
    result = _get_sunarp_pool().consultar(placa, timeout=acquire_timeout)
    if not result.get("placa"):
        result["placa"] = placa
    result["vehiculoId"] = None
    if not result.get("success"):
        return result

    def _fail(msg: str):
        result["success"] = False
        result["error"] = msg
        return result

    ocr_error = result.pop("ocr_error", None)
    if ocr_error:
        return _fail(ocr_error)  # Tesseract no instalado
    ocr_text = result.get("ocr_text") or ""
    if not ocr_text.strip():
        return _fail("OCR vacío: no se pudo leer la tarjeta vehicular")
    vehiculo = parse_ocr_text(ocr_text, empresaId, placa)
    if not tiene_datos(vehiculo):
        return _fail("Texto OCR sin datos de vehículo")

    ins = send_sunarp_webhook(
        {"operacion": "insertar_vehiculo", "empresaId": empresaId, "vehiculo": vehiculo},
        retries=WEBHOOK_SUNARP_INSERT_RETRIES,
    )
    result["webhook"] = ins
    veh_id = ins.get("vehiculoId")
    if ins.get("success") is True and isinstance(veh_id, int) and not isinstance(veh_id, bool) and veh_id > 0:
        result["vehiculoId"] = veh_id
        print(f"[sunarp] placa={placa} vehiculoId={veh_id} accion={ins.get('accion')}")
        return result
    motivo = ins.get("error") or ins.get("webhook_error") or "respuesta inválida del webhook (success/vehiculoId)"
    print(f"[sunarp] ERROR insert placa={placa}: {ins}")
    return _fail(f"No se pudo registrar el vehículo: {motivo}")


def _run_sunarp_async_task(placa: str, empresaId: int):
    """Corre el flujo Sunarp en un hilo; si el pool esta lleno el job espera su turno."""
    def _work():
        try:
            result = _procesar_sunarp(placa, empresaId, None)
        except Exception as e:
            result = {"placa": placa, "success": False, "error": str(e), "vehiculoId": None}
        print(f"[sunarp_async] placa={placa} vehiculoId={result.get('vehiculoId')} "
              f"success={result.get('success')} error={result.get('error')}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()
