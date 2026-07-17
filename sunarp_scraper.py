import time
import base64
import io
import json as json_lib

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PIL import Image
import pytesseract

from config import CAPSOLVER_API_KEY, SUNARP_URL
from captcha_solver import CaptchaSolver

# ── Configurar ruta de Tesseract para Windows ──
_tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
for _p in _tesseract_paths:
    if __import__("os").path.exists(_p):
        pytesseract.pytesseract.tesseract_cmd = _p
        break

# ── Configurar tessdata para español (si no existe en systema) ──
_user_tessdata = __import__("os").path.expanduser(r"~\.tesseract\tessdata")
if __import__("os").path.exists(_user_tessdata):
    __import__("os").environ["TESSDATA_PREFIX"] = _user_tessdata


def _attrs(el):
    """Helper: devuelve atributos clave de un elemento Selenium para debug."""
    atts = {}
    for a in ("id", "name", "class", "type", "placeholder", "formcontrolname", "aria-label"):
        v = el.get_attribute(a)
        if v:
            atts[a] = v[:60]
    return " ".join(f'{k}="{v}"' for k, v in atts.items())


class SunarpScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self.driver = None
        self.solver = CaptchaSolver(CAPSOLVER_API_KEY, None)
        self._api_requests = []  # para capturar requests de red

    def start(self):
        if self.driver is not None:
            print("[Sunarp] Chrome ya estaba iniciado, reutilizando")
            return
        print("[Sunarp] Iniciando Chrome...")
        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        self.driver = uc.Chrome(options=options)
        self.driver.set_page_load_timeout(45)
        self._captured_requests = []
        print(f"[Sunarp] Chrome iniciado. Ventana visible={not self.headless}")

    def _enable_network_logging(self):
        """Usa CDP (Chrome DevTools Protocol) para capturar requests de red con headers completos."""
        self._captured_requests = []
        try:
            # Habilitar dominio Network via CDP
            self.driver.execute_cdp_cmd("Network.enable", {})
            print("[Sunarp] CDP Network logging activado")
        except Exception as e:
            print(f"[Sunarp] CDP Network no disponible ({e}), usando fallback JS")

    def _get_captured_requests(self):
        """Obtiene los requests capturados via CDP."""
        try:
            # Obtener cookies
            cookies = self.driver.execute_cdp_cmd("Network.getAllCookies", {})
            cookie_dict = {}
            for c in cookies.get("cookies", []):
                if "sunarp" in c.get("domain", ""):
                    cookie_dict[c["name"]] = c["value"]
            if cookie_dict:
                print(f"[Sunarp] Cookies Sunarp: {list(cookie_dict.keys())}")

            # Obtener headers de la ultima request via Performance Logging
            perf = self.driver.execute_cdp_cmd(
                "Performance.getNetworkTimeline", {"type": "network"}
            )
            for entry in perf.get("data", []):
                url = entry.get("url", "")
                if "getDatosVehiculo" in url or "sunarp" in url.lower():
                    print(f"[Sunarp] Network entry: {url}")
        except Exception as e:
            print(f"[Sunarp] Error leyendo CDP: {e}")

    def stop(self):
        if self.driver:
            print("[Sunarp] Cerrando Chrome...")
            self.driver.quit()
            self.driver = None
            print("[Sunarp] Chrome cerrado")

    def navigate_to_base(self):
        """Navega a la URL base. Si ya estamos en la pagina, resetea el form via JS (mas rapido)."""
        current_url = self.driver.current_url or ""
        if "consultavehicular.sunarp.gob.pe" in current_url:
            print("[Sunarp] Ya en la pagina, reseteando formulario via JS...")
            try:
                self.driver.execute_script("""
                    // Cerrar modales abiertos
                    document.querySelectorAll('.modal.show .close, .modal.show [aria-label="Close"]').forEach(
                        function(b) { b.click(); }
                    );
                    // Limpiar solo el campo de placa (no el Turnstile)
                    var placaInput = document.querySelector('input[formcontrolname="nroPlaca"], input#nroPlaca');
                    if (placaInput) {
                        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        ).set;
                        nativeInputValueSetter.call(placaInput, '');
                        placaInput.dispatchEvent(new Event('input', { bubbles: true }));
                        placaInput.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                """)
                # Verificar que el formulario sigue accesible
                WebDriverWait(self.driver, 3).until(
                    EC.presence_of_element_located((By.ID, "nroPlaca"))
                )
                print("[Sunarp] Formulario reseteado")
                return
            except Exception as e:
                print(f"[Sunarp] Reset JS fallo ({e}), navegando desde cero...")

        print(f"[Sunarp] Navegando a {SUNARP_URL}")
        self.driver.get(SUNARP_URL)
        # Esperar a que Angular renderice el formulario Y el input sea interactuable
        try:
            WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.ID, "nroPlaca"))
            )
            print("[Sunarp] Formulario listo e interactuable")
        except TimeoutException:
            print("[Sunarp] Timeout esperando formulario, continuando...")
            time.sleep(1)

    def consultar(self, placa: str) -> dict:
        placa = placa.strip().upper()
        t_start = time.time()

        try:
            result = self._do_consult(placa)
            result["success"] = True
            result["placa"] = placa
            result["tiempo_segundos"] = round(time.time() - t_start, 1)
            return result
        except Exception as e:
            return {
                "success": False,
                "placa": placa,
                "error": str(e),
                "tiempo_segundos": round(time.time() - t_start, 1),
            }

    def _do_consult(self, placa: str) -> dict:
        print(f"\n[Sunarp] ===== INICIANDO CONSULTA {placa} =====")
        self.navigate_to_base()
        self._enable_network_logging()

        self._close_modal()

        print("[Sunarp] Buscando campo de ingreso de placa...")
        plate_input = self._find_plate_input()

        # Intentar send_keys; verificar que se escribio; si no, usar JS como respaldo
        plate_input.clear()
        plate_input.send_keys(placa)
        time.sleep(0.3)
        typed_value = plate_input.get_attribute("value") or ""
        if typed_value.upper() != placa:
            print(f"[Sunarp] send_keys fallo (valor='{typed_value}'), intentando con JavaScript...")
            self.driver.execute_script(f"""
                var el = document.querySelector('input#nroPlaca, input[formcontrolname="nroPlaca"]');
                if (!el) return;
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, '{placa}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            """)
            time.sleep(0.3)
            typed_value = plate_input.get_attribute("value") or ""
            print(f"[Sunarp] Despues de JS: valor='{typed_value}'")
        else:
            print(f"[Sunarp] Placa '{placa}' ingresada correctamente")

        # Resolver Turnstile via CapSolver antes de enviar
        print("[Sunarp] Resolviendo Cloudflare Turnstile con CapSolver...")
        self._solve_turnstile()

        # Verificar que el Turnstile fue resuelto antes de continuar
        try:
            turnstile_val = self.driver.execute_script(
                "var el = document.querySelector('input[name=\"cf-turnstile-response\"]');"
                "return el ? el.value : '';"
            )
            if not turnstile_val or len(turnstile_val) < 10:
                print("[Sunarp] Turnstile no tiene token valido, esperando auto-resolucion...")
                self._wait_turnstile_auto(10)
        except Exception:
            pass

        print("[Sunarp] Buscando boton Consultar...")
        consult_btn = self._find_consult_button()
        print(f"[Sunarp] Boton: <{consult_btn.tag_name}> text='{consult_btn.text.strip()}'")

        # Esperar que desaparezca el spinner overlay si existe
        try:
            WebDriverWait(self.driver, 3).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, "ngx-spinner-overlay"))
            )
            print("[Sunarp] Spinner overlay desaparecio")
        except TimeoutException:
            print("[Sunarp] No habia spinner overlay o no desaparecio")

        # Intentar click normal; si falla o el boton esta deshabilitado, usar JavaScript
        try:
            if consult_btn.is_enabled():
                consult_btn.click()
            else:
                print("[Sunarp] Boton deshabilitado, usando JavaScript click...")
                self.driver.execute_script("arguments[0].click();", consult_btn)
        except Exception as e:
            print(f"[Sunarp] Click normal fallo ({e}), intentando JavaScript click...")
            self.driver.execute_script("arguments[0].click();", consult_btn)
        print("[Sunarp] Clic en Consultar ejecutado, esperando resultado...")

        # Capturar cookies via CDP
        self._get_captured_requests()

        # Capturar cookies del dominio sunarp
        try:
            cookies = self.driver.execute_cdp_cmd("Network.getAllCookies", {})
            for c in cookies.get("cookies", []):
                if "sunarp" in c.get("domain", "") or "sunarp" in c.get("name", "").lower():
                    print(f"[Sunarp] Cookie: {c['name']}={c['value'][:50]}... domain={c.get('domain','')}")
        except Exception as e:
            print(f"[Sunarp] Error cookies CDP: {e}")

        # Capturar headers de Angular via Performance Logging
        try:
            perf = self.driver.execute_cdp_cmd("Performance.getNetworkTimeline", {"type": "network"})
            for entry in perf.get("data", []):
                url = entry.get("url", "")
                if "getDatosVehiculo" in url or "api-gateway" in url:
                    print(f"[Sunarp] API request detectada: {url[:120]}")
        except Exception as e:
            pass

        # Esperar resultado
        result_image_b64 = self._wait_and_extract_result()

        print("[Sunarp] Ejecutando OCR sobre la imagen...")
        ocr_text = self._ocr_image(result_image_b64)

        print(f"[Sunarp] ===== CONSULTA COMPLETADA ({len(result_image_b64)} chars img) =====")
        return {
            "placa": placa,
            "result_image_base64": result_image_b64,
            "ocr_text": ocr_text,
        }

    def _close_modal(self):
        for sel in ("button.close", "button[aria-label='Close']", ".modal-header button", "button.cerrar"):
            try:
                for btn in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(0.1)
                        return
            except Exception:
                pass

    def _dump_page_state(self):
        print("\n[Sunarp] ===== DUMP DE PAGINA =====")
        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            print(f"[Sunarp] Inputs encontrados ({len(inputs)}):")
            for i, inp in enumerate(inputs[:20]):
                visible = inp.is_displayed()
                attrs = _attrs(inp)
                print(f"         [{i}] visible={visible} <input {attrs}>")
            if len(inputs) > 20:
                print(f"         ... y {len(inputs)-20} mas")
        except Exception as e:
            print(f"[Sunarp] Error dump inputs: {e}")

        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            print(f"[Sunarp] Botones ({len(buttons)}):")
            for i, btn in enumerate(buttons[:15]):
                visible = btn.is_displayed()
                txt = btn.text.strip()[:60]
                cls = btn.get_attribute("class") or ""
                print(f"         [{i}] visible={visible} text='{txt}' class='{cls}'")
            if len(buttons) > 15:
                print(f"         ... y {len(buttons)-15} mas")
        except Exception as e:
            print(f"[Sunarp] Error dump buttons: {e}")

        try:
            select_els = self.driver.find_elements(By.TAG_NAME, "select")
            if select_els:
                print(f"[Sunarp] Selects ({len(select_els)}):")
                for i, sel in enumerate(select_els[:5]):
                    print(f"         [{i}] <select {_attrs(sel)}>")
        except Exception:
            pass

        try:
            imgs = self.driver.find_elements(By.TAG_NAME, "img")
            print(f"[Sunarp] Imagenes ({len(imgs)}):")
            for i, img in enumerate(imgs[:5]):
                src = (img.get_attribute("src") or "")[:80]
                print(f"         [{i}] src='{src}'")
            if len(imgs) > 5:
                print(f"         ... y {len(imgs)-5} mas")
        except Exception:
            pass

        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            print(f"[Sunarp] Iframes ({len(iframes)}):")
            for i, f in enumerate(iframes):
                src = (f.get_attribute("src") or "")[:100]
                print(f"         [{i}] src='{src}'")
        except Exception:
            pass

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            print(f"[Sunarp] Body text (primeros 500 chars):")
            print(f"         {body.text[:500]}")
        except Exception:
            pass

        print("[Sunarp] ===== FIN DUMP =====\n")

    def _solve_turnstile(self):
        site_key = "0x4AAAAAACFzt4Xn8T1Jg9ZS"
        print(f"[Sunarp] Solicitando token Turnstile a CapSolver (sitekey={site_key})...")
        solution = self.solver.solve_cloudflare_turnstile(SUNARP_URL, site_key)
        token = solution.get("token", "")
        if token:
            print(f"[Sunarp] Token Turnstile obtenido ({len(token)} chars)")
        else:
            print(f"[Sunarp] CapSolver no devolvio token: {solution}")

        if not token:
            print("[Sunarp] Sin token, esperando auto-resolucion...")
            self._wait_turnstile_auto(20)
            return

        # Inyectar token en el input hidden
        print("[Sunarp] Inyectando token Turnstile...")
        try:
            script = f"""
            var input = document.querySelector('input[name="cf-turnstile-response"]');
            if (input) {{
                Object.defineProperty(input, 'value', {{
                    writable: true,
                    configurable: true,
                    value: '{token}'
                }});
                input.value = '{token}';
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
            // Buscar iframe de Turnstile y hacerle click para activar callback
            var iframes = document.querySelectorAll('iframe[src*="turnstile"]');
            iframes.forEach(function(f) {{
                try {{
                    f.click();
                }} catch(e) {{}}
            }});
            """
            self.driver.execute_script(script)
            print("[Sunarp] Token inyectado")
        except Exception as e:
            print(f"[Sunarp] Error inyectando token: {e}")

        # Verificar que el token se inyectó correctamente
        try:
            val = self.driver.execute_script(
                "var el = document.querySelector('input[name=\"cf-turnstile-response\"]');"
                "return el ? el.value : '';"
            )
            if val and len(val) > 10:
                print(f"[Sunarp] Token verificado en DOM ({len(val)} chars)")
            else:
                print(f"[Sunarp] Token NO encontrado en DOM despues de inyectar")
        except Exception:
            pass

        # Dar tiempo a Angular para procesar el token
        time.sleep(0.5)

    def _wait_turnstile_auto(self, timeout=20):
        """Espera a que Turnstile se resuelva automaticamente."""
        import re
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                el = self.driver.find_element(By.NAME, "cf-turnstile-response")
                val = el.get_attribute("value") or ""
                if val and len(val) > 10:
                    print(f"[Sunarp] Turnstile auto-resuelto ({len(val)} chars)")
                    return True
            except Exception:
                pass
            time.sleep(1)
        print("[Sunarp] Turnstile no se auto-resolvio en el tiempo limite")
        return False

    def _find_plate_input(self):
        try:
            return self.driver.find_element(By.ID, "nroPlaca")
        except NoSuchElementException:
            pass
        # Fallbacks
        for sel in ("input[formcontrolname='nroPlaca']", "input[placeholder*='placa' i]"):
            try:
                return self.driver.find_element(By.CSS_SELECTOR, sel)
            except NoSuchElementException:
                pass
        # Ultimo recurso: primer input visible
        for inp in self.driver.find_elements(By.TAG_NAME, "input"):
            if inp.is_displayed() and (inp.get_attribute("type") or "text") in ("text", "", "search"):
                return inp
        raise Exception("No se encontro campo de ingreso de placa")

    def _find_consult_button(self):
        xpath_checks = [
            "//button[contains(translate(text(),'CONSULTAR','consultar'),'consultar')]",
            "//button[contains(@class,'consultar')]",
            "//button[contains(@class,'btn-primary')]",
            "//button[contains(@class,'btn-submit')]",
            "//button[@type='submit']",
        ]
        for xp in xpath_checks:
            try:
                btn = self.driver.find_element(By.XPATH, xp)
                if btn.is_displayed():
                    print(f"[Sunarp] Boton consulta encontrado via XPath: '{xp}'")
                    return btn
            except NoSuchElementException:
                pass

        print("[Sunarp] Buscando botones por texto...")
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if btn.is_displayed():
                txt = btn.text.lower().strip()
                if any(k in txt for k in ("consult", "buscar", "enviar", "aceptar")):
                    print(f"[Sunarp] Boton fallback: <button> '{btn.text.strip()}'")
                    return btn

        # dump all buttons for debugging
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        print(f"[Sunarp] Botones visibles en pagina ({len(buttons)}):")
        for btn in buttons:
            if btn.is_displayed():
                print(f"         <button> '{btn.text.strip()[:50]}' classes='{btn.get_attribute('class')}'")

        raise Exception("No se encontro boton de consulta")

    def _solve_captcha_if_present(self) -> bool:
        print("[Sunarp] Verificando si aparece captcha de imagen...")
        captcha_selectors = [
            "img[src*='base64']",
            "img.captcha",
            ".captcha-container img",
            "[class*='captcha'] img",
            "#captcha img",
        ]
        try:
            wait = WebDriverWait(self.driver, 6)
            captcha_img = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ", ".join(captcha_selectors))))
            print(f"[Sunarp] Captcha imagen detectado: <{captcha_img.tag_name} {_attrs(captcha_img)}>")
        except TimeoutException:
            print("[Sunarp] No aparecio captcha de imagen (timeout 6s)")
            return False

        img_src = captcha_img.get_attribute("src") or ""
        if not img_src or "base64" not in img_src:
            print(f"[Sunarp] Captcha encontrado pero sin base64. src={img_src[:80]}")
            return False

        print(f"[Sunarp] Enviando captcha a CapSolver ({len(img_src)} chars)...")
        captcha_text = self.solver.solve_image_captcha(img_src)
        print(f"[Sunarp] CapSolver devolvio: '{captcha_text}'")

        captcha_input = self._find_captcha_input()
        if captcha_input:
            print(f"[Sunarp] Input captcha encontrado: <{captcha_input.tag_name} {_attrs(captcha_input)}>")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)
            print(f"[Sunarp] Texto '{captcha_text}' ingresado en campo captcha")

            verify_btn = self._find_verify_button()
            if verify_btn:
                print(f"[Sunarp] Boton validar encontrado: '{verify_btn.text.strip()}'")
                verify_btn.click()
                print("[Sunarp] Clic en validar captcha ejecutado")
                time.sleep(2)
                return True
            else:
                print("[Sunarp] No se encontro boton de validar captcha")
        else:
            print("[Sunarp] No se encontro input para el captcha")
            # Maybe the captcha is already validated? Continue.

        return True

    def _find_captcha_input(self):
        selectors = [
            "input[formcontrolname='codigoCaptcha']",
            "input[placeholder*='captcha' i]",
            "input[placeholder*='codigo' i]",
            "input[placeholder*='Código']",
            "input.captcha-input",
            "input[id*='captcha' i]",
            ".captcha-container input",
        ]
        for sel in selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    print(f"[Sunarp] Selector captcha_input OK: '{sel}'")
                    return el
            except NoSuchElementException:
                pass

        print("[Sunarp] Buscando input captcha por fallback...")
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            if inp.is_displayed():
                return inp
        return None

    def _find_verify_button(self):
        xpath_checks = [
            "//button[contains(translate(text(),'VALIDAR','validar'),'validar')]",
            "//button[contains(translate(text(),'ACEPTAR','aceptar'),'aceptar')]",
            "//button[contains(translate(text(),'ENVIAR','enviar'),'enviar')]",
            "//button[contains(translate(text(),'VERIFICAR','verificar'),'verificar')]",
            "//button[contains(@class,'validar')]",
        ]
        for xp in xpath_checks:
            try:
                btn = self.driver.find_element(By.XPATH, xp)
                if btn.is_displayed():
                    return btn
            except NoSuchElementException:
                pass

        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if btn.is_displayed():
                txt = btn.text.lower()
                if any(k in txt for k in ("validar", "aceptar", "enviar", "verificar", "ok")):
                    return btn
        return None

    def _wait_and_extract_result(self) -> str:
        """Espera inteligente a que aparezca la imagen resultado (max 5s)."""
        deadline = time.time() + 5
        while time.time() < deadline:
            b64 = self._extract_result_image()
            if b64:
                return b64
            time.sleep(0.3)
        print("[Sunarp] No se encontro imagen resultado en 5s, tomando screenshot")
        return self._screenshot_base64()

    def _extract_result_image(self) -> str:
        """Busca la imagen resultado en el DOM. Retorna None si no la encuentra."""
        selectors = [
            "img[src*='base64']",
            ".resultado img",
            ".result-container img",
            ".consulta-result img",
            "img[class*='result']",
            ".modal-body img",
            ".card img",
            "main img",
            "section img",
        ]

        for sel in selectors:
            try:
                imgs = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for img in imgs:
                    src = img.get_attribute("src") or ""
                    if src and len(src) > 100:
                        print(f"[Sunarp] Imagen resultado con selector '{sel}': {len(src)} chars")
                        return src
            except NoSuchElementException:
                pass

        print("[Sunarp] Buscando cualquier imagen en la pagina...")
        imgs = self.driver.find_elements(By.TAG_NAME, "img")
        print(f"[Sunarp] Total imagenes en pagina: {len(imgs)}")
        for i, img in enumerate(imgs):
            src = img.get_attribute("src") or ""
            visible = img.is_displayed()
            print(f"         img[{i}]: visible={visible} src={src[:80]}...")
            if src and len(src) > 500:
                print(f"[Sunarp] Usando img[{i}] como resultado ({len(src)} chars)")
                return src

        return None

    def _screenshot_base64(self) -> str:
        print("[Sunarp] Capturando screenshot...")
        png = self.driver.get_screenshot_as_png()
        b64 = base64.b64encode(png).decode()
        print(f"[Sunarp] Screenshot: {len(b64)} chars base64")
        return f"data:image/png;base64,{b64}"

    def _ocr_image(self, image_b64: str) -> str:
        if not image_b64 or "base64" not in image_b64:
            print("[Sunarp] OCR: no hay imagen (sin base64)")
            return ""

        try:
            raw = image_b64.split(",")[1] if "," in image_b64 else image_b64
            img_data = base64.b64decode(raw)
            img = Image.open(io.BytesIO(img_data))
            print(f"[Sunarp] OCR: imagen {img.size[0]}x{img.size[1]} {img.mode}")

            try:
                text = pytesseract.image_to_string(img, lang="spa")
            except Exception:
                print("[Sunarp] OCR con lang=spa fallo, intentando sin idioma...")
                text = pytesseract.image_to_string(img)

            text = text.strip()
            print(f"[Sunarp] OCR extrajo {len(text)} caracteres:")
            if text:
                for line in text.splitlines():
                    print(f"         | {line}")
            return text
        except ImportError:
            print("[Sunarp] pytesseract no instalado, OCR omitido")
            return ""
        except Exception as e:
            print(f"[Sunarp] Error OCR: {e}")
            return ""


if __name__ == "__main__":
    import sys
    placa = sys.argv[1] if len(sys.argv) > 1 else "ABC123"
    scraper = SunarpScraper()
    scraper.start()
    try:
        result = scraper.consultar(placa)
        print(json_lib.dumps(result, ensure_ascii=False, indent=2))
    finally:
        scraper.stop()
