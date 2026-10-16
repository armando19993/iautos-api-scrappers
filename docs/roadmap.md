# Roadmap

Última actualización: 16/10/2026 · Redactado por: Armando Campos

## Hecho

| Fecha | Qué | Referencia |
|---|---|---|
| 16/10/2026 | Estructura del proyecto por procesos (H0–H3) | `.claude/prds/estructura-por-procesos.prd.md`, ADR 0001 |
| 16/10/2026 | MTC con proxy de Perú (regresión de `country_ANY`) | PR #5 `hotfix/mtc-proxy-peru` |
| 14/10/2026 | SOAT: canal de proxy nuevo, lock de arranque de Chrome, sin falsos positivos | commits `5d89ff6`, `d93bb9f` |

## Pendiente (sin priorizar)

| Tema | Detalle | Origen |
|---|---|---|
| Sunarp: falso positivo con placa inexistente | `SunarpHTTP` devuelve `success:true` cuando Sunarp responde `cod: 0` ("No se ha encontrado la placa") | Prueba de 30 consultas (15/10/2026) |
| Sunarp: reintentos de red | Un corte de red falla al instante o deja un cliente del pool colgado ~350 s | Prueba de 30 consultas |
| MTC: 500 ante corte del proxy | `ERR_TUNNEL_CONNECTION_FAILED` en `driver.get` no se captura y la ruta responde 500 | Smoke del refactor |
| Secretos a variables de entorno | Credenciales del proxy (`app/core/config.py`), API key en `docker-compose.yml`, Basic Auth de `/docs` | H4 (fuera de alcance del refactor) |
| CI en GitHub Actions | Correr contrato + unitarios + integración en cada PR | H4 |
| Fijar versiones en `requirements.txt` | FastAPI sin versión; 0.143 cambió la forma de `app.routes` | Refactor H2 |
| Retirar el shim `api.py` | Cuando el VPS y los scripts usen `app.main:app` | ADR 0001 |
| Limpieza menor | Imports sin uso en los scrapers; `.env.example` lista variables MariaDB que el código no usa; `scripts/probar_proxy.py` tiene credenciales del canal viejo | Refactor H1/H3 |
