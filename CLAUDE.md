# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FastAPI service ("Api Scrappers IAUTOS") that looks up Peruvian vehicle data by license plate (`placa`) from three official sources, solving captchas via CapSolver. Code, comments, docs and API text are in Spanish. No linter or build step; tests are plain scripts run as modules (see Commands).

The code is organized **by process** (see `docs/adr/0001-estructura-por-procesos.md`):

| Source | Package | Technique |
|---|---|---|
| SOAT (apeseg.org.pe) | `app/procesos/soat/` → `scraper.SOATScraper` | undetected-chromedriver (Selenium) + Turnstile/image captcha |
| CITV / revisión técnica (rec.mtc.gob.pe) | `app/procesos/mtc/` → `scraper.MTCScraper` | undetected-chromedriver + CapSolver |
| Registro vehicular (consultavehicular.sunarp.gob.pe) | `app/procesos/sunarp/` → `cliente_http.SunarpHTTP` | direct HTTP (httpx) + Turnstile token + Tesseract OCR (~3s) |

`app/procesos/sunarp/scraper_selenium.py` is an older Selenium version of Sunarp used only by the CLI; the API uses `cliente_http.py`.

## Commands

```bash
pip install -r requirements.txt          # also needs Google Chrome; Tesseract (+ spa data) for Sunarp OCR
cp .env.example .env                     # CAPSOLVER_API_KEY, Sunarp vars, optional CHROME_VERSION_MAIN

uvicorn app.main:app --host 0.0.0.0 --port 8000   # docs at /docs (Basic Auth). `uvicorn api:app` still works (compat shim)
python -m app.cli --placa ABC123 [--proxy] [--mtc|--sunarp] [--output file.json]   # CLI (--placas A,B,C for several)

python -m tests.contrato.test_openapi              # API contract vs tests/contrato/openapi.snapshot.json (--actualizar to regenerate)
python -m tests.unitarios.test_sunarp_parser
python -m tests.unitarios.test_sunarp_ocr
python -m tests.integracion.test_sunarp_sync
python -m tests.carga.test_soat_proxy ABC123 16 4 1     # real SOAT lookups: placa, total, workers, use_proxy(1/0); no webhook
python -m tests.carga.test_sunarp --total 30            # real Sunarp lookups + live HTML report in reportes/; no webhook

docker compose up --build                # needs external network: docker network create proxy-net
```

Run everything from the repo root. Deployment notes (Docker + Nginx Proxy Manager on a VPS) are in `docs/despliegue-vps.md`.

## Architecture

```
app/main.py            FastAPI app: CORS + BasicAuthMiddleware, custom OpenAPI, include_router per process, shutdown
app/cli.py             CLI
app/core/              config.py (.env), openapi.py (description/tags/x-logo), seguridad.py (Basic Auth for docs),
                       schemas.py (shared models + RESP_* blocks), rutas.py (/ and /health)
app/compartido/        captcha.py, chrome.py, proxy_forwarder.py, webhook.py
app/procesos/<p>/      scraper (or cliente_http), schemas.py, rutas.py (APIRouter), servicio.py
api.py                 compat shim: from app.main import app
```

Rules: a process never imports from another process (shared code goes to `app/compartido/`); routes only validate and delegate to `servicio.py`; `include_router` order in `app/main.py` is the order of the OpenAPI/docs.

