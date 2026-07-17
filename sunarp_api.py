import time
import base64
import io

import httpx
from PIL import Image
import pytesseract

from config import CAPSOLVER_API_KEY, SUNARP_URL
from captcha_solver import CaptchaSolver

# ── Configurar Tesseract para Windows ──
import os
for _p in [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]:
    if os.path.exists(_p):
        pytesseract.pytesseract.tesseract_cmd = _p
        break

_user_tessdata = os.path.expanduser(r"~\.tesseract\tessdata")
if os.path.exists(_user_tessdata):
    os.environ["TESSDATA_PREFIX"] = _user_tessdata

# ── Endpoints y constantes ──
API_URL = "https://api-gateway.sunarp.gob.pe:9443/sunarp/multiservicios/multiservicio-consvehicular/consulta/getDatosVehiculo"
TURNSTILE_SITE_KEY = "0x4AAAAAACFzt4Xn8T1Jg9ZS"
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://consultavehicular.sunarp.gob.pe",
    "Referer": "https://consultavehicular.sunarp.gob.pe/consulta-vehicular",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-IBM-Client-Id": "70574c7d9194834316a156b1d68fdb90",
}


class SunarpHTTP:
    """Consulta Sunarp via HTTP directo (sin Selenium). ~2-3s por consulta."""

    def __init__(self):
        self.solver = CaptchaSolver(CAPSOLVER_API_KEY, None)
        self.client = httpx.Client(timeout=30, verify=False, follow_redirects=True)

    def consultar(self, placa: str) -> dict:
        placa = placa.strip().upper()
        t_start = time.time()

        try:
            # 1. Obtener token Turnstile via CapSolver
            print(f"[SunarpHTTP] Resolviendo Turnstile...")
            solution = self.solver.solve_cloudflare_turnstile(SUNARP_URL, TURNSTILE_SITE_KEY)
            token = solution.get("token", "")
            if not token:
                raise Exception(f"CapSolver no devolvió token: {solution}")
            print(f"[SunarpHTTP] Token obtenido ({len(token)} chars)")

            # 2. Hacer la consulta directa
            print(f"[SunarpHTTP] Consultando API para placa {placa}...")
            payload = {
                "numPlaca": placa,
                "regPubId": None,
                "oficRegId": None,
                "ipAddress": "200.48.77.6",
                "appVersion": "1.0",
                "dG9rZW4": token,
            }
            resp = self.client.post(API_URL, json=payload, headers=HEADERS)
            print(f"[SunarpHTTP] Status: {resp.status_code}")

            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

            result = resp.json()
            print(f"[SunarpHTTP] Keys: {list(result.keys())}")

            # 3. Extraer imagen del resultado
            result_image_b64 = self._extract_image_from_response(result)

            # 4. OCR
            ocr_text = ""
            if result_image_b64:
                ocr_text = self._ocr_image(result_image_b64)

            elapsed = round(time.time() - t_start, 1)
            print(f"[SunarpHTTP] Completado en {elapsed}s")

            return {
                "success": True,
                "placa": placa,
                "result_image_base64": result_image_b64,
                "ocr_text": ocr_text,
                "raw_response": result,
                "tiempo_segundos": elapsed,
            }

        except Exception as e:
            return {
                "success": False,
                "placa": placa,
                "error": str(e),
                "tiempo_segundos": round(time.time() - t_start, 1),
            }

    def _extract_image_from_response(self, result: dict) -> str:
        """Busca la imagen en la respuesta JSON de la API."""
        model = result.get("model", {})
        if isinstance(model, dict):
            imagen = model.get("imagen", "")
            if imagen and len(imagen) > 100:
                if not imagen.startswith("data:image"):
                    imagen = f"data:image/png;base64,{imagen}"
                print(f"[SunarpHTTP] Imagen encontrada en model.imagen ({len(imagen)} chars)")
                return imagen

        for key, val in result.items():
            if isinstance(val, str) and val.startswith("data:image"):
                print(f"[SunarpHTTP] Imagen encontrada en campo '{key}' ({len(val)} chars)")
                return val
            if isinstance(val, str) and len(val) > 1000 and ("base64" in val[:200] or val.startswith("iVBOR")):
                print(f"[SunarpHTTP] Posible imagen en campo '{key}' ({len(val)} chars)")
                return f"data:image/png;base64,{val}" if not val.startswith("data:") else val

        img = self._find_image_recursive(result)
        if img:
            return img

        print(f"[SunarpHTTP] No se encontró imagen en respuesta")
        return ""

    def _find_image_recursive(self, obj, depth=0) -> str:
        if depth > 5:
            return ""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and len(v) > 1000 and ("base64" in v[:200] or v.startswith("data:image")):
                    print(f"[SunarpHTTP] Imagen encontrada en '{k}' ({len(v)} chars)")
                    return v
                img = self._find_image_recursive(v, depth + 1)
                if img:
                    return img
        elif isinstance(obj, list):
            for item in obj:
                img = self._find_image_recursive(item, depth + 1)
                if img:
                    return img
        return ""

    def _ocr_image(self, image_b64: str) -> str:
        try:
            raw = image_b64.split(",")[1] if "," in image_b64 else image_b64
            img_data = base64.b64decode(raw)
            img = Image.open(io.BytesIO(img_data))
            print(f"[SunarpHTTP] OCR: imagen {img.size[0]}x{img.size[1]} {img.mode}")

            try:
                text = pytesseract.image_to_string(img, lang="spa")
            except Exception:
                text = pytesseract.image_to_string(img)

            text = text.strip()
            if text:
                print(f"[SunarpHTTP] OCR extrajo {len(text)} caracteres")
            return text
        except Exception as e:
            print(f"[SunarpHTTP] Error OCR: {e}")
            return ""

    def close(self):
        self.client.close()


if __name__ == "__main__":
    import sys
    placa = sys.argv[1] if len(sys.argv) > 1 else "ABC123"
    scraper = SunarpHTTP()
    try:
        import json
        result = scraper.consultar(placa)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        scraper.close()
