import httpx

WEBHOOK_URL = "https://api-next.iautos.pe/api/v1/soat/webhook"


def send_to_webhook(payload: dict) -> dict:
    """Envia el payload al endpoint api-next via POST y retorna su respuesta."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(WEBHOOK_URL, json=payload)
            try:
                return resp.json()
            except Exception:
                return {"status": resp.status_code, "body": resp.text[:1000]}
    except Exception as e:
        return {"webhook_error": str(e)}