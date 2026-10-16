import os
from dotenv import load_dotenv

load_dotenv()

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")
BASE_URL = "https://www.apeseg.org.pe/consultas-soat/"
MTC_BASE_URL = "https://rec.mtc.gob.pe"
SUNARP_URL = "https://consultavehicular.sunarp.gob.pe"

CAPSOLVER_PROXIES = [
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_7zPSq3W7KP:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_VsX3yr5SYa:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_NCMKbSuPvI:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_WMV80ODSI5:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_w3coDMMWoF:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_K1acTzFE0l:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_xcc5ePeAU5:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_houshocq2m:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_ANY-rotate_0m-session_bdZDkqU7w7:2O0jDAt2",
]
# Webhook de Sunarp (una sola URL; el body lleva `operacion`). Sin valores por defecto.
WEBHOOK_SUNARP_URL = os.getenv("WEBHOOK_SUNARP_URL", "")
WEBHOOK_SUNARP_TOKEN = os.getenv("WEBHOOK_SUNARP_TOKEN", "")
# Reintentos del INSERT (solo timeout / 5xx). 0 hasta confirmar el UNIQUE (Veh_NumeroPlaca, Veh_EmpId).
WEBHOOK_SUNARP_INSERT_RETRIES = max(0, min(2, int(os.getenv("WEBHOOK_SUNARP_INSERT_RETRIES", "0"))))

# Si es false, el flujo SINCRONO de Sunarp no llama al webhook insertar_vehiculo: devuelve los datos
# extraidos (operacion "datos_vehiculo") sin vehiculoId. WEBHOOK_SUNARP_URL solo hace falta si es true.
SUNARP_WEBHOOK_ENABLED = os.getenv("SUNARP_WEBHOOK_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si")

# Pool de clientes Sunarp compartido por sync y async.
SUNARP_POOL_SIZE = max(1, int(os.getenv("SUNARP_POOL_SIZE", "5")))
# Segundos que un request sync espera un cliente libre antes de responder 503.
SUNARP_SYNC_WAIT_SECONDS = float(os.getenv("SUNARP_SYNC_WAIT_SECONDS", "30"))

# OCR de Sunarp (Tesseract). TESSERACT_CMD vacio = autodeteccion.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
SUNARP_OCR_PREPROCESS = os.getenv("SUNARP_OCR_PREPROCESS", "1").strip().lower() not in ("0", "false", "no", "")
SUNARP_OCR_SCALE = max(1.0, min(4.0, float(os.getenv("SUNARP_OCR_SCALE", "2"))))
SUNARP_OCR_THRESHOLD = max(0, min(255, int(os.getenv("SUNARP_OCR_THRESHOLD", "150"))))
SUNARP_OCR_PSM = os.getenv("SUNARP_OCR_PSM", "auto").strip().lower()
if SUNARP_OCR_PSM not in ("auto", "4", "6"):
    SUNARP_OCR_PSM = "auto"
