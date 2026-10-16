# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FastAPI service ("Api Scrappers IAUTOS") that looks up Peruvian vehicle data by license plate (`placa`) from three official sources, solving captchas via CapSolver. Code, comments, docs and API text are in Spanish. There is no test suite, linter, or build step.

| Source | Module | Technique |
|---|---|---|
| SOAT (apeseg.org.pe) | `scraper.py` → `SOATScraper` | undetected-chromedriver (Selenium) + Turnstile/image captcha |
| CITV / revisión técnica (rec.mtc.gob.pe) | `mtc_scraper.py` → `MTCScraper` | undetected-chromedriver + CapSolver |
| Registro vehicular (consultavehicular.sunarp.gob.pe) | `sunarp_api.py` → `SunarpHTTP` | direct HTTP (httpx) + Turnstile token + Tesseract OCR (~3s) |

`sunarp_scraper.py` is an older Selenium version of Sunarp; the API uses `sunarp_api.py`. (The README still mentions Playwright and a `db.py`/MariaDB; neither exists in the code — Selenium/undetected-chromedriver is what's used.)

## Commands

```bash
pip install -r requirements.txt          # also needs Google Chrome; Tesseract (+ spa data) for Sunarp OCR
cp .env.example .env                     # CAPSOLVER_API_KEY, optional CHROME_VERSION_MAIN

python api.py                            # or: uvicorn api:app --host 0.0.0.0 --port 8000  (docs at /docs, Basic Auth)
python main.py --placa ABC123 [--proxy] [--output file.json]   # CLI for SOAT (--placas A,B,C for several)
python test_soat_proxy.py ABC123 16 4 1  # SOAT stability test: placa, total, parallel workers, use_proxy(1/0); does NOT hit the webhook

docker compose up --build                # needs external network: docker network create proxy-net
```

Deployment notes (Docker + Nginx Proxy Manager on a VPS) are in `VPS_SETUP.md`.

## Architecture

- **`api.py`** — all routes. Each source has the same four entry points: `POST /{soat,mtc,sunarp}` (sync, blocks until result), `POST .../async` (returns immediately), and `GET` shortcuts for both (`vehiculoId` query param is required). Failed lookups return HTTP 200 with `success:false` + `error`; 4xx/5xx are only for bad requests/internal errors. Docs routes (`/docs`, `/redoc`, `/openapi.json`) are behind `BasicAuthMiddleware`. The OpenAPI description/tags are long Spanish strings at the top of the file — update them when adding endpoints.
- **Async mode** (`_run_async_task`, `_run_mtc_async_task`, `_run_sunarp_async_task`): spawns a daemon `threading.Thread` (Selenium is blocking), builds a fresh scraper, runs it, then POSTs the result (with `vehiculoId`) to the IAUTOS webhook via `webhook.send_to_webhook`. SOAT/MTC webhook URLs live in `webhook.py` (`source="mtc"` switches endpoint). The Sunarp async task currently does *not* call the webhook.
- **Sunarp pool**: `SunarpHTTPPool` (size 5, lazily created by `_get_sunarp_pool()`, closed on shutdown) hands out `SunarpHTTP` clients from a queue for the sync endpoint.
- **Browser creation**: every Selenium scraper must create Chrome through `chrome_utils.create_driver()`, which detects the installed Chrome major version (override with `CHROME_VERSION_MAIN`) and retries once using the version parsed from a ChromeDriver mismatch error.
- **Proxy**: `scraper.ProxyForwarder` is a local HTTP CONNECT forwarder that adds auth for the CapSolver residential proxy and sends Chrome noise domains (Google telemetry/updates) direct, so only target-site traffic consumes proxy bandwidth. `SOATScraper` and `MTCScraper` each use a distinct local port (MTC: `LOCAL_PROXY_PORT = 18081`) and rotate through `config.CAPSOLVER_PROXIES`. Concurrent SOAT lookups with proxy were tuned recently (see git log) — keep ports/sessions per-instance.
- **Captcha**: `captcha_solver.CaptchaSolver` wraps the CapSolver API. `solve_turnstile.py` and `capture_headers.py` are standalone helper/debug scripts.
- **Result shape**: scrapers return dicts with `success`, `placa`, data fields, and often a base64 screenshot; recent commits ensure responses without data are not marked `success:true`.

## Gotchas

- Hardcoded secrets exist in the repo (`config.py` proxy credentials, `docker-compose.yml` CapSolver key, `api.py` docs Basic Auth, `proxy.py`). Don't copy them into new files or output; prefer env vars for anything new.
- The `.venv`, `*.log`, `resultados_*.json` and `__pycache__` are local artifacts.
- `run.bat` hardcodes a specific Windows Python path and runs `main.py`.
