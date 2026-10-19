import asyncio
import base64
import random
import socket
import struct
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.compartido.captcha import CaptchaSolver
from app.core.config import CAPSOLVER_API_KEY, CAPSOLVER_PROXIES, BASE_URL
from app.compartido.chrome import create_driver
from app.compartido.proxy_forwarder import ProxyForwarder


class SOATScraper:
    IFRAME_URL = "https://webapp.apeseg.org.pe/consulta-soat/"
    LOCAL_PROXY_PORT = 0  # 0 = puerto efimero (evita colisiones entre scrapers concurrentes)
    TURNSTILE_SITEKEY = "0x4AAAAAADyJA_4hEDeVktbR"

    def __init__(self, use_proxy=False, headless=False):
        self.use_proxy = use_proxy
        self.headless = headless
        # indice inicial aleatorio: scrapers concurrentes no comparten la misma sesion/IP
        self.proxy_index = random.randrange(len(CAPSOLVER_PROXIES)) if CAPSOLVER_PROXIES else 0
        self.current_proxy = None
        self.solver = None
        self.driver = None
        self.proxy_forwarder = None

    def _get_next_proxy(self):
        if not CAPSOLVER_PROXIES:
            return None
        proxy = CAPSOLVER_PROXIES[self.proxy_index % len(CAPSOLVER_PROXIES)]
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
        print(f"[*] Proxy forwarder en 127.0.0.1:{self.proxy_forwarder.local_port}")
        return self.proxy_forwarder.local_port

    def _stop_local_proxy(self):
        if self.proxy_forwarder:
            self.proxy_forwarder.stop()
            self.proxy_forwarder = None

    def _test_proxy(self, proxy_str):
        """Verifica que el proxy residencial de CapSolver responda (HTTP CONNECT)."""
        host, port, user, password = self._parse_proxy(proxy_str)
        try:
            s = socket.socket()
            s.settimeout(15)
            s.connect((host, int(port)))
            auth = base64.b64encode(f"{user}:{password}".encode()).decode()
            s.sendall(
                f"CONNECT api.ipify.org:443 HTTP/1.1\r\n"
                f"Host: api.ipify.org:443\r\n"
                f"Proxy-Authorization: Basic {auth}\r\n\r\n".encode()
            )
            resp = b""
            while b"\r\n\r\n" not in resp and len(resp) < 1024:
                chunk = s.recv(1024)
                if not chunk:
                    break
                resp += chunk
            s.close()
            first = resp.split(b"\r\n")[0].decode(errors="ignore")
            ok = " 200 " in first
            print(f"[*] Test proxy {host}:{port}: {first} -> {'OK' if ok else 'FALLO'}")
            return ok
        except Exception as e:
            print(f"[!] Test proxy falló: {e}")
            return False

    def start(self):
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-web-security")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--window-size=1280,800")
        # Modo headless para servidores Linux sin GUI
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--hide-scrollbars")
            options.add_argument("--blink-settings=imagesEnabled=true")
        # Desactivar servicios de Chrome que generan ruido de red (no los queremos por proxy)
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
            if not self.current_proxy:
                self.current_proxy = self._get_next_proxy()
            chosen = None
            max_tries = min(5, len(CAPSOLVER_PROXIES)) or 1
            for _ in range(max_tries):
                if self.current_proxy and self._test_proxy(self.current_proxy):
                    chosen = self.current_proxy
                    break
                print("[!] Proxy no responde, probando el siguiente...")
                self.current_proxy = self._get_next_proxy()
            if chosen:
                host, port, user, password = self._parse_proxy(chosen)
                local_port = self._start_local_proxy(host, port, user, password)
                options.add_argument(f"--proxy-server=http://127.0.0.1:{local_port}")
                self.solver = CaptchaSolver(CAPSOLVER_API_KEY, chosen)
                print(f"[*] Proxy CapSolver activo: {host}:{port}")
            else:
                # Solo para este driver; el proximo start() volvera a intentar con proxy
                print(f"[!] Ningun proxy respondio tras {max_tries} intentos. Este driver usara IP local.")

        if not self.solver:
            self.solver = CaptchaSolver(CAPSOLVER_API_KEY, None)

        self.driver = create_driver(options)
        self.driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

    def stop(self):
        self._stop_local_proxy()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _wait_for_cloudflare(self, timeout=20):
        """Espera a que una Cloudflare Challenge interstitial desaparezca (en pagina principal o iframe)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                title = (self.driver.title or "").lower()
                body = self.driver.find_element(By.TAG_NAME, "body").text.lower()[:200]
            except Exception:
                time.sleep(0.5)
                continue
            if "just a moment" in title or "just a moment" in body or "checking your browser" in body or "cloudflare" in body and "ray id" in body:
                print(f"[*] Cloudflare Challenge activa, esperando... (title={title[:40]})")
                time.sleep(1)
                continue
            return True
        return False

    def _switch_to_iframe(self):
        self._wait_for_cloudflare()
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='webapp.apeseg.org.pe']"))
        )
        iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe[src*='webapp.apeseg.org.pe']")
        self.driver.switch_to.frame(iframe)
        self._wait_for_cloudflare()
        print("[*] Frame del formulario encontrado")

    def _solve_turnstile(self):
        """Resuelve Cloudflare Turnstile invisible del contenedor #turnstile-container.

        El sitio Vue lo renderea con window.turnstile.render tras un delay de ~300ms.
        A veces auto-resuelve (_token ya en input cf-turnstile-response); si no,
        usamos CapSolver (AntiTurnstileTaskProxyLess) con sitekey conocido.
        """
        print("[*] Buscando Cloudflare Turnstile...")
        sitekey = self.TURNSTILE_SITEKEY

        # 1) Esperar a que el contenedor de Turnstile exista
        for _ in range(10):
            try:
                if self.driver.execute_script(
                    "return !!document.querySelector('#turnstile-container iframe, [name=\"cf-turnstile-response\"]')"
                ):
                    break
            except Exception:
                pass
            time.sleep(0.5)

        # 2) Si Turnstile auto-resolvió (token ya presente), usar ese
        try:
            token = self.driver.execute_script(
                "return (document.querySelector('[name=\"cf-turnstile-response\"]') || {}).value || ''"
            )
            if token:
                print(f"[*] Turnstile auto-resuelto: {token[:40]}...")
                return True
        except Exception:
            pass

        # 3) Resolver con CapSolver
        print(f"[*] Resolviendo Turnstile con CapSolver: {sitekey}")
        try:
            solution = self.solver.solve_cloudflare_turnstile(
                site_url=self.IFRAME_URL, site_key=sitekey
            )
            token = solution.get("token", "")
            if not token:
                print("[!] CapSolver no devolvió token")
                return False
            print(f"[*] Token: {token[:50]}...")
            injected = self.driver.execute_script(
                """
                const i = document.querySelector('[name="cf-turnstile-response"]');
                if (i) {
                    i.value = arguments[0];
                    i.dispatchEvent(new Event('input', {bubbles:true}));
                    i.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }
                return false;
                """,
                token,
            )
            if not injected:
                # crear el input si no existe
                self.driver.execute_script(
                    """
                    let i = document.querySelector('[name="cf-turnstile-response"]');
                    if (!i) {
                        i = document.createElement('input');
                        i.type = 'hidden';
                        i.name = 'cf-turnstile-response';
                        document.querySelector('#turnstile-container')?.appendChild(i)
                            || document.body.appendChild(i);
                    }
                    i.value = arguments[0];
                    i.dispatchEvent(new Event('input', {bubbles:true}));
                    i.dispatchEvent(new Event('change', {bubbles:true}));
                    """,
                    token,
                )
            print("[*] Token Turnstile inyectado")
            return True
        except Exception as e:
            print(f"[!] Error Turnstile: {e}")
            return False

    def _solve_image_captcha(self):
        time.sleep(0.5)
        captcha_img = None
        try:
            captcha_img = self.driver.find_element(By.CSS_SELECTOR, ".captcha-container img")
        except Exception:
            pass
        if not captcha_img:
            try:
                for img in self.driver.find_elements(By.TAG_NAME, "img"):
                    src = img.get_attribute("src") or ""
                    if "data:image" in src and len(src) > 100:
                        captcha_img = img
                        break
            except Exception:
                pass
        if not captcha_img:
            raise Exception("No se encontró imagen de CAPTCHA")

        # Preferir el base64 original del atributo src (calidad nativa del servidor)
        src = captcha_img.get_attribute("src") or ""
        if src.startswith("data:image") and "," in src:
            img_b64 = src.split(",", 1)[1]
            print(f"[*] CAPTCHA extraido del src ({len(img_b64)} chars base64)")
        else:
            img_bytes = captcha_img.screenshot_as_png
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            print(f"[*] CAPTCHA capturado via screenshot ({len(img_bytes)} bytes)")
        return self.solver.solve_image_captcha(img_b64)

    def consultar_soat(self, placa, retry_delay=5, max_attempts=10):
        """Consulta el SOAT. Reintenta en batches de 5:
        - 5 intentos con el mismo driver
        - si fallan, cierra el driver, abre uno nuevo y repite.
        Maximo max_attempts intentos totales.
        """
        t_start = time.time()
        print(f"\n{'='*50}")
        print(f"[*] Consultando SOAT para placa: {placa}")
        print(f"{'='*50}")

        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            t_attempt = time.time()
            try:
                # cada 5 intentos: cerrar driver y abrir uno nuevo
                if attempt > 1 and (attempt - 1) % 5 == 0:
                    print(f"[*] Cerrando driver (intento {attempt}, batch {(attempt-1)//5+1})...")
                    self.stop()
                    self.driver = None

                # si no hay driver, crearlo
                if self.driver is None:
                    print(f"[*] Creando nuevo driver...")
                    self.start()

                # si sigue siendo None, la creacion fallo
                if self.driver is None:
                    print("[!] No se pudo crear el driver, reintentando...")
                    time.sleep(retry_delay)
                    continue

                self.driver.get(BASE_URL)
                self._wait_for_cloudflare()
                title = (self.driver.title or "").lower()
                if self.use_proxy and ("error" in title or "bad gateway" in title or not title
                                       or "err_" in title or "proxy" in title):
                    raise Exception(f"PROXY_PAGE: la pagina no cargo via proxy (title={title!r})")
                elif "error" in title or "bad gateway" in title or not title:
                    print(f"[!] Pagina no cargo OK (title={title!r}).")
                print(f"[*] Pagina principal cargada ({time.time()-t_attempt:.1f}s)")
                self._switch_to_iframe()
                time.sleep(0.5)

                placa_input = self.driver.find_element(By.CSS_SELECTOR, "#placa, input[name='placa']")
                placa_input.clear()
                placa_input.send_keys(placa)
                print(f"[*] Placa ingresada: {placa}")

                if not self._solve_turnstile():
                    print("[!] No se pudo resolver Turnstile; reintentando")
                    time.sleep(retry_delay)
                    continue
                time.sleep(0.5)

                captcha_text = self._solve_image_captcha()
                print(f"[*] CAPTCHA resuelto: {captcha_text}")

                captcha_input = self.driver.find_element(By.CSS_SELECTOR, "#captcha, input[name='captcha']")
                captcha_input.clear()
                captcha_input.send_keys(captcha_text)

                time.sleep(0.5)
                try:
                    submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                except Exception:
                    submit_btn = self.driver.find_element(By.XPATH, "//button[contains(text(),'Consultar')]")
                submit_btn.click()
                print("[*] Formulario enviado")
                pre_body = ""
                try:
                    pre_body = self.driver.find_element(By.TAG_NAME, "body").text
                except Exception:
                    pass
                result = self._extract_result(pre_body)
                elapsed = time.time() - t_start
                print(f"[*] Tiempo total: {elapsed:.1f}s (intento {attempt})")
                if result.get("success"):
                    result["tiempo_segundos"] = round(elapsed, 1)
                    return result
                error_msg = result.get('error', '')[:200]
                print(f"[!] Intento {attempt} falló: {error_msg}")
                # Rate limit: no reintentar, cerrar driver y esperar
                if "se ha superado" in error_msg.lower():
                    print("[!] Rate limit detectado. Cerrando driver y esperando 30s...")
                    self.stop()
                    time.sleep(30)
                    if self.use_proxy:
                        self._rotate_proxy()
                    else:
                        self.start()
                    continue
                # el servidor no pudo validar el captcha o la llamada a la API se corto
                # (suele pasar si la IP residencial cae a mitad de la consulta):
                # reintentar con driver nuevo y otra sesion
                if any(k in error_msg.lower() for k in ("error validando captcha", "failed to fetch")):
                    self.stop()
                    if self.use_proxy:
                        self.current_proxy = self._get_next_proxy()
                        print("[*] Error de captcha/red en la pagina; reintento con otra sesion de proxy")
                    else:
                        print("[*] Error de captcha/red en la pagina; reintento con driver nuevo")
            except Exception as e:
                print(f"[!] Intento {attempt} error: {e}")
                # liberar driver + forwarder local; start() creara unos nuevos
                self.stop()
                msg = str(e)
                if self.use_proxy and any(k in msg for k in (
                        "PROXY_PAGE", "ERR_PROXY", "ERR_TUNNEL", "ERR_TIMED_OUT",
                        "ERR_CONNECTION", "timeout", "Timeout")):
                    self.current_proxy = self._get_next_proxy()
                    print(f"[*] Fallo de red/proxy; siguiente proxy: {self.current_proxy.split(':')[0] if self.current_proxy else None}")
            print(f"[*] Reintentando en {retry_delay}s... (intento {attempt})")
            time.sleep(retry_delay)

        print(f"[!] Maximo de {max_attempts} intentos alcanzado para placa {placa}")
        self.stop()
        return {
            "success": False,
            "placa": placa,
            "error": f"Maximo de {max_attempts} intentos sin resultado exitoso",
            "tiempo_segundos": round(time.time() - t_start, 1),
        }

    def _rotate_proxy(self):
        self.current_proxy = self._get_next_proxy()
        print(f"[*] Rotando proxy: {self.current_proxy}")
        self.solver = CaptchaSolver(CAPSOLVER_API_KEY, self.current_proxy)
        self.stop()
        self.start()

    def _extract_result(self, pre_submit_body=None, timeout=30):
        """Tras enviar, el SPA Vue:
        - si captcha incorrecto: muestra mensaje en el mismo body
        - si OK: hace fetch a /api/login, /api/certificados, guarda en localStorage["certificados"]
          y navega via Vue router a /resultados (URL del iframe cambia).
        Estrategia: leer localStorage["certificados"] (mas fiable que el DOM).
        Selecciona el SOAT mas reciente (VIGENTE > FechaInicio mas alta).
        Captura un screenshot en base64 de la pantalla de resultados.
        """
        deadline = time.time() + timeout
        last_body = pre_submit_body or ""
        while time.time() < deadline:
            try:
                body = self.driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                time.sleep(0.3)
                continue
            low = body.lower()
            # 1) detectar errores explicitos del SPA
            for ind in ["captcha incorrecto", "error validando captcha", "complete la validaci", "se ha superado",
                        "error consultando", "el servicio de captcha", "no se encuentra"]:
                if ind in low:
                    html = self.driver.page_source
                    screenshot_b64 = self._capturar_screenshot()
                    return {"success": False, "error": body[:1000],
                            "screenshot_base64": screenshot_b64,
                            "raw_html": html[:3000]}
            # 2) leer certificados del localStorage (el SPA los guarda ahi)
            try:
                cert_json = self.driver.execute_script(
                    "return localStorage.getItem('certificados') || ''"
                )
            except Exception:
                cert_json = ""
            if cert_json:
                print(f"\n[*] Certificados obtenidos via localStorage")
                import json as _json
                try:
                    cert = _json.loads(cert_json)
                except Exception:
                    cert = cert_json
                placa_val = ""
                try:
                    placa_val = cert[0].get("Placa", "") if isinstance(cert, list) and cert else ""
                except Exception:
                    pass
                # seleccionar el SOAT mas reciente: VIGENTE > FechaInicio mas alta
                soat_reciente = self._seleccionar_mas_reciente(cert)
                # capturar screenshot de la pagina de resultados
                screenshot_b64 = self._capturar_screenshot()
                if soat_reciente:
                    return {"success": True, "placa": placa_val,
                            "soat": soat_reciente,
                            "screenshot_base64": screenshot_b64}
                # sin certificados: la pagina muestra el motivo
                # (ej. "No se encontro la placa solicitada")
                # Estado = "SIN SOAT" para que el reporte no muestre "-"
                return {"success": True, "placa": placa_val,
                        "estado": "SIN SOAT",
                        "soat": {"Estado": "SIN SOAT"},
                        "screenshot_base64": screenshot_b64,
                        "error": self._mensaje_sin_resultado()}
            # 3) si el body cambio drasticamente (navego a /resultados)
            if pre_submit_body and body and body != pre_submit_body:
                if any(k in low for k in ["vigente", "aseguradora", "certificado",
                                          "no se encontr", "resultado", "placa"]):
                    html = self.driver.page_source
                    print(f"\n[*] Respuesta (DOM):\n{body[:800]}")
                    # exito solo si hay datos del SOAT; "placa"/"resultado" tambien aparecen
                    # en el formulario con errores como "Failed to fetch"
                    success = (any(k in low for k in ["vigente", "vencido", "aseguradora", "certificado"])
                               and not any(ind in low for ind in
                                           ["no se encontr", "no existe", "error consultando"]))
                    screenshot_b64 = self._capturar_screenshot()
                    return {"success": success, "raw_text": body[:2000],
                            "raw_html": html[:5000],
                            "screenshot_base64": screenshot_b64,
                            "error": None if success else body[:1000]}
            last_body = body
            time.sleep(0.3)
        html = self.driver.page_source
        print(f"\n[*] Estado final iframe:\n{last_body[:600]}")
        screenshot_b64 = self._capturar_screenshot()
        return {"success": False,
                "error": "Sin respuesta del servidor (posible captcha incorrecto)",
                "screenshot_base64": screenshot_b64,
                "raw_text": last_body[:1000], "raw_html": html[:3000]}

    def _seleccionar_mas_reciente(self, certificados):
        """De la lista de certificados, retornar el mas reciente:
        prioridad: Estado=VIGENTE, luego FechaInicio mas alta (dd/mm/yyyy).
        """
        if not isinstance(certificados, list) or not certificados:
            return None

        def parse_fecha(fecha_str):
            if not fecha_str:
                return ""
            try:
                d, m, y = fecha_str.split("/")
                return f"{y.zfill(4)}{m.zfill(2)}{d.zfill(2)}"
            except Exception:
                return ""

        vigentes = [c for c in certificados if (c.get("Estado") or "").upper() == "VIGENTE"]
        if vigentes:
            return max(vigentes, key=lambda c: parse_fecha(c.get("FechaInicio", "")))
        # si no hay vigentes, el mas reciente por FechaInicio
        try:
            return max(certificados, key=lambda c: parse_fecha(c.get("FechaInicio", "")))
        except Exception:
            return certificados[0]

    def _mensaje_sin_resultado(self, fallback="Sin resultados"):
        """Lee de la pagina el motivo por el que no hay certificados
        (ej. "No se encontro la placa solicitada"). Si no se detecta,
        devuelve `fallback`."""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            return fallback
        for line in body.splitlines():
            text = line.strip()
            if not text:
                continue
            low = text.lower()
            if any(ind in low for ind in
                   ["no se encontr", "sin resultados", "no registrado",
                    "no existe"]):
                return text
        return fallback

    def _capturar_screenshot(self):
        """Captura un screenshot del contenido del iframe de resultados.
        Busca el contenedor principal del SOAT dentro del iframe y captura
        ese elemento. Si no lo encuentra, captura el body del iframe.
        """
        try:
            # intentar capturar el elemento principal de resultados dentro del iframe
            selectors = [
                "div.container",
                "main",
                ".resultado",
                "[class*='result']",
                "[class*='certific']",
                ".card",
                "article",
            ]
            element = None
            for sel in selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if element.is_displayed():
                        break
                except Exception:
                    continue
            if element is None:
                element = self.driver.find_element(By.TAG_NAME, "body")
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'start', behavior: 'instant'});",
                element,
            )
            time.sleep(0.3)
            png = element.screenshot_as_png
            b64 = base64.b64encode(png).decode("utf-8")
            print(f"[*] Screenshot capturado ({len(png)} bytes base64={len(b64)} chars)")
            return b64
        except Exception as e:
            print(f"[!] No se pudo capturar screenshot: {e}")
            return ""


def main():
    scraper = SOATScraper(use_proxy=True)
    scraper.start()
    try:
        result = scraper.consultar_soat("ABC123")
        print(f"\n[RESULTADO]\n{result}")
    finally:
        scraper.stop()


if __name__ == "__main__":
    main()
