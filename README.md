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
3. Editar `.env` con tu API key:
   ```
   CAPSOLVER_API_KEY=CAP-XXXXX-tu-api-key
   ```

## Uso

```bash
# Consultar una placa
python main.py --placa ABC123

# Consultar multiples placas
python main.py --placas ABC123,XYZ789,DEF456

# Guardar en archivo especifico
python main.py --placa ABC123 --output mi_archivo.json
```

## Estructura

```
soat-scraper/
├── main.py              # Entry point CLI
├── scraper.py           # Logica principal del scraper
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
