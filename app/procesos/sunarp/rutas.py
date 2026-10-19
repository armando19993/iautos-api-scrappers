from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.core.schemas import ErrorDetail, RESP_400_PLACA, RESP_422, RESP_500
from app.procesos.sunarp import servicio
from app.procesos.sunarp.schemas import SunarpAsyncAcceptedResponse, SunarpRequest, SunarpResponse

router = APIRouter()

@router.post(
    "/sunarp",
    tags=["Sunarp"],
    summary="Consultar registro vehicular (síncrono)",
    response_description="Tarjeta de identificación vehicular + texto OCR.",
    responses={
        200: {
            "model": SunarpResponse,
            "description": "Consulta completada. Revise `success` para saber si hubo datos.",
            "content": {
                "application/json": {
                    "examples": {
                        "exito": {
                            "summary": "Vehículo encontrado",
                            "value": {
                                "success": True,
                                "placa": "ABC123",
                                "result_image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
                                "ocr_text": "PLACA: ABC123\nMARCA: TOYOTA\nMODELO: YARIS\nAÑO: 2020",
                                "raw_response": {"model": {"imagen": "..."}},
                                "tiempo_segundos": 3.1,
                                "operacion": "datos_vehiculo",
                                "empresaId": 3,
                                "vehiculo": {
                                    "Veh_NumeroPlaca": "ABC123",
                                    "Veh_NumeroVin": None,
                                    "Veh_NumeroMotor": "262496256",
                                    "Veh_Color": "ROJO",
                                    "Veh_Marca": "TOYOTA",
                                    "Veh_Modelo": "YARIS",
                                    "Veh_EstadoSunarp": "EN CIRCULACION",
                                    "Veh_Sede": "LIMA",
                                    "Veh_Propietario1": "GOMEZ GONZALES JOSEPH",
                                    "Veh_Propietario2": "SIN INFORMACION",
                                    "Veh_Propietario3": "SIN INFORMACION",
                                },
                            },
                        },
                        "sin_resultado": {
                            "summary": "No se obtuvo el registro",
                            "value": {
                                "success": False,
                                "placa": "ABC123",
                                "error": "HTTP 404: no se encontró el vehículo",
                                "tiempo_segundos": 2.4,
                                "operacion": None,
                                "empresaId": 3,
                                "vehiculo": None,
                            },
                        },
                        "insert_fallido": {
                            "summary": "Scraping OK pero el webhook de inserción falló",
                            "value": {
                                "success": False,
                                "placa": "ABC123",
                                "error": "No se pudo registrar el vehículo: timeout",
                                "ocr_text": "Nº PLACA: ABC123 ...",
                                "tiempo_segundos": 3.4,
                                "vehiculoId": None,
                                "webhook": {"webhook_error": "timeout"},
                            },
                        },
                    }
                }
            },
        },
        400: RESP_400_PLACA,
        422: RESP_422,
        500: RESP_500,
        503: {
            "model": ErrorDetail,
            "description": "Todos los clientes Sunarp están ocupados; reintente en unos segundos.",
            "content": {"application/json": {"example": {"detail": "Servicio Sunarp saturado: sin cliente disponible, reintente en unos segundos"}}},
        },
    },
)
def sunarp_sync(req: SunarpRequest):
    """Consulta vehicular en Sunarp (~3s) y devuelve los datos extraídos (`operacion: datos_vehiculo`,
    `empresaId`, `vehiculo`). Con `SUNARP_WEBHOOK_ENABLED=true` además registra el vehículo vía webhook
    y devuelve el `Veh_Id` en `vehiculoId`.
    Thread-safe: el pool (compartido con el modo async) asigna un cliente HTTP libre."""
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    try:
        return servicio.consultar_sincrono(placa, req.empresaId)
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Servicio Sunarp saturado: sin cliente disponible, reintente en unos segundos",
        )


@router.post(
    "/sunarp/async",
    tags=["Sunarp"],
    summary="Consultar registro vehicular (asíncrono)",
    response_description="Acuse de recibo. El resultado se procesa en segundo plano.",
    responses={
        200: {"model": SunarpAsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
        422: RESP_422,
    },
)
def sunarp_async(req: SunarpRequest, bg: BackgroundTasks):
    """Encola la consulta Sunarp en segundo plano y responde de inmediato (sin `vehiculoId`:
    lo genera el receptor del webhook al registrar el vehículo)."""
    return _sunarp_async_common(req.placa, req.empresaId, bg)


@router.get(
    "/sunarp/async",
    tags=["Sunarp"],
    summary="Consultar registro vehicular (asíncrono, vía GET)",
    response_description="Acuse de recibo. El resultado se procesa en segundo plano.",
    responses={
        200: {"model": SunarpAsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
        422: RESP_422,
    },
)
def sunarp_async_get(
    bg: BackgroundTasks,
    placa: str,
    empresaId: int = Query(..., ge=0, le=255),
):
    return _sunarp_async_common(placa, empresaId, bg)


def _sunarp_async_common(placa: str, empresaId: int, bg: BackgroundTasks):
    placa = placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    bg.add_task(servicio._run_sunarp_async_task, placa, empresaId)
    return {"status": "accepted", "placa": placa}


@router.get(
    "/sunarp/{placa}",
    tags=["Sunarp"],
    summary="Consultar registro vehicular (atajo GET)",
    response_description="Tarjeta de identificación vehicular + texto OCR.",
    responses={
        200: {"model": SunarpResponse, "description": "Consulta completada."},
        400: RESP_400_PLACA,
        422: RESP_422,
        500: RESP_500,
        503: {"model": ErrorDetail, "description": "Todos los clientes Sunarp están ocupados."},
    },
)
def sunarp_sync_get(
    placa: str,
    empresaId: int = Query(..., ge=0, le=255),
):
    """Atajo GET para probar rápido.
    Ej: `GET /sunarp/ABC123?empresaId=3`
    """
    return sunarp_sync(SunarpRequest(placa=placa, empresaId=empresaId))
