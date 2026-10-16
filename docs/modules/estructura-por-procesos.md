# Módulo · Estructura por procesos

Última actualización: 16/10/2026 · Redactado por: Armando Campos
PRD: `.claude/prds/estructura-por-procesos.prd.md` · ADR: [0001](../adr/0001-estructura-por-procesos.md)

## Objetivo

Reorganizar el repo por proceso (SOAT, MTC, Sunarp) sin cambiar el contrato de la API, para
que varias personas puedan trabajar en paralelo sin chocar en los mismos archivos.

## Mapa de archivos (antes → después)

| Antes | Después |
|---|---|
| `api.py` (1143 líneas) | `app/main.py` + `app/core/{openapi,seguridad,schemas,rutas}.py` + `app/procesos/*/{rutas,schemas,servicio}.py` + `app/procesos/sunarp/pool.py`; `api.py` queda como shim |
| `config.py` | `app/core/config.py` |
| `captcha_solver.py` | `app/compartido/captcha.py` |
| `chrome_utils.py` | `app/compartido/chrome.py` |
| `webhook.py` | `app/compartido/webhook.py` |
| `scraper.py` | `app/procesos/soat/scraper.py` + `app/compartido/proxy_forwarder.py` |
| `mtc_scraper.py` | `app/procesos/mtc/scraper.py` |
| `sunarp_api.py` | `app/procesos/sunarp/cliente_http.py` |
| `sunarp_ocr.py` | `app/procesos/sunarp/ocr.py` |
| `sunarp_parser.py` | `app/procesos/sunarp/parser.py` |
| `sunarp_scraper.py` | `app/procesos/sunarp/scraper_selenium.py` |
| `main.py` | `app/cli.py` (`python -m app.cli`) |
| `proxy.py`, `solve_turnstile.py`, `capture_headers.py` | `scripts/probar_proxy.py`, `scripts/resolver_turnstile.py`, `scripts/capturar_headers.py` |
| `test_sunarp_parser.py`, `test_sunarp_ocr.py` | `tests/unitarios/` |
| `test_sunarp_sync.py` | `tests/integracion/` |
| `test_soat_proxy.py` (+ `test_sunarp.py` nuevo) | `tests/carga/` |
| `VPS_SETUP.md` | `docs/despliegue-vps.md` |
| `Hola.txt`, `*.log`, `resultados_sunarp.json` | Eliminado / fuera de git (quedan en disco) |

Todos los movimientos se hicieron con `git mv`: `git log --follow <archivo>` muestra el historial completo.

## Comandos que cambiaron

| Antes | Ahora |
|---|---|
| `uvicorn api:app` | `uvicorn app.main:app` (el anterior sigue funcionando) |
| `python main.py --placa X` | `python -m app.cli --placa X` |
| `python test_x.py` | `python -m tests.<tipo>.test_x` |
| Dockerfile `CMD ... api:app` | `CMD ... app.main:app` |

## Cómo se verificó que la API no cambió

1. **Contrato** (`tests/contrato/test_openapi.py`): OpenAPI idéntico byte a byte al de `main`,
   misma tabla de rutas en el mismo orden, `/docs`/`/redoc`/`/openapi.json` con Basic Auth.
   Validado con mutaciones (summary editado, rutas o routers en otro orden, router faltante,
   docs sin auth): todas detectadas.
2. **Tests existentes** sin cambiar aserciones: parser 9 ok, OCR 14 ok, sync 18 ok.
   Los parches de los tests apuntan a los módulos reales (verificado con un mutante).
3. **Arranque real**: `uvicorn app.main:app` y `uvicorn api:app` → `/health` 200, `/docs` 401/200.
4. **Consultas reales** (webhooks de IAUTOS interceptados): SOAT VIGENTE, MTC VIGENTE, Sunarp
   con la misma respuesta que antes, endpoints async encolan con los mismos argumentos, placa
   vacía → 400.

## Hallazgos durante el refactor

- La respuesta 401 de `/docs` envía `realm="Documentación"` en latin-1 (válido en HTTP); el
  `TestClient` de Starlette no lo decodifica, por eso el test usa una llamada ASGI directa.
- FastAPI 0.143 registra `include_router` como `_IncludedRouter`; el test de contrato aplana las rutas.
- MTC con proxy fallaba por `country_ANY` (no relacionado con el refactor) → PR #5.
