import base64
import threading
import time
import queue
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from scraper import SOATScraper
from mtc_scraper import MTCScraper
from sunarp_api import SunarpHTTP
from webhook import send_to_webhook, send_sunarp_webhook
from config import SUNARP_POOL_SIZE, SUNARP_SYNC_WAIT_SECONDS, WEBHOOK_SUNARP_INSERT_RETRIES
from sunarp_parser import parse_ocr_text, tiene_datos


class SunarpHTTPPool:
    """Pool thread-safe de clientes HTTP para Sunarp (sin Selenium). ~3s por consulta."""

    def __init__(self, size=5):
        self._queue: queue.Queue[SunarpHTTP] = queue.Queue(maxsize=size)
        self.size = size
        self._clients = []

    def start(self):
        print(f"[SunarpPool] Iniciando {self.size} clientes HTTP...")
        for i in range(self.size):
            c = SunarpHTTP()
            self._clients.append(c)
            self._queue.put(c)
        print(f"[SunarpPool] Pool listo: {self.size} clientes disponibles")

    def acquire(self, timeout: Optional[float] = 30) -> SunarpHTTP:
        """timeout=None espera indefinidamente (jobs async: se encolan)."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"No hay cliente disponible tras {timeout}s "
                f"({self._queue.qsize()}/{self.size} libres)"
            )

    def release(self, client: SunarpHTTP):
        self._queue.put(client)

    def consultar(self, placa: str, timeout: Optional[float] = 30) -> dict:
        client = self.acquire(timeout)
        try:
            return client.consultar(placa)
        finally:
            self.release(client)

    def stop(self):
        for c in self._clients:
            try:
                c.close()
            except Exception:
                pass


# ── Instancia global del pool ──
_sunarp_pool: SunarpHTTPPool | None = None
_sunarp_pool_lock = threading.Lock()


def _get_sunarp_pool() -> SunarpHTTPPool:
    global _sunarp_pool
    with _sunarp_pool_lock:
        if _sunarp_pool is None:
            pool = SunarpHTTPPool(size=SUNARP_POOL_SIZE)
            pool.start()
            _sunarp_pool = pool
    return _sunarp_pool


# ─────────────────────────────────────────────────────────────────────────────
#  Metadatos de la documentación (ReDoc / Swagger)
# ─────────────────────────────────────────────────────────────────────────────

API_DESCRIPTION = """
API de scrapers de **IAUTOS** para consultar información oficial de vehículos
en el Perú a partir de la **placa**.

Reúne tres fuentes en una sola API:

| Fuente | Qué entrega | Endpoint | Tiempo aprox. |
|--------|-------------|----------|---------------|
| **SOAT** (APESEG) | Certificado SOAT vigente + captura | `POST /soat` | ~30–40 s |
| **CITV** (MTC) | Revisión técnica vigente + captura | `POST /mtc` | ~10–15 s |
| **Registro vehicular** (Sunarp) | Tarjeta de identificación + OCR | `POST /sunarp` | ~3 s |

## Modos de ejecución

Cada fuente ofrece dos modos:

- **Síncrono** (`POST /soat`, `/mtc`, `/sunarp`): la petición **bloquea** hasta
  obtener el resultado y lo devuelve en el cuerpo de la respuesta.
- **Asíncrono** (`/soat/async`, `/mtc/async`, `/sunarp/async`): responde de
  inmediato con `202`/`accepted` y procesa en segundo plano; al terminar
  **envía el resultado al webhook** de IAUTOS.

También existen **atajos GET** (`GET /soat/{placa}?vehiculoId=42`) pensados para
pruebas rápidas desde el navegador.

## Captcha y webhook

- Los captchas (reCAPTCHA / Cloudflare Turnstile) se resuelven automáticamente
  mediante **CapSolver**.
- Al finalizar, el resultado de SOAT y MTC se reenvía al webhook configurado en
  IAUTOS (`send_to_webhook`).

## Convención de respuestas

Todas las consultas devuelven un objeto JSON con el campo booleano **`success`**:

- `success: true`  → se obtuvieron los datos (ver el bloque correspondiente).
- `success: false` → no se pudo obtener el dato; el motivo va en **`error`**.
  Nota: una consulta fallida se devuelve con **HTTP 200** y `success:false`,
  no como un error HTTP. Los códigos `4xx`/`5xx` se reservan para errores de la
  propia petición (placa faltante, validación, fallo interno).
