from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

class SunarpRequest(BaseModel):
    placa: str = Field(
        ...,
        description="Placa del vehículo a consultar. Se normaliza a mayúsculas.",
        examples=["ABC123"],
    )
    empresaId: int = Field(
        ..., ge=0, le=255,
        description="ID de la empresa (`Veh_EmpId`, tinyint) a la que se asocia el vehículo.",
        examples=[3],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"placa": "ABC123", "empresaId": 3}]
        }
    }


class SunarpResponse(BaseModel):
    """Resultado de una consulta vehicular en Sunarp."""
    success: bool = Field(..., description="`true` si se obtuvo la tarjeta vehicular.")
    placa: str = Field(..., examples=["ABC123"])
    operacion: Optional[str] = Field(
        None, examples=["datos_vehiculo"],
        description="`datos_vehiculo` cuando el webhook está apagado (`SUNARP_WEBHOOK_ENABLED=false`); "
                    "`null` si falló.",
    )
    empresaId: Optional[int] = Field(None, examples=[3], description="Empresa recibida en la petición.")
    vehiculo: Optional[Dict[str, Optional[str]]] = Field(
        None,
        description="Datos parseados del OCR con las columnas `Veh_*` de la tabla `vehiculo` "
                    "(sin `Veh_EmpId`). Campos vacíos = `null`; propietarios faltantes = `SIN INFORMACION`.",
    )
    vehiculoId: Optional[int] = Field(
        None, examples=[42],
        description="Solo con `SUNARP_WEBHOOK_ENABLED=true`: `Veh_Id` devuelto por el webhook de inserción; "
                    "`null` si no se pudo registrar. Con el webhook apagado no se incluye.",
    )
    result_image_base64: Optional[str] = Field(
        None,
        description="Tarjeta de identificación vehicular como data URI PNG en base64.",
    )
    ocr_text: Optional[str] = Field(
        None, description="Texto extraído por OCR (Tesseract) de la imagen."
    )
    raw_response: Optional[Dict[str, Any]] = Field(
        None, description="Respuesta cruda de la API de Sunarp."
    )
    tiempo_segundos: Optional[float] = Field(None, examples=[3.1])
    error: Optional[str] = Field(
        None, description="Mensaje de error cuando `success` es `false`."
    )
    webhook: Optional[Dict[str, Any]] = Field(
        None, description="Respuesta del webhook de inserción de vehículo."
    )


class SunarpAsyncAcceptedResponse(BaseModel):
    """Acuse de una consulta Sunarp asíncrona. El `vehiculoId` lo genera el receptor del webhook."""
    status: str = Field("accepted", examples=["accepted"])
    placa: str = Field(..., examples=["ABC123"])
