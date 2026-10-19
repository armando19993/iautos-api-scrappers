from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

class SoatRequest(BaseModel):
    placa: str = Field(
        ...,
        description="Placa del vehículo a consultar. Se normaliza a mayúsculas.",
        examples=["ABC123"],
    )
    vehiculoId: int = Field(
        ...,
        description="ID interno del vehículo en IAUTOS. Se reenvía tal cual en la "
                    "respuesta y en el webhook para correlacionar.",
        examples=[42],
    )
    use_proxy: bool = Field(
        False,
        description="Si es `true`, enruta el scraping a través de un proxy rotativo.",
    )
    headless: bool = Field(
        True,
        description="Ejecuta Chrome en modo headless (sin ventana). Deja en `true` en servidor.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"placa": "ABC123", "vehiculoId": 42, "use_proxy": False, "headless": True}
            ]
        }
    }


class SoatResponse(BaseModel):
    """Resultado de una consulta SOAT (`success` indica si hubo datos)."""
    success: bool = Field(..., description="`true` si se obtuvo el certificado SOAT.")
    placa: str = Field(..., examples=["ABC123"])
    vehiculoId: Optional[int] = Field(None, examples=[42])
    soat: Optional[Dict[str, Any]] = Field(
        None,
        description="Certificado SOAT vigente más reciente (objeto crudo de APESEG). "
                    "Si la placa no tiene certificados, contiene "
                    "`{\"Estado\": \"SIN SOAT\"}`.",
    )
    estado: Optional[str] = Field(
        None,
        description="Estado del SOAT en la raíz de la respuesta. "
                    "`SIN SOAT` cuando no hay certificados.",
        examples=["VIGENTE"],
    )
    screenshot_base64: Optional[str] = Field(
        None,
        description="Captura de pantalla del resultado como data URI PNG en base64.",
    )
    tiempo_segundos: Optional[float] = Field(None, examples=[34.2])
    error: Optional[str] = Field(
        None,
        description="Motivo. Aparece con `success:false` (fallo tecnico) o, "
                    "tambien con `success:true`, cuando la pagina no tiene "
                    "certificados para la placa (`soat:null`); en ese caso el "
                    "texto se toma de la propia pagina "
                    "(ej. `No se encontro la placa solicitada`).",
    )
    webhook: Optional[Dict[str, Any]] = Field(
        None, description="Respuesta devuelta por el webhook de IAUTOS."
    )
