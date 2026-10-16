# Plan H3 · Scripts, tests, despliegue y documentación

PRD: `.claude/prds/estructura-por-procesos.prd.md` · Estado: **Aprobado — pendiente de ejecución**

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
| 3.1 | Mover CLI, scripts y tests; actualizar imports | Cada script/test arranca desde la raíz | Pendiente |
| 3.2 | Dockerfile: `CMD ["uvicorn", "app.main:app", ...]` | Revisión; build en el VPS (no hay Docker local) | Pendiente |
| 3.3 | `run.bat` → `python -m app.cli`; `.dockerignore` excluye `tests/`, `scripts/`, `reportes/`, `docs/` | Revisión | Pendiente |
| 3.4 | `.gitignore`: agregar `reportes/` y `resultados_*.json` | `git status` no los muestra | Pendiente |
| 3.4b | Limpieza: `git rm Hola.txt`; `git rm --cached api_err.log api_out.log resultados_sunarp.json` (quedan en disco) | Archivos fuera de git y presentes en disco | Pendiente |
| 3.5 | Documentación viva: `CLAUDE.md`, `README.md` (estructura y comandos; quitar Playwright/`db.py` que no existen), `docs/architecture.md`, `docs/roadmap.md`, `docs/modules/estructura-por-procesos.md`, índice `docs/adr/README.md` | `grep` sin nombres viejos | Pendiente |
| 3.6 | Guía corta "dónde va cada cosa" para el equipo (en `CLAUDE.md` y README): nuevo proceso = nueva carpeta en `procesos/` con `scraper/cliente`, `schemas`, `rutas`, `servicio` | Revisión | Pendiente |
| 3.7 | Validación final: contrato, tests, smoke por proceso, `grep` de nombres antiguos | Todo en verde | Pendiente |
| 3.8 | `/code-review` del branch, PR a `main` | Revisión aprobada | Pendiente |