""".strip()

tags_metadata = [
    {
        "name": "SOAT",
        "description": "Consulta del **SOAT vigente** en APESEG (apeseg.org.pe). "
                       "Usa navegador headless + CapSolver. Incluye captura de pantalla.",
    },
    {
        "name": "MTC",
        "description": "Consulta de la **revisión técnica (CITV)** en el MTC "
                       "(rec.mtc.gob.pe). Usa navegador headless + CapSolver. "
                       "Incluye captura de pantalla.",
    },
    {
        "name": "Sunarp",
        "description": "Consulta del **registro vehicular** en Sunarp "
                       "(consultavehicular.sunarp.gob.pe). HTTP directo (~3 s) con OCR "
                       "de la tarjeta de identificación vehicular.",
    },
    {
        "name": "Sistema",
        "description": "Endpoints utilitarios: índice de la API y health check.",
    },
]

app = FastAPI(
    title="Api Scrappers IAUTOS",
    description=API_DESCRIPTION,
    version="1.2.0",
    contact={
        "name": "IAUTOS",
        "url": "https://next.iautos.pe",
    },
    license_info={
        "name": "Uso privado — IAUTOS",
    },
    servers=[
        {"url": "http://localhost:8000", "description": "Local (desarrollo)"},
        {"url": "http://200.234.233.170:8000", "description": "Producción"},
    ],
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Basic Auth para documentación (/docs, /redoc, /openapi.json)
# ─────────────────────────────────────────────────────────────────────────────

DOCS_USER = "waytech"
DOCS_PASSWORD = "iautos2026!"
PROTECTED_PATHS = ("/docs", "/redoc", "/openapi.json")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Middleware que protege las rutas de documentación con HTTP Basic Auth."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in PROTECTED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                user, password = decoded.split(":", 1)
                if user == DOCS_USER and password == DOCS_PASSWORD:
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            content="Credenciales inválidas",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Documentación"'},
        )


app.add_middleware(BasicAuthMiddleware)


# ─────────────────────────────────────────────────────────────────────────────
#  Esquema OpenAPI personalizado: inyecta el logo de IAUTOS para ReDoc (x-logo)
# ─────────────────────────────────────────────────────────────────────────────

def custom_openapi():
    """Genera el esquema OpenAPI una sola vez e inyecta `x-logo`.

    ReDoc lee `info["x-logo"]` para mostrar el logo en la cabecera de la
    documentación. También añadimos un pie de página con enlace a IAUTOS.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        contact=app.contact,
        license_info=app.license_info,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://next.iautos.pe/logo.svg",
        "altText": "IAUTOS",
        "backgroundColor": "#FFFFFF",
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ─────────────────────────────────────────────────────────────────────────────
#  Modelos de petición (request bodies)
# ─────────────────────────────────────────────────────────────────────────────

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
    platemId: int = Field(
        ..., ge=1,
        description="ID de la fila de `placa_temporal` (`PlaTem_Id`) que se marca como ejecutada.",
        examples=[39698],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"placa": "ABC123", "empresaId": 3, "platemId": 39698}]
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Modelos de respuesta (solo documentación — no filtran la salida real)
# ─────────────────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Error HTTP estándar de FastAPI (códigos 4xx/5xx)."""
    detail: str = Field(..., examples=["placa requerida"])


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


