import threading

from app.compartido.webhook import send_to_webhook
from app.procesos.mtc.scraper import MTCScraper


def consultar(placa: str, vehiculoId: int, use_proxy: bool) -> dict:
    """Modo sincrono: corre el scraper CITV, devuelve el resultado y lo envia al webhook de IAUTOS."""
    scraper = MTCScraper(use_proxy=use_proxy)
    try:
        scraper.start()
        result = scraper.consultar(placa)
        if not result.get("placa"):
            result["placa"] = placa
        result["vehiculoId"] = vehiculoId
    finally:
        scraper.stop()

    result["webhook"] = send_to_webhook(result, source="mtc")
    return result

def _run_mtc_async_task(placa: str, vehiculoId: int, use_proxy: bool = False):
    """Corre el scraper MTC en un hilo separado y envia al webhook."""
    def _work():
        scraper = MTCScraper(use_proxy=use_proxy)
        try:
            scraper.start()
            result = scraper.consultar(placa)
            if not result.get("placa"):
                result["placa"] = placa
            result["vehiculoId"] = vehiculoId
        except Exception as e:
            result = {"placa": placa, "vehiculoId": vehiculoId, "success": False, "error": str(e)}
        finally:
            scraper.stop()
        result["webhook"] = send_to_webhook(result, source="mtc")
        print(f"[mtc_async] placa={placa} vehiculoId={vehiculoId} success={result.get('success')} webhook={result['webhook']}")

    t = threading.Thread(target=_work, daemon=True)
    t.start()
