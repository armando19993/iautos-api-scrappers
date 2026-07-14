import httpx

WEBHOOK_URL = "https://webhook.site/6c469eb8-dc75-442f-81f2-65af79b066cd"


def send_to_webhook(payload: dict) -> dict:
    """Envia el payload (ya con placa/resultado) al endpoint webhook.site via POST.
    Retorna la respuesta del webhook (dict con status/body) o un dict con error.
    """
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(WEBHOOK_URL, json=payload)
            return {
                "webhook_status": resp.status_code,
                "webhook_response": resp.text[:500],
            }
    except Exception as e:
        return {"webhook_error": str(e)}