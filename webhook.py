import httpx

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
