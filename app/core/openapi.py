from fastapi.openapi.utils import get_openapi

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


def instalar_openapi(app):
    """Reemplaza `app.openapi` por la version que inyecta el logo de IAUTOS para ReDoc."""

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
