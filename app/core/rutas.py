from fastapi import APIRouter

from app.core.schemas import HealthResponse, RootResponse

router = APIRouter()

@router.get(
    "/",
    tags=["Sistema"],
    summary="Índice de la API",
    response_description="Enlace a la documentación y mapa de endpoints.",
    response_model=RootResponse,
)
def root():
    return {
        "redoc": "/redoc",
        "endpoints": {
            "soat_sincrono": "POST /soat  (~30-40s)",
            "soat_async": "POST /soat/async  (background + webhook)",
            "mtc_sincrono": "POST /mtc  (~10-15s)",
            "mtc_async": "POST /mtc/async  (background + webhook)",
            "sunarp_sincrono": "POST /sunarp  (HTTP directo, ~3s)",
            "sunarp_async": "POST /sunarp/async  (background)",
            "health": "GET /health",
        },
    }


@router.get(
    "/health",
    tags=["Sistema"],
    summary="Health check",
    response_description="Estado del servicio.",
    response_model=HealthResponse,
)
def health():
    return {"status": "ok"}
