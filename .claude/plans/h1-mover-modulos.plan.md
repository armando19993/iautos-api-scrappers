# Plan H1 · Mover y renombrar módulos por proceso

PRD: `.claude/prds/estructura-por-procesos.prd.md` · ADR: `docs/adr/0001-estructura-por-procesos.md`
Estado: **Completado (16/10/2026)**

Objetivo: cada archivo de lógica pasa a su paquete con un nombre que dice qué es. `api.py`
todavía no se parte: solo cambia sus imports.

## Mapa de movimientos (todos con `git mv`)

| Hoy | Después | Contenido |
|---|---|---|
| `config.py` | `app/core/config.py` | Variables de entorno y proxies |
| `captcha_solver.py` | `app/compartido/captcha.py` | `CaptchaSolver` (CapSolver) |
| `chrome_utils.py` | `app/compartido/chrome.py` | `create_driver`, detección de Chrome |
| `scraper.py` → clase `ProxyForwarder` | `app/compartido/proxy_forwarder.py` | Forwarder CONNECT (lo usan SOAT y MTC) |
| `webhook.py` | `app/compartido/webhook.py` | Webhooks SOAT/MTC y Sunarp |
| `scraper.py` → clase `SOATScraper` | `app/procesos/soat/scraper.py` | Scraper SOAT (APESEG) |
| `mtc_scraper.py` | `app/procesos/mtc/scraper.py` | Scraper CITV (MTC) |
| `sunarp_api.py` | `app/procesos/sunarp/cliente_http.py` | `SunarpHTTP` (lo usa la API) |
| `sunarp_ocr.py` | `app/procesos/sunarp/ocr.py` | OCR de la tarjeta |
| `sunarp_parser.py` | `app/procesos/sunarp/parser.py` | Parser del texto OCR |
| `sunarp_scraper.py` | `app/procesos/sunarp/scraper_selenium.py` | Versión Selenium (solo CLI) |

Cada carpeta lleva `__init__.py`. Imports absolutos: `from app.compartido.captcha import CaptchaSolver`.

## Tareas

| # | Tarea | Validación | Estado |
|---|---|---|---|
| 1.1 | Crear paquetes `app/`, `app/core/`, `app/compartido/`, `app/procesos/{soat,mtc,sunarp}/` | `python -c "import app"` | Hecho |
| 1.2 | `git mv` de los módulos 1 a 1 según el mapa | `git status` muestra 10 `renamed` | Hecho |
| 1.3 | Separar `ProxyForwarder` de `scraper.py` a `compartido/proxy_forwarder.py` (copia literal) | 178 líneas movidas literal; SOAT y MTC usan la misma clase | Hecho |
| 1.4 | Actualizar imports en todos los módulos, `api.py`, `main.py` y los tests | compileall OK; 13 módulos importan; `.env` se sigue cargando | Hecho |
| 1.5 | Ajustar los parches de `test_sunarp_ocr.py` (`sunarp_ocr.*` → `app.procesos.sunarp.ocr.*`) | Alias `import app.procesos.sunarp.ocr as sunarp_ocr` / `app.compartido.webhook as webhook`: parches sobre el módulo real; mutante sin parche del pool falla | Hecho |
| 1.6 | Correr test de contrato + 3 tests existentes | Contrato igual; parser 9 · ocr 14 · sync 18 ok | Hecho |
| 1.7 | Commit `refactor: mover modulos a paquetes por proceso` | — | Hecho |

## Fuera de este hito
- Partir `api.py` (H2). Mover scripts/tests/docs (H3).

## Resultado

- 10 módulos movidos con `git mv` (historial conservado) + `ProxyForwarder` separado a
  `app/compartido/proxy_forwarder.py`.
- 36 imports actualizados en `app/`, `api.py`, `main.py`, scripts y tests.
- En `app/procesos/soat/scraper.py` se quitaron `select` y `threading` (solo los usaba
  `ProxyForwarder`). `asyncio` y `struct` ya estaban sin uso antes; se dejan para no mezclar
  limpiezas con el movimiento.
- Pendiente para H3: comentarios/docstrings que todavía nombran los módulos viejos.
