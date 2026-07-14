import threading
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from scraper import SOATScraper
from webhook import send_to_webhook

app = FastAPI(
    title="SOAT Scraper API",
    description="Consulta el SOAT de una placa en apeseg.org.pe, resuelve "
                "Cloudflare Turnstile + captcha de imagen via CapSolver y "
                "envia el resultado a un webhook.site.",
    version="1.0.0",
)


class PlacaRequest(BaseModel):
    placa: str
    use_proxy: bool = False


@app.get("/")
def root():
    return {
        "endpoints": {
            "sincrono": "POST /soat  (espera resultado, ~30-40s)",
            "async": "POST /soat/async  (responde 202, corre en background y envia al webhook)",
            "health": "GET /health",
        }
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/soat")
def soat_sync(req: PlacaRequest):
    """Modo sincrono: bloquea hasta tener el resultado del SOAT y lo retorna.
    Tambien envia el resultado al webhook.site.
    """
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")

    scraper = SOATScraper(use_proxy=req.use_proxy)
    scraper.start()
    try:
        result = scraper.consultar_soat(placa)
        if not result.get("placa"):
            result["placa"] = placa
    finally:
        scraper.stop()

    # enviar al webhook en el mismo request (sync)
    result["webhook"] = send_to_webhook(result)
    return result


@app.post("/soat/async")
def soat_async(req: PlacaRequest, bg: BackgroundTasks):
    """Modo asincrono: responde 202 inmediatamente. El scraper corre en una
    tarea en segundo plano; al terminar envia el resultado al webhook.site.
    """
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")

    bg.add_task(_run_async_task, placa, req.use_proxy)
    return {"status": "accepted", "placa": placa, "webhook": "se enviara al terminar"}


@app.get("/soat/{placa}")
def soat_sync_get(placa: str, use_proxy: bool = False):
    """Atajo GET para probar rapido desde el navegador.
    Ej: GET /soat/ABC123
    """
    return soat_sync(PlacaRequest(placa=placa, use_proxy=use_proxy))


def _run_async_task(placa: str, use_proxy: bool):
    """Corre el scraper en un hilo separado (FastAPI BackgroundTasks es async;
    el scraper usa undetected-chromedriver que es bloqueante) y envia al webhook."""
    def _work():
        scraper = SOATScraper(use_proxy=use_proxy)
        scraper.start()
        try:
            result = scraper.consultar_soat(placa)
            if not result.get("placa"):
                result["placa"] = placa
        except Exception as e:
            result = {"placa": placa, "success": False, "error": str(e)}
        finally:
            scraper.stop()
        result["webhook"] = send_to_webhook(result)
        print(f"[async] placa={placa} success={result.get('success')} webhook={result['webhook']}")

    # aislar el Chrome bloqueante en su propio hilo
    t = threading.Thread(target=_work, daemon=True)
    t.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)