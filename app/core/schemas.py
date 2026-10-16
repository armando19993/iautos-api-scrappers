from typing import Dict

from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    """Error HTTP estándar de FastAPI (códigos 4xx/5xx)."""
    detail: str = Field(..., examples=["placa requerida"])


class AsyncAcceptedResponse(BaseModel):
    """Acuse de recibo de una consulta asíncrona. El resultado llega por webhook."""
    status: str = Field("accepted", examples=["accepted"])
    placa: str = Field(..., examples=["ABC123"])
    vehiculoId: int = Field(..., examples=[42])
    webhook: str = Field(..., examples=["se enviara al terminar"])


class HealthResponse(BaseModel):
    status: str = Field("ok", examples=["ok"])


class RootResponse(BaseModel):
    redoc: str = Field("/redoc", examples=["/redoc"])
    endpoints: Dict[str, str]


RESP_400_PLACA = {
    "model": ErrorDetail,
    "description": "Petición inválida: la placa está vacía.",
    "content": {"application/json": {"example": {"detail": "placa requerida"}}},
}

RESP_422 = {
    "description": "Error de validación: falta un campo requerido o tiene un tipo incorrecto.",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "vehiculoId"],
                        "msg": "Field required",
                        "input": {"placa": "ABC123"},
                    }
                ]
            }
        }
    },
}

RESP_500 = {
    "model": ErrorDetail,
    "description": "Error interno: fallo inesperado del scraper o del navegador.",
    "content": {"application/json": {"example": {"detail": "Internal Server Error"}}},
}
