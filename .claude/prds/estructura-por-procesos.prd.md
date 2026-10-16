# PRD · Estructura del proyecto por procesos

| Campo | Valor |
|---|---|
| Módulo | estructura-por-procesos |
| Repo | `armando19993/iautos-api-scrappers` |
| Redactado por | Armando Campos |
| Estado | **Aprobado (16/10/2026) — en desarrollo** |
| Fecha | 16/10/2026 |

## 1. Problema

Todo el código vive en la raíz del repo con nombres que no dicen a qué proceso pertenecen
(`scraper.py` es SOAT, `sunarp_api.py` es el cliente HTTP de Sunarp, `proxy.py` es un script
de prueba). `api.py` tiene 1143 líneas con las rutas, modelos, tareas async, pool y
documentación de los tres procesos. Otras personas van a empezar a hacer cambios: con esta
forma, dos personas que tocan procesos distintos chocan en el mismo archivo, y no hay nada
que avise si un cambio rompe el contrato de la API.

## 2. Objetivo

Reorganizar el repo por proceso (SOAT, MTC/CITV, Sunarp) y por responsabilidad, **sin cambiar
el comportamiento de la API**: mismas rutas, métodos, parámetros, modelos y respuestas.

## 3. Alcance

**Dentro**
- Paquete `app/` con `core/`, `compartido/` y `procesos/{soat,mtc,sunarp}/`.
- Partir `api.py` en rutas, schemas y servicios por proceso.
- Mover scripts de ayuda a `scripts/`, pruebas a `tests/` y documentación a `docs/`.
- Test de contrato que congela el OpenAPI actual y falla si cambia.
- Actualizar Dockerfile, `run.bat`, `.dockerignore`, README, `CLAUDE.md` y documentación viva.

**Fuera** (no se cambia en este módulo)
- Lógica de scraping, captcha, proxy, OCR, parser o webhooks.
- Contrato de la API (rutas, modelos, códigos de respuesta).
- Variables de entorno y su significado.

## 4. Requisitos

| ID | Requisito | Verificación |
|---|---|---|
| R1 | El OpenAPI generado después del refactor es idéntico al de antes | `tests/contrato` compara contra snapshot |
| R2 | Los tests actuales (parser, OCR, sunarp sync) pasan sin cambiar sus aserciones | Ejecutarlos antes y después |
| R3 | Una consulta real por proceso (SOAT, MTC, Sunarp) devuelve la misma forma de respuesta | Smoke contra uvicorn local |
| R4 | El historial de cada archivo se conserva | Movimientos con `git mv`; `git log --follow` |
| R5 | El arranque del contenedor sigue funcionando | Dockerfile apunta al nuevo módulo; build en el VPS |
| R6 | Cada proceso se puede modificar sin tocar archivos de los otros | Revisión de la estructura final |
| R7 | No quedan referencias a nombres viejos en código, scripts ni docs | `grep` de los nombres antiguos |

## 5. Hitos

| Hito | Descripción | Plan | Estado |
|---|---|---|---|
| H0 | Rama de trabajo + test de contrato (línea base) | `.claude/plans/h0-linea-base.plan.md` | Completado |
| H1 | Mover y renombrar módulos por proceso (sin partir `api.py`) | `.claude/plans/h1-mover-modulos.plan.md` | Completado |
| H2 | Partir `api.py` en rutas/schemas/servicios por proceso | `.claude/plans/h2-partir-api.plan.md` | Completado |
| H3 | Scripts, tests, despliegue y documentación | `.claude/plans/h3-despliegue-docs.plan.md` | Aprobado, pendiente |
| H4 | (Opcional) Guardarraíles del equipo: CI, plantilla de PR, protección de `main`, secretos a env | — | Fuera de alcance (decisión 16/10/2026) |

## 6. Línea base (medida el 16/10/2026 sobre `main` = `2088194`)

- OpenAPI: 14 operaciones, 14 schemas.
  `GET /`, `GET /health`, y para `soat`, `mtc` y `sunarp`: `POST /x`, `POST /x/async`, `GET /x/async`, `GET /x/{placa}`.
- Rutas fuera del schema: `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc` (con Basic Auth).
- Tests: `test_sunarp_parser.py` (9 ok), `test_sunarp_ocr.py` (14 ok), `test_sunarp_sync.py` (18 ok) pasan (scripts, sin pytest).
- Contrato congelado en `tests/contrato/openapi.snapshot.json` (14 operaciones, 14 schemas, 18 rutas).
- Docker no está disponible en la máquina local; el build se valida en el VPS.

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Comandos de arranque externos (`uvicorn api:app` en el VPS o en scripts de alguien) | Se mantiene un `api.py` mínimo de compatibilidad durante la transición (ver ADR 0001) |
| Los tests parchean `api._get_sunarp_pool`, `api.SUNARP_WEBHOOK_ENABLED`, etc. | Las rutas delegan en `servicio.py`; los parches apuntan a ese módulo y se verifica que el test falle si el parche no aplica |
| Ramas abiertas de otras personas quedan en conflicto | Hacer el refactor en una rama corta y avisar antes de mergear; `git mv` ayuda a Git a seguir los renombres |
| FastAPI sin versión fijada: 0.143 cambió la forma de `app.routes` con `include_router` | El test de contrato aplana las rutas; evaluar fijar versiones en `requirements.txt` |
| `load_dotenv()` y rutas relativas dependen del directorio de trabajo | Se sigue arrancando desde la raíz; se valida con uvicorn real |

## 8. Decisiones (16/10/2026)

1. Se mantiene `api.py` en la raíz como shim (`from app.main import app`) durante la transición.
2. Se trabaja en la rama `refactor/estructura-procesos`, un commit por hito, y PR a `main`.
3. Limpieza: se borra `Hola.txt`; `api_err.log`, `api_out.log` y `resultados_sunarp.json` se
   quitan de git (`git rm --cached`) y se conservan en disco.
4. H4 queda fuera de este módulo.
