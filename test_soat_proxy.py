"""Prueba de estabilidad SOAT + proxy. Usa SOATScraper directamente (NO envia al webhook).

Uso: python test_soat_proxy.py [placa] [total] [paralelo] [use_proxy 1/0]
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from scraper import SOATScraper

PLACA = sys.argv[1] if len(sys.argv) > 1 else "ABC123"
TOTAL = int(sys.argv[2]) if len(sys.argv) > 2 else 16
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 4
USE_PROXY = (sys.argv[4] != "0") if len(sys.argv) > 4 else True


def run(i):
    t = time.time()
    s = SOATScraper(use_proxy=USE_PROXY, headless=True)
    try:
        s.start()
        r = s.consultar_soat(PLACA)
        ok = bool(r.get("success"))
        detail = (r.get("estado") or (r.get("soat") or {}).get("Estado")
                  or str(r.get("error"))[:80])
    except Exception as e:
        ok, detail = False, f"EXC {str(e)[:100]}"
    finally:
        s.stop()
    dt = time.time() - t
    print(f"### PRUEBA {i:02d}: {'OK' if ok else 'FALLO'} | {dt:.0f}s | {detail}", flush=True)
    return ok, dt


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = list(ex.map(run, range(1, TOTAL + 1)))
    oks = sum(1 for o, _ in res if o)
    print(f"### RESUMEN: {oks}/{TOTAL} OK | promedio {sum(d for _, d in res)/len(res):.0f}s", flush=True)
