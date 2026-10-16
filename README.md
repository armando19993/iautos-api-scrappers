# Api Scrappers IAUTOS

API (FastAPI) que consulta información oficial de vehículos en el Perú a partir de la placa.
Los captchas se resuelven con [CapSolver](https://www.capsolver.com).

| Proceso | Fuente | Técnica | Endpoint | Tiempo aprox. |
|---|---|---|---|---|
| SOAT | APESEG (apeseg.org.pe) | Chrome (undetected-chromedriver) + Turnstile + captcha de imagen | `POST /soat` | 30–40 s |
| MTC (CITV) | rec.mtc.gob.pe | Chrome + CapSolver | `POST /mtc` | 10–40 s |
| Sunarp | consultavehicular.sunarp.gob.pe | HTTP directo + Turnstile + OCR (Tesseract) | `POST /sunarp` | ~3 s |

## Requisitos

- Python 3.11+
- Google Chrome
- Tesseract OCR con datos en español (solo Sunarp)
- API key de CapSolver

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env     # completar CAPSOLVER_API_KEY y las variables de Sunarp
```

Las variables disponibles están documentadas en `.env.example`.

## Ejecutar la API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Documentación interactiva: `/docs` y `/redoc` (protegidas con Basic Auth).
- `uvicorn api:app` sigue funcionando por compatibilidad (ver [ADR 0001](docs/adr/0001-estructura-por-procesos.md)).

### Endpoints

Cada proceso tiene los mismos cuatro puntos de entrada:

| Método | Ruta | Modo |
|---|---|---|
| POST | `/{soat,mtc,sunarp}` | Síncrono: espera y devuelve el resultado |
| POST | `/{soat,mtc,sunarp}/async` | Asíncrono: responde de inmediato y procesa en segundo plano |
| GET | `/{soat,mtc,sunarp}/async` | Asíncrono vía query params |
| GET | `/{soat,mtc,sunarp}/{placa}` | Atajo síncrono para pruebas |

Además: `GET /` (índice) y `GET /health`.

- SOAT y MTC reciben `placa` y `vehiculoId`, y envían el resultado al webhook de IAUTOS.
- Sunarp recibe `placa` y `empresaId`.
- Una consulta fallida responde **HTTP 200 con `success:false`** y el motivo en `error`; los
  códigos 4xx/5xx son para peticiones inválidas o errores internos.

## CLI

```bash
python -m app.cli --placa ABC123                 # SOAT
python -m app.cli --placas ABC123,XYZ789         # varias placas
python -m app.cli --placa ABC123 --mtc           # MTC CITV
python -m app.cli --placa ABC123 --sunarp        # Sunarp (Selenium + OCR)
python -m app.cli --placa ABC123 --proxy --output resultado.json
```

En Windows también: `run.bat --placa ABC123`.

## Tests

Se ejecutan desde la raíz del repo:

```bash
python -m tests.contrato.test_openapi              # el contrato de la API no cambió
python -m tests.unitarios.test_sunarp_parser
python -m tests.unitarios.test_sunarp_ocr
python -m tests.integracion.test_sunarp_sync
```

- **Contrato**: compara el OpenAPI y las rutas contra `tests/contrato/openapi.snapshot.json`.
  Si cambias la API a propósito, regenera el snapshot con
  `python -m tests.contrato.test_openapi --actualizar` y deja el diff visible en el PR.
- **Carga** (`tests/carga/`): consultas reales contra los sitios oficiales; gastan saldo de
  CapSolver y tráfico de proxy. No envían nada al webhook.
  ```bash
  python -m tests.carga.test_soat_proxy ABC123 20 4 1
  python -m tests.carga.test_sunarp --total 30 --workers 5
  ```

## Estructura

```
app/
├── main.py              # crea la app FastAPI: middlewares, OpenAPI y routers
├── cli.py               # consultas desde la terminal
├── core/                # config (.env), OpenAPI, Basic Auth de /docs, schemas y rutas comunes
├── compartido/          # captcha (CapSolver), chrome, proxy_forwarder, webhook
└── procesos/
    ├── soat/            # scraper · schemas · rutas · servicio
    ├── mtc/             # scraper · schemas · rutas · servicio
    └── sunarp/          # cliente_http · pool · ocr · parser · scraper_selenium · schemas · rutas · servicio
scripts/                 # herramientas manuales (probar proxy, OCR, mock del webhook...)
tests/                   # contrato · unitarios · integracion · carga
docs/                    # arquitectura, roadmap, ADRs, módulos, despliegue
api.py                   # compatibilidad: uvicorn api:app
```

### Dónde va cada cosa

| Quiero… | Archivo |
|---|---|
| Cambiar cómo se scrapea un sitio | `app/procesos/<proceso>/scraper.py` (Sunarp: `cliente_http.py`) |
| Cambiar qué hace un endpoint con el resultado (webhook, validaciones, async) | `app/procesos/<proceso>/servicio.py` |
| Agregar o cambiar un endpoint | `app/procesos/<proceso>/rutas.py` + `schemas.py` (y regenerar el snapshot del contrato) |
| Algo que usan varios procesos (captcha, Chrome, proxy, webhook) | `app/compartido/` |
| Una variable de entorno | `app/core/config.py` + `.env.example` |
| Un proceso nuevo | carpeta nueva en `app/procesos/` con `scraper`, `schemas`, `rutas`, `servicio`, y su `include_router` en `app/main.py` |

Reglas: un proceso no importa nada de otro proceso; las rutas solo validan y delegan en
`servicio.py`.

## Despliegue

Docker + Nginx Proxy Manager en un VPS: [docs/despliegue-vps.md](docs/despliegue-vps.md).

## Solución de problemas

### `SessionNotCreatedException: This version of ChromeDriver only supports Chrome version X`

El ChromeDriver que descarga `undetected-chromedriver` debe coincidir con la versión mayor
del Chrome instalado. Todos los scrapers crean el navegador con
`app.compartido.chrome.create_driver()`, que:

1. Detecta la versión instalada (Windows: metadatos de `chrome.exe`, carpeta de instalación
   o registro; Linux/macOS: `google-chrome --version`).
2. Si aun así el driver no coincide (por ejemplo, Chrome se acaba de actualizar), lee la
   versión real del mensaje de error y reintenta con ella.

Para forzar una versión concreta, define `CHROME_VERSION_MAIN` (también vale en `.env`):

```
CHROME_VERSION_MAIN=152
```

### Sunarp responde "Tesseract no instalado"

Instala Tesseract con el paquete de idioma español, o indica la ruta del ejecutable en
`TESSERACT_CMD`.

## Documentación

- [Arquitectura](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Decisiones de arquitectura (ADR)](docs/adr/README.md)