- **Contract test**: `tests/contrato/test_openapi.py` compares the generated OpenAPI and the effective route table (in order) against a snapshot and checks docs are behind Basic Auth. Any intentional API change must regenerate the snapshot so the diff shows in the PR. FastAPI is unpinned; since 0.14x `include_router` stores `_IncludedRouter` entries in `app.routes`, which the test flattens.
- **Endpoints**: each source has the same four entry points: `POST /{soat,mtc,sunarp}` (sync, blocks until result), `POST .../async` (returns immediately), and `GET` shortcuts for both. Failed lookups return HTTP 200 with `success:false` + `error`; 4xx/5xx are only for bad requests/internal errors. Route docstrings are published as OpenAPI descriptions. The OpenAPI description/tags live in `app/core/openapi.py` — update them when adding endpoints.
- **Async mode** (`servicio._run_async_task`, `_run_mtc_async_task`, `_run_sunarp_async_task`): spawns a daemon `threading.Thread` (Selenium is blocking), builds a fresh scraper, runs it, then POSTs the result (with `vehiculoId`) to the IAUTOS webhook via `app.compartido.webhook.send_to_webhook`. SOAT/MTC webhook URLs live in `app/compartido/webhook.py` (`source="mtc"` switches endpoint).
- **Sunarp flow** (`app/procesos/sunarp/servicio.py`): endpoints take `placa` and `empresaId` (no `vehiculoId`). **Sync** (`consultar_sincrono`) with `SUNARP_WEBHOOK_ENABLED=false` (default; the receiver endpoint doesn't exist yet) uses `_consultar_sunarp_datos`: no webhook call, no `vehiculoId`; the response adds `operacion:"datos_vehiculo"`, `empresaId` and `vehiculo` (`Veh_*` without `Veh_EmpId`), `success:true` only if marca and modelo were parsed, else `success:false` with `operacion`/`vehiculo` null. With the flag `true`, and always for **async**, `_procesar_sunarp` runs as follows (async ignores the flag, so with no `WEBHOOK_SUNARP_URL` it only logs `ERROR insert`). It runs the scrape/OCR, parses `ocr_text` with `parser.parse_ocr_text`, (OCR lives in `ocr.py`: grayscale/upscale/threshold preprocessing, picks the better of psm 6 vs 4, falls back to the raw image; knobs `TESSERACT_CMD`, `SUNARP_OCR_*`; failures are distinguished as Tesseract not installed / OCR vacío / texto sin datos de vehículo), then sends `insertar_vehiculo` via `send_sunarp_webhook` (single URL `WEBHOOK_SUNARP_URL`, `operacion` field, optional Bearer token, retries on timeout/5xx via `WEBHOOK_SUNARP_INSERT_RETRIES`). `vehiculoId` in the response = `Veh_Id` returned by the receiver; if the insert fails → `success:false`, `vehiculoId:null`, scrape data kept. Async returns only `{status, placa}`. Tests patch flags/dependencies on `app.procesos.sunarp.servicio`, so read them there at call time.
- **Sunarp pool** (`app/procesos/sunarp/pool.py`): `SunarpHTTPPool` (`SUNARP_POOL_SIZE`, default 5; lazily created by `_get_sunarp_pool()`, closed on shutdown via `cerrar_pool()`) is shared by sync and async. Async jobs wait for a free client; sync waits `SUNARP_SYNC_WAIT_SECONDS` then returns 503.
- **Browser creation**: every Selenium scraper must create Chrome through `app.compartido.chrome.create_driver()`, which detects the installed Chrome major version (override with `CHROME_VERSION_MAIN`), retries once using the version parsed from a ChromeDriver mismatch error, and serializes `uc.Chrome` startup with a lock (concurrent patching of the cached chromedriver fails on Windows).
- **Proxy**: `app.compartido.proxy_forwarder.ProxyForwarder` is a local HTTP CONNECT forwarder that adds auth for the CapSolver residential proxy and sends Chrome noise domains (Google telemetry/updates) direct, so only target-site traffic consumes proxy bandwidth. SOAT uses an ephemeral local port and `config.CAPSOLVER_PROXIES` (`country_ANY`); MTC uses `LOCAL_PROXY_PORT = 18081` and `config.CAPSOLVER_PROXIES_MTC` (same sessions with `country_PE`: the MTC hides its captcha from foreign IPs). Keep ports/sessions per-instance.
- **Captcha**: `app.compartido.captcha.CaptchaSolver` wraps the CapSolver API. `scripts/` holds standalone helper/debug tools (`resolver_turnstile.py`, `capturar_headers.py`, `probar_proxy.py`, `probar_ocr.py`, `mock_webhook.py`).
- **Result shape**: scrapers return dicts with `success`, `placa`, data fields, and often a base64 screenshot; responses without data must not be marked `success:true`.

## Gotchas

- Hardcoded secrets exist in the repo (`app/core/config.py` proxy credentials, `docker-compose.yml` CapSolver key, `app/core/seguridad.py` docs Basic Auth, `scripts/probar_proxy.py`). Don't copy them into new files or output; prefer env vars for anything new.
- The `.venv`, `*.log`, `resultados_*.json`, `reportes/` and `__pycache__` are local artifacts.
- `run.bat` hardcodes a specific Windows Python path and runs `python -m app.cli`.
- Planning docs live in `.claude/prds/` and `.claude/plans/`; architecture decisions in `docs/adr/`.
