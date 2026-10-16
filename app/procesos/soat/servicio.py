import threading

from app.compartido.webhook import send_to_webhook
from app.procesos.soat.scraper import SOATScraper


def consultar(placa: str, vehiculoId: int, use_proxy: bool, headless: bool) -> dict:
    """Modo sincrono: corre el scraper, devuelve el resultado y lo envia al webhook de IAUTOS."""
    scraper = SOATScraper(use_proxy=use_proxy, headless=headless)
    try:
        scraper.start()
        result = scraper.consultar_soat(placa)
        if not result.get("placa"):
            result["placa"] = placa
        result["vehiculoId"] = vehiculoId
    finally:
        scraper.stop()

    result["webhook"] = send_to_webhook(result)
    return result

def _run_async_task(placa: str, vehiculoId: int, use_proxy: bool, headless: bool = True):
    """Corre el scraper en un hilo separado (FastAPI BackgroundTasks es async;
    el scraper usa undetected-chromedriver que es bloqueante) y envia al webhook."""
    def _work():
        scraper = SOATScraper(use_proxy=use_proxy, headless=headless)
        try:
            scraper.start()
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
