import time
import httpx
from config import CAPSOLVER_API_KEY


class CaptchaSolver:
    """Solver de CAPTCHAs usando CapSolver API.

    Nota: segun la documentacion oficial de CapSolver, Turnstile (AntiTurnstileTaskProxyLess)
    e ImageToText NO requieren proxy. El proxy solo lo usa el navegador para cargar la pagina,
    no el solver.
    """

    API_URL = "https://api.capsolver.com"

    def __init__(self, api_key: str = None, proxy: str = None):
        self.api_key = api_key or CAPSOLVER_API_KEY
        self.proxy = proxy
        self.client = httpx.Client(timeout=120)

    def solve_image_captcha(self, image_b64: str) -> str:
        """Resuelve un CAPTCHA de imagen (ImageToTextTask) - ProxyLess, retorno directo."""
        if image_b64.startswith("data:image"):
            image_b64 = image_b64.split(",")[1]

        task = {
            "type": "ImageToTextTask",
            "module": "common",
            "body": image_b64,
        }

        payload = {
            "clientKey": self.api_key,
            "task": task,
        }

        print(f"[*] Enviando CAPTCHA a CapSolver ({len(image_b64)} chars)...")
        try:
            resp = self.client.post(f"{self.API_URL}/createTask", json=payload)
        except Exception as e:
            raise Exception(f"Error de red con CapSolver: {e}")

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text}")

        resp_json = resp.json()
        if resp_json.get("errorId") != 0:
            raise Exception(
                f"CapSolver error: {resp_json.get('errorDescription', resp_json)}"
            )

        solution = resp_json.get("solution", {})
        text = solution.get("text", "").strip()
        if not text:
            raise Exception(f"CapSolver no devolvio texto: {resp_json}")
        print(f"[+] CAPTCHA resuelto: '{text}'")
        return text

    def solve_cloudflare_turnstile(self, site_url: str, site_key: str) -> dict:
        """Resuelve Cloudflare Turnstile (AntiTurnstileTaskProxyLess) - retorna {'token': ...}."""
        task = {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": site_url,
            "websiteKey": site_key,
        }
        return self._create_and_wait_task(task, timeout=90)

    def _create_and_wait_task(self, task: dict, timeout: int = 90) -> dict:
        """Crea tarea async (createTask) y espera resultado (getTaskResult)."""
        payload = {"clientKey": self.api_key, "task": task}

        try:
            resp = self.client.post(f"{self.API_URL}/createTask", json=payload)
        except Exception as e:
            raise Exception(f"Error de red con CapSolver: {e}")

        resp_json = resp.json()
        if resp_json.get("errorId") != 0:
            raise Exception(
                f"Error creando tarea: {resp_json.get('errorDescription', resp_json)}"
            )

        task_id = resp_json.get("taskId")
        if not task_id:
            raise Exception(f"CapSolver no devolvio taskId: {resp_json}")
        print(f"[*] Task ID: {task_id}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            try:
                resp = self.client.post(
                    f"{self.API_URL}/getTaskResult",
                    json={"clientKey": self.api_key, "taskId": task_id},
                )
            except Exception as e:
                print(f"[!] Reintentando getTaskResult: {e}")
                continue
            resp_json = resp.json()

            status = resp_json.get("status")
            if status == "ready":
                return resp_json.get("solution", {})
            if status == "failed" or resp_json.get("errorId"):
                raise Exception(
                    f"Tarea fallida: {resp_json.get('errorDescription', resp_json)}"
                )

        raise TimeoutError("Tiempo agotado esperando Turnstile")

    def close(self):
        self.client.close()