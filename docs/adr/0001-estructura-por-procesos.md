# ADR 0001 · Estructura del proyecto por procesos

- Estado: **Aceptado** (16/10/2026)
- Fecha: 16/10/2026
- Autor: Armando Campos

## Contexto

El servicio consulta tres fuentes (SOAT/APESEG, CITV/MTC, Sunarp). Todo el código está en la
raíz con nombres ambiguos (`scraper.py` = SOAT) y `api.py` concentra rutas, modelos, tareas
async, pool y documentación de las tres fuentes. Se suma más gente al proyecto y cualquier
cambio en un proceso obliga a tocar el mismo archivo que los demás.

## Decisión

Organizar el código en un paquete `app/` por **proceso** (vertical) y, dentro, por
**responsabilidad**:

```
app/
├── main.py                 # arma la app FastAPI
├── cli.py                  # consultas desde terminal
├── core/                   # config, OpenAPI, seguridad de /docs, schemas y rutas generales
├── compartido/             # captcha, chrome, proxy_forwarder, webhook
└── procesos/
    ├── soat/               # scraper, schemas, rutas, servicio
    ├── mtc/                # scraper, schemas, rutas, servicio
    └── sunarp/             # cliente_http, pool, ocr, parser, scraper_selenium, schemas, rutas, servicio
scripts/                    # utilidades manuales (probar proxy, mock webhook, OCR...)
tests/
├── contrato/               # snapshot del OpenAPI
├── unitarios/
├── integracion/
└── carga/                  # pruebas contra servicios reales
docs/                       # arquitectura, roadmap, ADRs, módulos, despliegue
```

Reglas:
- Un proceso no importa nada de otro proceso; lo común va a `compartido/`.
- Las rutas solo validan y delegan en `servicio.py`.
- El contrato de la API se congela en `tests/contrato/openapi.snapshot.json`.
- Los nombres de carpetas siguen las rutas de la API (`soat`, `mtc`, `sunarp`) para que sea
  obvio qué carpeta atiende qué endpoint.
- Se conserva un `api.py` en la raíz (`from app.main import app`) para no romper
  `uvicorn api:app` mientras se migran los comandos de arranque.

## Alternativas consideradas

- **Por capa** (`routers/`, `scrapers/`, `models/`): un cambio de SOAT seguiría tocando tres
  carpetas compartidas con los otros procesos. Descartada.
- **Solo renombrar archivos en la raíz**: barato, pero `api.py` seguiría siendo el punto de
  choque. Descartada.

## Consecuencias

- (+) Cada persona trabaja en la carpeta de su proceso; menos conflictos de merge.
- (+) El test de contrato detecta cambios accidentales en la API.
- (−) Cambia el comando de arranque (`app.main:app`) y las rutas de los tests y scripts.
- (−) Ramas abiertas antes del refactor tendrán conflictos al rebasar.
