# Plan H2 · Partir `api.py` por proceso

PRD: `.claude/prds/estructura-por-procesos.prd.md` · ADR: `docs/adr/0001-estructura-por-procesos.md`
Estado: **Completado (16/10/2026)**

Objetivo: que un cambio en SOAT no toque los archivos de Sunarp ni de MTC. Hoy los tres viven
en `api.py` (1143 líneas).

## Destino de cada parte de `api.py`

| Bloque actual (líneas aprox.) | Destino |
|---|---|
| Creación de `FastAPI`, CORS, `include_router`, `shutdown` | `app/main.py` |
| `API_DESCRIPTION`, tags, `custom_openapi` (86–252) | `app/core/openapi.py` |
| `DOCS_USER/PASSWORD`, `BasicAuthMiddleware` (186–217) | `app/core/seguridad.py` |
| `ErrorDetail`, `AsyncAcceptedResponse`, `HealthResponse`, `RootResponse` | `app/core/schemas.py` |
| `GET /`, `GET /health` | `app/core/rutas.py` |
| `SoatRequest`, `SoatResponse` | `app/procesos/soat/schemas.py` |
| Endpoints `/soat*` | `app/procesos/soat/rutas.py` (`APIRouter`) |
| `_run_async_task`, `_soat_async_common` | `app/procesos/soat/servicio.py` |
| `MtcRequest`, `MtcUltimoDocumento`, `MtcResponse` | `app/procesos/mtc/schemas.py` |
| Endpoints `/mtc*` | `app/procesos/mtc/rutas.py` |
| `_run_mtc_async_task`, `_mtc_async_common` | `app/procesos/mtc/servicio.py` |
| `SunarpRequest`, `SunarpResponse`, `SunarpAsyncAcceptedResponse` | `app/procesos/sunarp/schemas.py` |
| Endpoints `/sunarp*` | `app/procesos/sunarp/rutas.py` |
| `SunarpHTTPPool`, `_get_sunarp_pool` | `app/procesos/sunarp/pool.py` |
| `_consultar_sunarp_datos`, `_procesar_sunarp`, `_run_sunarp_async_task`, flag de webhook | `app/procesos/sunarp/servicio.py` |
| — | `api.py` en raíz queda con `from app.main import app` (compatibilidad, si se aprueba) |

Regla para las rutas: el handler solo valida y delega en `servicio.py`. Los flags
(`SUNARP_WEBHOOK_ENABLED`) y dependencias (`_get_sunarp_pool`, `send_sunarp_webhook`) se leen
desde `servicio.py`, para que haya un solo lugar que parchear en tests.

## Tareas

| # | Tarea | Validación | Estado |
|---|---|---|---|
| 2.1 | Crear `core/` (openapi, seguridad, schemas, rutas) moviendo el código literal | Contrato idéntico | Hecho |
| 2.2 | Crear `soat/{schemas,rutas,servicio}.py` y registrar el router | Contrato idéntico | Hecho |
| 2.3 | Ídem `mtc/` | Contrato idéntico | Hecho |
| 2.4 | Ídem `sunarp/` + `pool.py` | Contrato idéntico | Hecho |
| 2.5 | Mantener el orden de registro de rutas y tags igual al actual (afecta el orden del OpenAPI y `/docs`) | Snapshot sin diff, incluido el orden; mutantes (orden de routers / router faltante) detectados | Hecho |
| 2.6 | `app/main.py` arma la app; `api.py` queda como shim | Ambos arrancan: health 200, /docs 401 sin auth y 200 con auth, 14 operaciones | Hecho |
| 2.7 | Actualizar parches de `test_sunarp_sync.py` a `app.procesos.sunarp.servicio` | sync 18 ok con parches en `servicio` | Hecho |
| 2.8 | Smoke real con uvicorn local: `GET /health`, 1 SOAT, 1 MTC, 1 Sunarp (sync); `/docs` pide Basic Auth | Ver resultado abajo | Hecho |
| 2.9 | Commit `refactor: separar api por proceso` | — | Hecho |

## Resultado

- `api.py`: 1143 → 12 líneas (shim). Código repartido en 15 módulos (el mayor, 166 líneas),
  cortado literalmente por rangos de líneas; solo se cambiaron las rutas para delegar en
  `servicio.py` (`consultar`, `consultar_sincrono`) y las tareas async.
- Contrato OpenAPI idéntico byte a byte al snapshot de `main`. pyflakes limpio en los módulos nuevos.
- Hallazgo: FastAPI 0.143 (sin versión fijada en `requirements.txt`) registra `include_router`
  como `_IncludedRouter` en `app.routes`. El test de contrato ahora aplana la tabla de rutas
  respetando el orden.
- Smoke real (webhooks de IAUTOS interceptados, no se envió nada):
  - `POST /soat` → 200, `success:true`, VIGENTE (23 s).
  - `POST /mtc` sin proxy → 200, `success:true`, VIGENTE (17 s).
  - `POST /sunarp` → 200, `success:false` "Tesseract no instalado" (esperado en local; mismo comportamiento que antes).
  - `/soat/async`, `/mtc/async` encolan la tarea con los mismos argumentos; `/sunarp/async` acepta.
  - Placa vacía → 400.
- **Hallazgo fuera del refactor:** `POST /mtc` con proxy falla con `country_ANY` (el MTC no
  muestra el captcha a IPs extranjeras) y funciona con `country_PE`. La regresión viene del
  commit `5d89ff6` ya en `main`. Pendiente de decisión.
- Los 500 de MTC ante `ERR_TUNNEL_CONNECTION_FAILED` ya existían (sin `except` en la ruta).
