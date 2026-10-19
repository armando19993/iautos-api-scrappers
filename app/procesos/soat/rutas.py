from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.schemas import AsyncAcceptedResponse, RESP_400_PLACA, RESP_422, RESP_500
from app.procesos.soat import servicio
from app.procesos.soat.schemas import SoatRequest, SoatResponse

router = APIRouter()

@router.post(
    "/soat",
    tags=["SOAT"],
    summary="Consultar SOAT (síncrono)",
    response_description="Certificado SOAT vigente más reciente.",
    responses={
        200: {
            "model": SoatResponse,
            "description": "Consulta completada. Revise `success` para saber si hubo datos.",
            "content": {
                "application/json": {
                    "examples": {
                        "exito": {
                            "summary": "SOAT encontrado",
                            "value": {
                                "success": True,
                                "placa": "ABC123",
                                "soat": {
                                    "Placa": "ABC123",
                                    "Aseguradora": "LA POSITIVA SEGUROS",
                                    "Estado": "VIGENTE",
                                    "FechaInicio": "01/01/2025",
                                    "FechaFin": "01/01/2026",
                                },
                                "screenshot_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
                                "tiempo_segundos": 34.2,
                                "vehiculoId": 42,
                                "webhook": {"status": "ok"},
                            },
                        },
                        "sin_resultado": {
                            "summary": "No se obtuvo el SOAT",
                            "value": {
                                "success": False,
                                "placa": "ABC123",
                                "error": "Maximo de 10 intentos sin resultado exitoso",
                                "tiempo_segundos": 45.0,
                                "vehiculoId": 42,
                                "webhook": {"status": "ok"},
                            },
                        },
                    }
                }
            },
        },
        400: RESP_400_PLACA,
        422: RESP_422,
        500: RESP_500,
    },
)
def soat_sync(req: SoatRequest):
    """Modo síncrono: bloquea hasta tener el resultado del SOAT y lo retorna.
    También envía el resultado al webhook de IAUTOS.
    """
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    return servicio.consultar(placa, req.vehiculoId, req.use_proxy, req.headless)


def _soat_async_common(placa: str, vehiculoId: int, use_proxy: bool, headless: bool, bg: BackgroundTasks):
    placa = placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    bg.add_task(servicio._run_async_task, placa, vehiculoId, use_proxy, headless)
    return {"status": "accepted", "placa": placa, "vehiculoId": vehiculoId, "webhook": "se enviara al terminar"}


@router.post(
    "/soat/async",
    tags=["SOAT"],
    summary="Consultar SOAT (asíncrono)",
    response_description="Acuse de recibo. El resultado se envía al webhook al terminar.",
    responses={
        200: {"model": AsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
        422: RESP_422,
    },
)
def soat_async(req: SoatRequest, bg: BackgroundTasks):
    """Encola la consulta en segundo plano y responde de inmediato.
    Al finalizar, el resultado se envía al webhook de IAUTOS."""
    return _soat_async_common(req.placa, req.vehiculoId, req.use_proxy, req.headless, bg)


@router.get(
    "/soat/async",
    tags=["SOAT"],
    summary="Consultar SOAT (asíncrono, vía GET)",
    response_description="Acuse de recibo. El resultado se envía al webhook al terminar.",
    responses={
        200: {"model": AsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
    },
)
def soat_async_get(placa: str, vehiculoId: int, use_proxy: bool = False, headless: bool = True, bg: BackgroundTasks = BackgroundTasks()):
    return _soat_async_common(placa, vehiculoId, use_proxy, headless, bg)


@router.get(
    "/soat/{placa}",
    tags=["SOAT"],
    summary="Consultar SOAT (atajo GET)",
    response_description="Certificado SOAT vigente más reciente.",
    responses={
        200: {"model": SoatResponse, "description": "Consulta completada."},
        400: RESP_400_PLACA,
        500: RESP_500,
    },
)
def soat_sync_get(placa: str, vehiculoId: int, use_proxy: bool = False, headless: bool = True):
    """Atajo GET para probar rápido desde el navegador.
    Ej: `GET /soat/ABC123?vehiculoId=42`
    """
    return soat_sync(SoatRequest(placa=placa, vehiculoId=vehiculoId, use_proxy=use_proxy, headless=headless))
