# Arquitectura

Última actualización: 16/10/2026 · Redactado por: Armando Campos

## Vista general

```
Cliente IAUTOS ──HTTP──► FastAPI (app/main.py)
                          │  CORS → BasicAuth (/docs, /redoc, /openapi.json)
                          ├── /, /health           app/core/rutas.py
                          ├── /soat*               app/procesos/soat/rutas.py   → servicio → SOATScraper (Chrome)
                          ├── /mtc*                app/procesos/mtc/rutas.py    → servicio → MTCScraper  (Chrome)
                          └── /sunarp*             app/procesos/sunarp/rutas.py → servicio → pool → SunarpHTTP (httpx)
                                                                                         └── ocr → parser
Servicios externos:
  CapSolver API (Turnstile, captcha de imagen) · Proxy residencial CapSolver
  apeseg.org.pe · rec.mtc.gob.pe · api-gateway.sunarp.gob.pe
  Webhooks IAUTOS (SOAT, MTC) · WEBHOOK_SUNARP_URL (Sunarp, opcional)
```

## Capas por proceso

| Capa | Responsabilidad | No debe |
|---|---|---|
| `rutas.py` | Declarar endpoints (`APIRouter`), validar la placa, traducir errores a HTTP (400, 503) | Contener lógica de scraping o webhooks |
| `servicio.py` | Orquestar: crear el scraper/cliente, normalizar el resultado, enviar al webhook, tareas async en hilos | Conocer detalles de FastAPI más allá de lo necesario |
| `scraper.py` / `cliente_http.py` | Hablar con el sitio oficial y devolver un `dict` con `success` | Llamar a webhooks |
| `schemas.py` | Modelos Pydantic de petición y respuesta (documentación del contrato) | — |

`app/compartido/` contiene lo que usan varios procesos: `captcha.py` (CapSolver),
`chrome.py` (creación de Chrome con detección de versión y lock de arranque),
`proxy_forwarder.py` (túnel CONNECT local hacia el proxy residencial) y `webhook.py`.

`app/core/` contiene la configuración (`config.py`, lee `.env`), la documentación OpenAPI
(`openapi.py`), la protección de `/docs` (`seguridad.py`), los modelos y bloques de respuesta
compartidos (`schemas.py`) y las rutas `/` y `/health`.

## Flujos

- **Síncrono SOAT/MTC**: ruta → `servicio.consultar` → scraper (Chrome, 10–40 s) → webhook IAUTOS → respuesta.
- **Asíncrono SOAT/MTC**: ruta → `BackgroundTasks` → hilo daemon → scraper → webhook IAUTOS.
- **Sunarp**: ruta → `servicio.consultar_sincrono` → pool de clientes HTTP (`SUNARP_POOL_SIZE`) →
  Turnstile (CapSolver) → API Sunarp → OCR → parser. Con `SUNARP_WEBHOOK_ENABLED=true` (y siempre en
  async) registra el vehículo por webhook y devuelve `vehiculoId`.

## Proxies

Mismas sesiones del proxy residencial de CapSolver, con salida distinta por proceso:

| Proceso | Lista | País |
|---|---|---|
| SOAT | `CAPSOLVER_PROXIES` | `country_ANY` |
| MTC | `CAPSOLVER_PROXIES_MTC` | `country_PE` (el MTC no muestra el captcha a IPs extranjeras) |
| Sunarp | — | Sin proxy |

## Contrato de la API

`tests/contrato/openapi.snapshot.json` congela el OpenAPI y la tabla de rutas. El test
`python -m tests.contrato.test_openapi` falla si cambian; un cambio intencional se publica
regenerando el snapshot (`--actualizar`) en el mismo PR.

## Despliegue

Imagen Docker (`Dockerfile`, Python 3.11 + Chrome + Tesseract) arrancada con
`uvicorn app.main:app`. Detalle en [despliegue-vps.md](despliegue-vps.md).

## Decisiones

Ver [ADR](adr/README.md).
