from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

class MtcRequest(BaseModel):
    placa: str = Field(
        ...,
        description="Placa del vehículo a consultar. Se normaliza a mayúsculas.",
        examples=["ABC123"],
    )
    vehiculoId: int = Field(
        ...,
        description="ID interno del vehículo en IAUTOS. Se reenvía en la respuesta y el webhook.",
        examples=[42],
    )
    use_proxy: bool = Field(
        True,
        description="Si es `true`, enruta las peticiones HTTP por un proxy rotativo. "
                    "Recomendado: el sitio MTC bloquea IPs de servidores.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"placa": "ABC123", "vehiculoId": 42, "use_proxy": True}
            ]
        }
    }


class MtcUltimoDocumento(BaseModel):
    """Último certificado CITV encontrado para la placa."""
    empresa_certificadora: str = Field("", examples=["REVISIONES TECNICAS DEL PERU S.A."])
    direccion: str = ""
    placa: str = Field("", examples=["ABC123"])
    nro_certificado: str = Field("", examples=["12345-2025"])
    tipo_documento: str = ""
    vigente_desde: str = Field("", examples=["01/01/2025"])
    vigente_hasta: str = Field("", examples=["01/01/2026"])
    resultado_inspeccion: str = Field("", examples=["APROBADO"])
    estado: str = Field("", examples=["VIGENTE"])
    ambito: str = ""
    tipo_servicio: str = ""
    observaciones: str = ""


class MtcResponse(BaseModel):
    """Resultado de una consulta CITV (MTC)."""
    success: bool = Field(..., description="`true` si se obtuvo el certificado CITV.")
    placa: str = Field(..., examples=["ABC123"])
    vehiculoId: Optional[int] = Field(None, examples=[42])
    fuente: Optional[str] = Field(None, examples=["MTC_CITV"])
    ultimo_documento: Optional[MtcUltimoDocumento] = Field(
        None, description="Certificado CITV más reciente, con campos normalizados."
    )
    documentos_completos: Optional[List[Dict[str, Any]]] = Field(
        None, description="Todos los documentos crudos devueltos por el MTC."
    )
    screenshot_base64: Optional[str] = Field(
        None,
        description="Captura de pantalla del resultado como base64 PNG.",
    )
    tiempo_segundos: Optional[float] = Field(None, examples=[12.3])
    error: Optional[str] = Field(
        None, description="Mensaje de error cuando `success` es `false`."
    )
    webhook: Optional[Dict[str, Any]] = Field(
        None, description="Respuesta devuelta por el webhook de IAUTOS."
    )
