import queue
import threading
from typing import Optional

from app.core.config import SUNARP_POOL_SIZE
from app.procesos.sunarp.cliente_http import SunarpHTTP

class SunarpHTTPPool:
    """Pool thread-safe de clientes HTTP para Sunarp (sin Selenium). ~3s por consulta."""

    def __init__(self, size=5):
        self._queue: queue.Queue[SunarpHTTP] = queue.Queue(maxsize=size)
        self.size = size
        self._clients = []

    def start(self):
        print(f"[SunarpPool] Iniciando {self.size} clientes HTTP...")
        for i in range(self.size):
            c = SunarpHTTP()
            self._clients.append(c)
            self._queue.put(c)
        print(f"[SunarpPool] Pool listo: {self.size} clientes disponibles")

    def acquire(self, timeout: Optional[float] = 30) -> SunarpHTTP:
        """timeout=None espera indefinidamente (jobs async: se encolan)."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"No hay cliente disponible tras {timeout}s "
                f"({self._queue.qsize()}/{self.size} libres)"
            )

    def release(self, client: SunarpHTTP):
        self._queue.put(client)

    def consultar(self, placa: str, timeout: Optional[float] = 30) -> dict:
        client = self.acquire(timeout)
        try:
            return client.consultar(placa)
        finally:
            self.release(client)

    def stop(self):
        for c in self._clients:
            try:
                c.close()
            except Exception:
                pass


# ── Instancia global del pool ──
_sunarp_pool: SunarpHTTPPool | None = None
_sunarp_pool_lock = threading.Lock()


def _get_sunarp_pool() -> SunarpHTTPPool:
    global _sunarp_pool
    with _sunarp_pool_lock:
        if _sunarp_pool is None:
            pool = SunarpHTTPPool(size=SUNARP_POOL_SIZE)
            pool.start()
            _sunarp_pool = pool
    return _sunarp_pool


def cerrar_pool():
    global _sunarp_pool
    if _sunarp_pool:
        print("[api] Cerrando pool HTTP Sunarp...")
        _sunarp_pool.stop()
        _sunarp_pool = None
