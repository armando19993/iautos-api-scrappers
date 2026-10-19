# Plan H3 · Scripts, tests, despliegue y documentación

PRD: `.claude/prds/estructura-por-procesos.prd.md` · Estado: **Completado (19/10/2026)**

## Movimientos (con `git mv`)

| Hoy | Después |
|---|---|
| `main.py` (CLI) | `app/cli.py` → `python -m app.cli --placa ABC123` |
| `proxy.py` | `scripts/probar_proxy.py` |
| `solve_turnstile.py` | `scripts/resolver_turnstile.py` |
| `capture_headers.py` | `scripts/capturar_headers.py` |
| `scripts/mock_webhook.py`, `scripts/probar_ocr.py` | se quedan |
| `test_sunarp_parser.py`, `test_sunarp_ocr.py` | `tests/unitarios/` |
| `test_sunarp_sync.py` | `tests/integracion/` |
| `test_soat_proxy.py`, `test_sunarp.py` | `tests/carga/` (usan servicios reales y gastan CapSolver) |
| `VPS_SETUP.md` | `docs/despliegue-vps.md` |

Los tests se ejecutan desde la raíz como módulos: `python -m tests.unitarios.test_sunarp_parser`.

## Tareas

| # | Tarea | Validación | Estado |
|---|---|---|---|
| 3.1 | Mover CLI, scripts y tests; actualizar imports | Cada script/test arranca desde la raíz | Hecho |
| 3.2 | Dockerfile: `CMD ["uvicorn", "app.main:app", ...]` | `uvicorn app.main:app` validado en H2; build de la imagen pendiente en el VPS (no hay Docker local) | Hecho |
| 3.3 | `run.bat` → `python -m app.cli`; `.dockerignore` excluye `tests/`, `scripts/`, `reportes/`, `docs/` | Revisión | Hecho |
| 3.4 | `.gitignore`: agregar `reportes/` y `resultados_*.json` | `git status` no los muestra | Hecho |
| 3.4b | Limpieza: `git rm Hola.txt`; `git rm --cached api_err.log api_out.log resultados_sunarp.json` (quedan en disco) | Archivos fuera de git y presentes en disco | Hecho |
| 3.5 | Documentación viva: `CLAUDE.md`, `README.md` (estructura y comandos; quitar Playwright/`db.py` que no existen), `docs/architecture.md`, `docs/roadmap.md`, `docs/modules/estructura-por-procesos.md`, índice `docs/adr/README.md` | `grep` sin nombres viejos | Hecho |
| 3.6 | Guía corta "dónde va cada cosa" para el equipo (en `CLAUDE.md` y README): nuevo proceso = nueva carpeta en `procesos/` con `scraper/cliente`, `schemas`, `rutas`, `servicio` | Revisión | Hecho |
| 3.7 | Validación final: contrato, tests, smoke por proceso, `grep` de nombres antiguos | Todo en verde | Hecho |
| 3.8 | `/code-review` del branch, PR a `main` | Revisión: 8 hallazgos, ninguno cambia el comportamiento de la API; PR abierto a `main` | Hecho |

## Resultado

- CLI, scripts, tests y guía de despliegue movidos con `git mv`. Scripts siguen la convención de
  `probar_ocr.py` (agregan la raíz al `sys.path`) y se corren como `python scripts/x.py`; tests como
  `python -m tests.<tipo>.<test>`.
- Dockerfile arranca `app.main:app`; `run.bat` usa `python -m app.cli`; `.dockerignore` excluye
  tests, scripts, docs, reportes y `.claude`; `.gitignore` agrega `reportes/` y `resultados_*.json`.
- Limpieza: `Hola.txt` borrado; `api_err.log`, `api_out.log`, `resultados_sunarp.json` fuera de git (en disco).
- Docs: README reescrito (quitaba Playwright/MariaDB/`db.py` inexistentes), `CLAUDE.md` actualizado,
  nuevos `docs/architecture.md`, `docs/roadmap.md`, `docs/modules/estructura-por-procesos.md`.
- Validación: contrato igual, parser 9 · ocr 14 · sync 18 ok como módulos, CLI y scripts arrancan,
  sin referencias a rutas viejas.
- Integrado el hotfix de MTC (PR #5) en la rama (merge `46ff610`).

## Revisión (`/code-review`, 19/10/2026)

Sin bloqueantes. Hallazgos pendientes para después del merge:
- `CAPSOLVER_PROXIES_MTC` depende de reemplazar el texto `-country_ANY-` (frágil si cambia la lista base).
- El test de contrato no prueba que `/docs` abra con credenciales válidas.
- Rutas y tests usan funciones privadas de `servicio.py`.
- Bloque scraper + webhook duplicado entre modo síncrono y asíncrono (SOAT, MTC).
- Los tests importan `REAL` desde el test del parser (lo re-ejecutan).
- Git muestra `Hola.txt -> tests/carga/__init__.py` como renombre (ambos vacíos).
- `scripts/probar_proxy.py` conserva credenciales del canal agotado.
- Mergear el PR #5 sin squash (o después de este PR) para no repetir el conflicto del import de MTC.
