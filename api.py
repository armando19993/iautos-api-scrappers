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


class SoatRequest(BaseModel):
    placa: str
    vehiculoId: int
    use_proxy: bool = False
    headless: bool = True


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
def soat_sync(req: SoatRequest):
    """Modo sincrono: bloquea hasta tener el resultado del SOAT y lo retorna.
    Tambien envia el resultado al webhook.site.
    """
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")

    scraper = SOATScraper(use_proxy=req.use_proxy, headless=req.headless)
    scraper.start()
    try:
        result = scraper.consultar_soat(placa)
        if not result.get("placa"):
            result["placa"] = placa
        result["vehiculoId"] = req.vehiculoId
    finally:
        scraper.stop()

    result["webhook"] = send_to_webhook(result)
    return result


@app.post("/soat/async")
def soat_async(req: SoatRequest, bg: BackgroundTasks):
    """Modo asincrono: responde 202 inmediatamente. El scraper corre en una
    tarea en segundo plano; al terminar envia el resultado al webhook.site.
    """
    placa = req.placa.strip().upper()
    if not placa:
        raise HTTPException(status_code=400, detail="placa requerida")

    bg.add_task(_run_async_task, placa, req.vehiculoId, req.use_proxy, req.headless)
    return {"status": "accepted", "placa": placa, "vehiculoId": req.vehiculoId, "webhook": "se enviara al terminar"}


@app.get("/soat/{placa}")
def soat_sync_get(placa: str, vehiculoId: int, use_proxy: bool = False, headless: bool = True):
    """Atajo GET para probar rapido desde el navegador.
    Ej: GET /soat/ABC123?vehiculoId=42
    """
    return soat_sync(SoatRequest(placa=placa, vehiculoId=vehiculoId, use_proxy=use_proxy, headless=headless))


def _run_async_task(placa: str, vehiculoId: int, use_proxy: bool, headless: bool = True):
    """Corre el scraper en un hilo separado (FastAPI BackgroundTasks es async;
    el scraper usa undetected-chromedriver que es bloqueante) y envia al webhook."""
    def _work():
        scraper = SOATScraper(use_proxy=use_proxy, headless=headless)
        scraper.start()
        try:
            result = scraper.consultar_soat(placa)
            if not result.get("placa"):
                result["placa"] = placa
            result["vehiculoId"] = vehiculoId
        except Exception as e:
            result = {"placa": placa, "vehiculoId": vehiculoId, "success": False, "error": str(e)}
        finally:
            scraper.stop()
        result["webhook"] = send_to_webhook(result)
        print(f"[async] placa={placa} vehiculoId={vehiculoId} success={result.get('success')} webhook={result['webhook']}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)