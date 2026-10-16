# Plan H2 · Partir `api.py` por proceso

PRD: `.claude/prds/estructura-por-procesos.prd.md` · ADR: `docs/adr/0001-estructura-por-procesos.md`
Estado: **Aprobado — pendiente de ejecución**

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
| 2.1 | Crear `core/` (openapi, seguridad, schemas, rutas) moviendo el código literal | Contrato idéntico | Pendiente |
| 2.2 | Crear `soat/{schemas,rutas,servicio}.py` y registrar el router | Contrato idéntico | Pendiente |
| 2.3 | Ídem `mtc/` | Contrato idéntico | Pendiente |
| 2.4 | Ídem `sunarp/` + `pool.py` | Contrato idéntico | Pendiente |
| 2.5 | Mantener el orden de registro de rutas y tags igual al actual (afecta el orden del OpenAPI y `/docs`) | Snapshot sin diff, incluido el orden | Pendiente |
| 2.6 | `app/main.py` arma la app; `api.py` queda como shim | `uvicorn api:app` y `uvicorn app.main:app` arrancan | Pendiente |
| 2.7 | Actualizar parches de `test_sunarp_sync.py` a `app.procesos.sunarp.servicio` | Pasa; y falla si se quita un parche | Pendiente |
| 2.8 | Smoke real con uvicorn local: `GET /health`, 1 SOAT, 1 MTC, 1 Sunarp (sync); `/docs` pide Basic Auth | Misma forma de respuesta que hoy | Pendiente |
| 2.9 | Commit `refactor: separar api por proceso` | — | Pendiente |
