import base64
import json
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from captcha_solver import CaptchaSolver
from config import CAPSOLVER_API_KEY, CAPSOLVER_PROXIES_MTC, MTC_BASE_URL
from scraper import ProxyForwarder
from chrome_utils import create_driver


class MTCScraper:
    LOCAL_PROXY_PORT = 18081

    def __init__(self, use_proxy=False, headless=True):
        self.use_proxy = use_proxy
        self.headless = headless
        self.driver = None
        self.proxy_index = 0
        self.solver = CaptchaSolver(CAPSOLVER_API_KEY, None)
        self.proxy_forwarder = None

    def _get_next_proxy(self):
        if not CAPSOLVER_PROXIES_MTC:
            return None
        proxy = CAPSOLVER_PROXIES_MTC[self.proxy_index % len(CAPSOLVER_PROXIES_MTC)]
        self.proxy_index += 1
        return proxy

    def _parse_proxy(self, proxy_str):
        parts = proxy_str.split(":")
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], parts[3]
        return proxy_str, None, None, None

    def _start_local_proxy(self, host, port, user, password):
        self.proxy_forwarder = ProxyForwarder(
            self.LOCAL_PROXY_PORT, host, port, user, password
        )
        self.proxy_forwarder.start()
        print(f"[*] Proxy forwarder MTC en 127.0.0.1:{self.LOCAL_PROXY_PORT}")

    def _stop_local_proxy(self):
        if self.proxy_forwarder:
            self.proxy_forwarder.stop()
            self.proxy_forwarder = None

    def start(self, _retry_on_403=True):
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--window-size=1280,800")
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--hide-scrollbars")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-component-update")
        options.add_argument("--disable-domain-reliability")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-features=OptimizationGuideDownloading,OptimizationHints,Translate,MediaRouter")
        options.add_argument("--safebrowsing-disable-auto-update")
        options.add_argument("--disable-client-side-phishing-detection")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-extensions")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-first-run")

        if self.use_proxy:
            raw = self._get_next_proxy()
            if raw:
                host, port, user, password = self._parse_proxy(raw)
                self._start_local_proxy(host, port, user, password)
                options.add_argument(f"--proxy-server=127.0.0.1:{self.LOCAL_PROXY_PORT}")
                print(f"[*] MTC usando proxy via forwarder: {host}:{port}")

        self.driver = create_driver(options)
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        self.driver.get(f"{MTC_BASE_URL}/Citv/ArConsultaCitv")
        time.sleep(3)

        title = (self.driver.title or "").lower()
        if "403" in title or "forbidden" in title:
            if _retry_on_403:
                print(f"[!] MTC 403 Forbidden - rotando proxy...")
                self.stop()
                time.sleep(2)
                self.use_proxy = True
                self.start(_retry_on_403=False)
                return
        print(f"[*] Sesion MTC iniciada (title={self.driver.title})")

    def stop(self):
        self._stop_local_proxy()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _refresh_captcha(self):
        """Obtiene la imagen captcha del DOM (data:image/png;base64)."""
        time.sleep(1)

        captcha_img = None

        # El captcha esta en img con alt="Cargando.." y src data:image/png;base64
        try:
            captcha_img = self.driver.find_element(
                By.CSS_SELECTOR, "img[alt*='Cargando']"
            )
            src = captcha_img.get_attribute("src") or ""
            if "data:image" in src:
                print(f"[*] Captcha encontrado por alt='Cargando..'")
            else:
                captcha_img = None
        except Exception:
            pass

        if not captcha_img:
            try:
                imgs = self.driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src") or ""
                    if src.startswith("data:image") and len(src) > 100:
                        captcha_img = img
                        print(f"[*] Captcha encontrado por data:image src")
                        break
            except Exception:
                pass

        if not captcha_img:
            raise Exception("No se encontro imagen de CAPTCHA")

        src = captcha_img.get_attribute("src") or ""
        if src.startswith("data:image") and "," in src:
            img_b64 = src.split(",", 1)[1].strip()
            print(f"[*] Captcha obtenido ({len(img_b64)} chars base64)")
            return img_b64
        else:
            png = captcha_img.screenshot_as_png
            img_b64 = base64.b64encode(png).decode("utf-8")
            print(f"[*] Captcha capturado via screenshot ({len(png)} bytes)")
            return img_b64

    def _solve_captcha(self, image_b64):
        return self.solver.solve_image_captcha(image_b64)

    def _consultar(self, placa, captcha_text):
        """Llena el formulario y ejecuta la consulta."""

        # Seleccionar busqueda por Placa si es necesario
        try:
            sel = self.driver.find_element(By.ID, "selBUS_Filtro")
            from selenium.webdriver.support.ui import Select
            select = Select(sel)
            for option in select.options:
                if "placa" in (option.text or "").lower():
                    select.select_by_visible_text(option.text)
                    print(f"[*] Tipo busqueda: {option.text}")
                    time.sleep(0.5)
                    break
        except Exception:
            pass

        # Ingresar placa en texFiltro
        placa_input = self.driver.find_element(By.ID, "texFiltro")
        placa_input.clear()
        placa_input.send_keys(placa)
        print(f"[*] Placa ingresada: {placa}")

        # Ingresar captcha en texCaptcha
        captcha_input = self.driver.find_element(By.ID, "texCaptcha")
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)
        print(f"[*] Captcha ingresado: {captcha_text}")

        time.sleep(0.5)

        # Click en boton Buscar
        submit_btn = self.driver.find_element(
            By.XPATH, "//button[contains(text(),'Buscar')]"
        )
        submit_btn.click()
        print("[*] Formulario enviado")

        # Manejar alerts de JavaScript (errores del sitio)
        time.sleep(1)
        alert_text = ""
        try:
            alert = self.driver.switch_to.alert
            alert_text = alert.text
            print(f"[!] Alert detectado: {alert_text}")
            alert.accept()
        except Exception:
            pass

        # Si hubo alert de captcha incorrecto, retornar ese error
        if alert_text:
            if "valido" in alert_text.lower() or "captcha" in alert_text.lower():
                return alert_text

        # Esperar a que aparezcan los resultados
        time.sleep(3)

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_text = ""

        return body_text

    def consultar(self, placa, max_retries=10):
        placa = placa.strip().upper()
        t_start = time.time()

        for intento in range(1, max_retries + 1):
            print(f"\n[*] MTC consulta {placa} (intento {intento}/{max_retries})")
            try:
                b64 = self._refresh_captcha()
                captcha_text = self._solve_captcha(b64)
                print(f"[*] Captcha resuelto: {captcha_text}")

                body_text = self._consultar(placa, captcha_text)
                result = self._procesar_respuesta(body_text, placa, t_start)

                screenshot_b64 = self._capturar_screenshot()
                result["screenshot_base64"] = screenshot_b64

                if result.get("success"):
                    return result
                print(f"[!] Intento {intento}: {result.get('error', 'error desconocido')}")
            except Exception as e:
                print(f"[!] Intento {intento} error: {e}")
                if max_retries == 1:
                    raise

            if intento < max_retries:
                time.sleep(2)

        return {
            "success": False,
            "placa": placa,
            "error": f"No se obtuvo resultado tras {max_retries} intentos",
            "screenshot_base64": self._capturar_screenshot(),
            "tiempo_segundos": round(time.time() - t_start, 1),
        }

    def _procesar_respuesta(self, body_text, placa, t_start):
        low = body_text.lower()

        # Si el body viene de un alert de captcha incorrecto
        if "valido" in low or "verifique" in low:
            return {"success": False, "placa": placa, "error": body_text}

        for ind in ["captcha incorrecto", "captcha errado", "codigo incorrecto",
                    "complete la validacion", "se ha superado", "error consultando",
                    "el servicio", "no se encuentra", "no existe"]:
            if ind in low:
                return {"success": False, "placa": placa, "error": body_text[:500]}

        if "no se encontraron certificados" in low or "sin resultados" in low:
            return {"success": False, "placa": placa, "error": "No se encontraron certificados"}

        for ind in ["empresa certificadora", "nro certificado", "vigente",
                    "resultado", "aprobado", "rechazado", "estado"]:
            if ind in low:
                return self._extraer_datos_del_dom(placa, t_start)

        return {"success": False, "placa": placa, "error": f"Respuesta no reconocida: {body_text[:300]}"}

    def _extraer_datos_del_dom(self, placa, t_start):
        """Extrae los datos del CITV directamente del DOM usando los span IDs."""
        documentos = []

        for record_num in range(1, 20):
            prefix = f"Spv{record_num}_"
            try:
                empresa = self.driver.find_element(By.ID, f"{prefix}1").text.strip()
            except Exception:
                break
            try:
                direccion = self.driver.find_element(By.ID, f"{prefix}2").text.strip()
            except Exception:
                direccion = ""
            try:
                placa_val = self.driver.find_element(By.ID, f"{prefix}3").text.strip()
            except Exception:
                placa_val = ""
            try:
                nro_cert = self.driver.find_element(By.ID, f"{prefix}4").text.strip()
            except Exception:
                nro_cert = ""
            try:
                vigente_desde = self.driver.find_element(By.ID, f"{prefix}5").text.strip()
            except Exception:
                vigente_desde = ""
            try:
                vigente_hasta = self.driver.find_element(By.ID, f"{prefix}6").text.strip()
            except Exception:
                vigente_hasta = ""
            try:
                resultado = self.driver.find_element(By.ID, f"{prefix}7").text.strip()
            except Exception:
                resultado = ""
            try:
                estado = self.driver.find_element(By.ID, f"{prefix}8").text.strip()
            except Exception:
                estado = ""
            try:
                ambito = self.driver.find_element(By.ID, f"{prefix}9").text.strip()
            except Exception:
                ambito = ""
            try:
                tipo_servicio = self.driver.find_element(By.ID, f"{prefix}10").text.strip()
            except Exception:
                tipo_servicio = ""
            try:
                observaciones = self.driver.find_element(By.ID, f"{prefix}11").text.strip()
            except Exception:
                observaciones = ""
            try:
                nro_informe = self.driver.find_element(By.ID, f"{prefix}12").text.strip()
            except Exception:
                nro_informe = ""

            nro_doc = nro_cert or nro_informe

            doc = {
                "empresa_certificadora": empresa,
                "direccion": direccion,
                "placa": placa_val,
                "nro_certificado": nro_doc,
                "tipo_documento": "CITV",
                "vigente_desde": vigente_desde,
                "vigente_hasta": vigente_hasta,
                "resultado_inspeccion": resultado,
                "estado": estado,
                "ambito": ambito,
                "tipo_servicio": tipo_servicio,
                "observaciones": observaciones,
            }
            documentos.append(doc)

        if not documentos:
            return {"success": False, "placa": placa,
                    "error": "No se pudieron extraer datos del DOM"}

        ultimo = documentos[0]
        return {
            "success": True,
            "placa": placa,
            "fuente": "MTC_CITV",
            "ultimo_documento": ultimo,
            "documentos_completos": documentos,
            "tiempo_segundos": round(time.time() - t_start, 1),
        }

    def _capturar_screenshot(self):
        try:
            tables = self.driver.find_elements(By.CSS_SELECTOR, "table.table")
            if tables:
                element = tables[0]
                parent = self.driver.execute_script(
                    "return arguments[0].parentElement;", element
                )
                if parent:
                    element = parent
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'start', behavior: 'instant'});",
                    element,
                )
                time.sleep(0.3)
                png = element.screenshot_as_png
                b64 = base64.b64encode(png).decode("utf-8")
                print(f"[*] Screenshot MTC capturado (tabla, {len(png)} bytes)")
                return b64
            element = self.driver.find_element(By.TAG_NAME, "body")
            png = element.screenshot_as_png
            b64 = base64.b64encode(png).decode("utf-8")
            print(f"[*] Screenshot MTC full-page ({len(png)} bytes)")
            return b64
        except Exception as e:
            print(f"[!] No se pudo capturar screenshot MTC: {e}")
            try:
                png = self.driver.get_screenshot_as_png()
                b64 = base64.b64encode(png).decode("utf-8")
                return b64
            except Exception:
                return ""


if __name__ == "__main__":
    import sys
    placa = sys.argv[1] if len(sys.argv) > 1 else "ABC123"
    scraper = MTCScraper()
    scraper.start()
    try:
        result = scraper.consultar(placa)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        scraper.stop()