class SunarpResponse(BaseModel):
    """Resultado de una consulta vehicular en Sunarp."""
    success: bool = Field(..., description="`true` si se obtuvo la tarjeta vehicular.")
    placa: str = Field(..., examples=["ABC123"])
    vehiculoId: Optional[int] = Field(
        None, examples=[42],
        description="`Veh_Id` devuelto por el webhook de inserción; `null` si no se pudo registrar.",
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
    platemId: int = Field(..., examples=[39698])


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


# ─────────────────────────────────────────────────────────────────────────────
#  Respuestas de error reutilizables (para el bloque `responses=`)
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
#  Sistema
# ─────────────────────────────────────────────────────────────────────────────

@app.get(
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


@app.get(
    "/health",
    tags=["Sistema"],
    summary="Health check",
    response_description="Estado del servicio.",
    response_model=HealthResponse,
)
def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
#  SOAT
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
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

    scraper = SOATScraper(use_proxy=req.use_proxy, headless=req.headless)
    try:
        scraper.start()
        result = scraper.consultar_soat(placa)
        if not result.get("placa"):
            result["placa"] = placa
        result["vehiculoId"] = req.vehiculoId
    finally:
        scraper.stop()

    result["webhook"] = send_to_webhook(result)
    return result


def _soat_async_common(placa: str, vehiculoId: int, use_proxy: bool, headless: bool, bg: BackgroundTasks):
    placa = placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    bg.add_task(_run_async_task, placa, vehiculoId, use_proxy, headless)
    return {"status": "accepted", "placa": placa, "vehiculoId": vehiculoId, "webhook": "se enviara al terminar"}


@app.post(
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


@app.get(
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


@app.get(
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


# ─────────────────────────────────────────────────────────────────────────────
#  MTC CITV
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
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

    scraper = MTCScraper(use_proxy=req.use_proxy)
    try:
        scraper.start()
        result = scraper.consultar(placa)
        if not result.get("placa"):
            result["placa"] = placa
        result["vehiculoId"] = req.vehiculoId
    finally:
        scraper.stop()

    result["webhook"] = send_to_webhook(result, source="mtc")
    return result


@app.post(
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


@app.get(
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
    bg.add_task(_run_mtc_async_task, placa, vehiculoId, use_proxy)
    return {"status": "accepted", "placa": placa, "vehiculoId": vehiculoId, "webhook": "se enviara al terminar"}


@app.get(
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


# ─────────────────────────────────────────────────────────────────────────────
#  Sunarp consulta vehicular
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
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
                                "vehiculoId": 42,
                            },
                        },
                        "sin_resultado": {
                            "summary": "No se obtuvo el registro",
                            "value": {
                                "success": False,
                                "placa": "ABC123",
                                "error": "HTTP 404: no se encontró el vehículo",
                                "tiempo_segundos": 2.4,
                                "vehiculoId": None,
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
    """Consulta vehicular en Sunarp (~3s), registra el vehículo vía webhook y
    devuelve el `Veh_Id` generado en `vehiculoId`.
    Thread-safe: el pool (compartido con el modo async) asigna un cliente HTTP libre."""
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    try:
        return _procesar_sunarp(placa, req.empresaId, req.platemId, SUNARP_SYNC_WAIT_SECONDS)
    except TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Servicio Sunarp saturado: sin cliente disponible, reintente en unos segundos",
        )


@app.post(
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
    lo genera el receptor del webhook, que lo relaciona con `platemId`)."""
    return _sunarp_async_common(req.placa, req.empresaId, req.platemId, bg)


@app.get(
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
    platemId: int = Query(..., ge=1),
):
    return _sunarp_async_common(placa, empresaId, platemId, bg)


def _sunarp_async_common(placa: str, empresaId: int, platemId: int, bg: BackgroundTasks):
    placa = placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")
    bg.add_task(_run_sunarp_async_task, placa, empresaId, platemId)
    return {"status": "accepted", "placa": placa, "platemId": platemId}


@app.get(
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
    platemId: int = Query(..., ge=1),
):
    """Atajo GET para probar rápido.
    Ej: `GET /sunarp/ABC123?empresaId=3&platemId=39698`
    """
    return sunarp_sync(SunarpRequest(placa=placa, empresaId=empresaId, platemId=platemId))


# ─────────────────────────────────────────────────────────────────────────────
#  Tareas en segundo plano
# ─────────────────────────────────────────────────────────────────────────────

def _run_async_task(placa: str, vehiculoId: int, use_proxy: bool, headless: bool = True):
    """Corre el scraper en un hilo separado (FastAPI BackgroundTasks es async;
    el scraper usa undetected-chromedriver que es bloqueante) y envia al webhook."""
    def _work():
        scraper = SOATScraper(use_proxy=use_proxy, headless=headless)
        try:
            scraper.start()
            result = scraper.consultar_soat(placa)
            if not result.get("placa"):
                result["placa"] = placa
            result["vehiculoId"] = vehiculoId
        except Exception as e:
            result = {"placa": placa, "vehiculoId": vehiculoId, "success": False, "error": str(e)}
        finally:
            scraper.stop()
        result["webhook"] = send_to_webhook(result)
        print(f"[async] placa={placa} vehiculoId={vehiculoId} success={result.get('success')} webhook={result['webhook']}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


def _run_mtc_async_task(placa: str, vehiculoId: int, use_proxy: bool = False):
    """Corre el scraper MTC en un hilo separado y envia al webhook."""
    def _work():
        scraper = MTCScraper(use_proxy=use_proxy)
        try:
            scraper.start()
            result = scraper.consultar(placa)
            if not result.get("placa"):
                result["placa"] = placa
            result["vehiculoId"] = vehiculoId
        except Exception as e:
            result = {"placa": placa, "vehiculoId": vehiculoId, "success": False, "error": str(e)}
        finally:
            scraper.stop()
        result["webhook"] = send_to_webhook(result, source="mtc")
        print(f"[mtc_async] placa={placa} vehiculoId={vehiculoId} success={result.get('success')} webhook={result['webhook']}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


def _marcar_placa_temporal(platemId: int):
    """Marca PlaTem_Ejecucion=1 en un hilo aparte; si falla solo se registra en log."""
    def _work():
        try:
            resp = send_sunarp_webhook({
                "operacion": "actualizar_placa_temporal",
                "platemId": platemId,
                "ejecucion": 1,
            })
            if resp.get("webhook_error") or resp.get("success") is False:
                print(f"[sunarp] WARN placa_temporal platemId={platemId} no actualizada: {resp}")
        except Exception as e:
            print(f"[sunarp] WARN placa_temporal platemId={platemId} error: {e}")

    threading.Thread(target=_work, daemon=True).start()


def _procesar_sunarp(placa: str, empresaId: int, platemId: int, acquire_timeout: Optional[float]) -> dict:
    """Flujo completo Sunarp: marca placa_temporal (en paralelo), scraping/OCR, parseo,
    INSERT por webhook y `vehiculoId` = Veh_Id. Lanza TimeoutError si no hay cliente libre
    dentro de `acquire_timeout` (None = esperar)."""
    _marcar_placa_temporal(platemId)

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

    ocr_text = result.get("ocr_text") or ""
    if not ocr_text.strip():
        return _fail("OCR sin texto: no se pudo leer la tarjeta vehicular")
    vehiculo = parse_ocr_text(ocr_text, empresaId, placa)
    if not tiene_datos(vehiculo):
        return _fail("El OCR no contiene datos del vehículo")

    ins = send_sunarp_webhook(
        {"operacion": "insertar_vehiculo", "platemId": platemId, "empresaId": empresaId, "vehiculo": vehiculo},
        retries=WEBHOOK_SUNARP_INSERT_RETRIES,
    )
    result["webhook"] = ins
    veh_id = ins.get("vehiculoId")
    if ins.get("success") is True and isinstance(veh_id, int) and not isinstance(veh_id, bool) and veh_id > 0:
        result["vehiculoId"] = veh_id
        print(f"[sunarp] placa={placa} platemId={platemId} vehiculoId={veh_id} accion={ins.get('accion')}")
        return result
    motivo = ins.get("error") or ins.get("webhook_error") or "respuesta inválida del webhook (success/vehiculoId)"
    print(f"[sunarp] ERROR insert placa={placa} platemId={platemId}: {ins}")
    return _fail(f"No se pudo registrar el vehículo: {motivo}")


def _run_sunarp_async_task(placa: str, empresaId: int, platemId: int):
    """Corre el flujo Sunarp en un hilo; si el pool esta lleno el job espera su turno."""
    def _work():
        try:
            result = _procesar_sunarp(placa, empresaId, platemId, None)
        except Exception as e:
            result = {"placa": placa, "success": False, "error": str(e), "vehiculoId": None}
        print(f"[sunarp_async] placa={placa} platemId={platemId} vehiculoId={result.get('vehiculoId')} "
              f"success={result.get('success')} error={result.get('error')}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


@app.on_event("shutdown")
def shutdown():
    global _sunarp_pool
    if _sunarp_pool:
        print("[api] Cerrando pool HTTP Sunarp...")
        _sunarp_pool.stop()
        _sunarp_pool = None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
