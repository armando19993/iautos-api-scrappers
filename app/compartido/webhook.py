import time

import httpx

from app.core.config import WEBHOOK_SUNARP_URL, WEBHOOK_SUNARP_TOKEN

WEBHOOK_SOAT_URL = "https://api-next.iautos.pe/api/v1/soat/webhook"
WEBHOOK_MTC_URL = "https://api-next.iautos.pe/api/v1/revision-tecnica/webhook"


def send_to_webhook(payload: dict, source: str = "soat") -> dict:
    """Envia el payload al endpoint api-next via POST y retorna su respuesta."""
    url = WEBHOOK_MTC_URL if source == "mtc" else WEBHOOK_SOAT_URL
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            try:
                return resp.json()
            except Exception:
                return {"status": resp.status_code, "body": resp.text[:1000]}
    except Exception as e:
        return {"webhook_error": str(e)}


def send_sunarp_webhook(payload: dict, retries: int = 0) -> dict:
    """Envia un payload de Sunarp (con campo `operacion`) al WEBHOOK_SUNARP_URL.

    Mismo patron que send_to_webhook (httpx.Client, timeout=30, nunca lanza: los
    errores de red vuelven como {"webhook_error": ...}). Diferencias: URL/token por
    entorno y reintentos (hasta `retries`, con backoff corto) SOLO ante timeout o 5xx.
    """
    if not WEBHOOK_SUNARP_URL:
        return {"webhook_error": "WEBHOOK_SUNARP_URL no configurada"}
    headers = {"Authorization": f"Bearer {WEBHOOK_SUNARP_TOKEN}"} if WEBHOOK_SUNARP_TOKEN else {}
    last = {"webhook_error": "sin intentos"}
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(0.5 * attempt)
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(WEBHOOK_SUNARP_URL, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            last = {"webhook_error": f"timeout: {e}"}
            continue
        except Exception as e:
            return {"webhook_error": str(e)}
        try:
            body = resp.json()
        except Exception:
            body = None
        if resp.status_code >= 500:
            last = body if isinstance(body, dict) else {"webhook_error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
            continue
        if isinstance(body, dict):
            return body
        return {"webhook_error": f"HTTP {resp.status_code}: respuesta no JSON: {resp.text[:300]}"}
    return last
