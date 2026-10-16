from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.schemas import AsyncAcceptedResponse, RESP_400_PLACA, RESP_422, RESP_500
from app.procesos.mtc import servicio
from app.procesos.mtc.schemas import MtcRequest, MtcResponse

router = APIRouter()

@router.post(
    "/mtc",
    tags=["MTC"],
    summary="Consultar CITV (síncrono)",
    response_description="Certificado de revisión técnica (CITV) más reciente.",
    responses={
        200: {
            "model": MtcResponse,
            "description": "Consulta completada. Revise `success` para saber si hubo datos.",
            "content": {
                "application/json": {
                    "examples": {
                        "exito": {
                            "summary": "CITV encontrado",
                            "value": {
                                "success": True,
                                "placa": "ABC123",
                                "fuente": "MTC_CITV",
                                "ultimo_documento": {
                                    "empresa_certificadora": "REVISIONES TECNICAS DEL PERU S.A.",
                                    "direccion": "AV. EJEMPLO 123, LIMA",
                                    "placa": "ABC123",
                                    "nro_certificado": "12345-2025",
                                    "tipo_documento": "CITV",
                                    "vigente_desde": "01/01/2025",
                                    "vigente_hasta": "01/01/2026",
                                    "resultado_inspeccion": "APROBADO",
                                    "estado": "VIGENTE",
                                    "ambito": "NACIONAL",
                                    "tipo_servicio": "PARTICULAR",
                                    "observaciones": "",
                                },
                                "documentos_completos": [],
                                "screenshot_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
                                "tiempo_segundos": 12.3,
                                "vehiculoId": 42,
                                "webhook": {"status": "ok"},
                            },
                        },
                        "sin_resultado": {
                            "summary": "No se encontró CITV",
                            "value": {
                                "success": False,
                                "placa": "ABC123",
                                "error": "No se encontraron certificados",
                                "screenshot_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
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
def mtc_sync(req: MtcRequest):
    """Consulta CITV en MTC. Usa navegador headless + CapSolver.
    Retorna el certificado y una captura de pantalla del resultado."""
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    return servicio.consultar(placa, req.vehiculoId, req.use_proxy)


@router.post(
    "/mtc/async",
    tags=["MTC"],
    summary="Consultar CITV (asíncrono)",
    response_description="Acuse de recibo. El resultado se envía al webhook al terminar.",
    responses={
        200: {"model": AsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
        422: RESP_422,
    },
)
def mtc_async(req: MtcRequest, bg: BackgroundTasks):
    """Encola la consulta CITV en segundo plano y responde de inmediato.
    El resultado incluye captura de pantalla."""
    return _mtc_async_common(req.placa, req.vehiculoId, req.use_proxy, bg)


@router.get(
    "/mtc/async",
    tags=["MTC"],
    summary="Consultar CITV (asíncrono, vía GET)",
    response_description="Acuse de recibo. El resultado se envía al webhook al terminar.",
    responses={
        200: {"model": AsyncAcceptedResponse, "description": "Tarea aceptada y encolada."},
        400: RESP_400_PLACA,
    },
)
def mtc_async_get(placa: str, vehiculoId: int, use_proxy: bool = True, bg: BackgroundTasks = BackgroundTasks()):
    return _mtc_async_common(placa, vehiculoId, use_proxy, bg)


def _mtc_async_common(placa: str, vehiculoId: int, use_proxy: bool, bg: BackgroundTasks):
    placa = placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    bg.add_task(servicio._run_mtc_async_task, placa, vehiculoId, use_proxy)
    return {"status": "accepted", "placa": placa, "vehiculoId": vehiculoId, "webhook": "se enviara al terminar"}


@router.get(
    "/mtc/{placa}",
    tags=["MTC"],
    summary="Consultar CITV (atajo GET)",
    response_description="Certificado de revisión técnica (CITV) más reciente.",
    responses={
        200: {"model": MtcResponse, "description": "Consulta completada."},
        400: RESP_400_PLACA,
        500: RESP_500,
    },
)
def mtc_sync_get(placa: str, vehiculoId: int, use_proxy: bool = True):
    """Atajo GET para probar rápido.
    Ej: `GET /mtc/ABC123?vehiculoId=42`
    """
    return mtc_sync(MtcRequest(placa=placa, vehiculoId=vehiculoId, use_proxy=use_proxy))
