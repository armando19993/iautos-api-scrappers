# SOAT Scraper - APESEG

Scraper para consultar SOAT en apeseg.org.pe con resolucion automatica de CAPTCHAs.

## Tecnologias

- **Playwright** - Navegador real (mas rapido que Selenium)
- **CapSolver API** - Resolucion de CAPTCHAs con IA
- **Python 3.10+**

## CAPTCHAs Soportados

1. **Image CAPTCHA** - Texto distorsionado
2. **Cloudflare Turnstile** - Widget de verificacion
3. **Cloudflare Challenge** - Challenge completo

## Instalacion

```bash
cd soat-scraper
pip install -r requirements.txt
playwright install chromium
```

## Configuracion

1. Registrarse en [CapSolver](https://www.capsolver.com) y obtener API key
2. Crear archivo `.env` desde el ejemplo:
   ```bash
   copy .env.example .env
   ```
3. Editar `.env` con tu API key y datos de MariaDB:
   ```
   CAPSOLVER_API_KEY=CAP-XXXXX-tu-api-key
   MARIADB_HOST=localhost
   MARIADB_PORT=3306
   MARIADB_USER=root
   MARIADB_PASSWORD=tu_password
   MARIADB_DATABASE=soat
   ```
4. La API crea la tabla `soat_consultas` automaticamente al arrancar
   (ver `db.py` para el esquema completo).

## Uso

### CLI

```bash
# Consultar una placa (sin proxy, usa tu IP local)
python main.py --placa ABC123

# Consultar multiples placas
python main.py --placas ABC123,XYZ789,DEF456

# Guardar en archivo especifico
python main.py --placa ABC123 --output mi_archivo.json

# Usar proxy residencial CapSolver (solo si tu IP es bloqueada por Cloudflare)
python main.py --placa ABC123 --proxy
```

### API (FastAPI)

```bash
# Iniciar el servidor
python api.py
# o: uvicorn api:app --host 0.0.0.0 --port 8000
```

Endpoints disponibles:

| Metodo | Ruta                | Descripcion                                            |
|--------|---------------------|--------------------------------------------------------|
| GET    | `/`                 | Lista de endpoints                                     |
| GET    | `/health`           | Estado del servicio                                    |
| POST   | `/soat`             | Modo sincrono (espera ~30-40s y retorna el SOAT)       |
| POST   | `/soat/async`       | Modo async (202 inmediato, corre en background)       |
| GET    | `/soat/{placa}`     | Atajo sync desde el navegador                          |

**POST /soat** (sincrono):
```bash
curl -X POST http://localhost:8000/soat \
  -H "Content-Type: application/json" \
  -d "{\"placa\":\"ABC123\"}"
```

**POST /soat/async** (background):
```bash
curl -X POST http://localhost:8000/soat/async \
  -H "Content-Type: application/json" \
  -d "{\"placa\":\"ABC123\"}"
```

Body:
- `placa` (str, requerido): placa del vehiculo
- `use_proxy` (bool, opcional, default false): usar proxy residencial CapSolver

Ambos modos envian el resultado al webhook.site configurado en `webhook.py`.

Docs interactivas: http://localhost:8000/docs

## Estructura

```
soat-scraper/
├── main.py              # Entry point CLI
├── scraper.py           # Logica principal del scraper
├── chrome_utils.py      # Deteccion de version de Chrome + creacion del driver
├── captcha_solver.py    # Solver via CapSolver
├── config.py            # Configuracion
├── requirements.txt     # Dependencias
├── .env.example         # Ejemplo de configuracion
└── README.md
```

## CapSolver API - Precios

| Tipo                 | Velocidad   |
|----------------------|-------------|
| Image CAPTCHA        | < 1 seg     |
| Cloudflare Turnstile | < 20 seg    |
| Cloudflare Challenge | < 20 seg    |

- [Dashboard de CapSolver](https://www.capsolver.com)

## Notas

- El scraper abre un navegador real (no headless) para pasar verificaciones anti-bot
- Cloudflare Turnstile se resuelve automaticamente sin proxy
- Cloudflare Challenge requiere proxy (configurar en `.env`)
- Si falla, esperar unos segundos y reintentar

## Solucion de problemas

### `SessionNotCreatedException: This version of ChromeDriver only supports Chrome version X`

El ChromeDriver que descarga `undetected-chromedriver` debe coincidir con la
version mayor del Chrome instalado. Todos los scrapers crean el navegador con
`chrome_utils.create_driver()`, que:

1. Detecta la version instalada (Windows: metadatos de `chrome.exe`, carpeta de
   instalacion o registro; Linux/macOS: `google-chrome --version`).
2. Si aun asi el driver no coincide (por ejemplo Chrome se acaba de actualizar),
   lee la version real del mensaje de error y reintenta con ella.

Si necesitas forzar una version concreta (o la deteccion falla en tu entorno),
define la variable de entorno `CHROME_VERSION_MAIN` (tambien vale en `.env`):

```
CHROME_VERSION_MAIN=152
```
