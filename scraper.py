import asyncio
import base64
import random
import select
import socket
import struct
import subprocess
import threading
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from captcha_solver import CaptchaSolver
from config import CAPSOLVER_API_KEY, CAPSOLVER_PROXIES, BASE_URL


def _detect_chrome_version():
    """Detecta la version mayor de Chrome instalada."""
    for cmd in (["google-chrome", "--version"], ["google-chrome-stable", "--version"],
                ["/usr/bin/google-chrome", "--version"], ["chromium", "--version"]):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5).decode()
            import re
            m = re.search(r"(\d+)\.\d+\.\d+\.\d+", out)
            if m:
                v = int(m.group(1))
                print(f"[Chrome] Version detectada: {v}")
                return v
        except Exception:
            pass
    print("[Chrome] No se detecto version, usando 150 por defecto")
    return 150


class ProxyForwarder:
    """Proxy HTTP CONNECT forwarder con auth para CapSolver.

    Filtra dominios de ruido de Chrome (telemetria/updates) que NO deben pasar
    por el proxy residencial: esos se atienden localmente (sin proxy) para no
    agotar la sesion ni ancho de banda del proxy. Solo los dominios del sitio
    objetivo (apeseg.org.pe, webapp.apeseg.org.pe, api.apeseg.org.pe,
    challenges.cloudflare.com) se tlever a traves del proxy residencial.
    """

    NOISE_DOMAINS = (
        "google.com", "googleapis.com", "gstatic.com", "gvt1.com", "gvt2.com", "gvt3.com",
        "google-analytics.com", "googletagmanager.com", "doubleclick.net",
        "fonts.googleapis.com", "fonts.gstatic.com", "accounts.google.com",
        "android.clients.google.com", "clients2.google.com",
        "clientservices.googleapis.com", "encrypted-tbn0.gstatic.com",
        "safebrowsingohttpgateway.googleapis.com",
        "optimizationguide-pa.googleapis.com", "redirector.gvt1.com",
        "update.googleapis.com", "edge.microsoft.com", "bing.com",
        "www.gstatic.com",
    )

    def __init__(self, local_port, remote_host, remote_port, username, password):
        self.local_port = local_port
        self.remote_host = remote_host
        self.remote_port = int(remote_port)
        self.credentials = f"{username}:{password}"
        self.server_socket = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(("127.0.0.1", self.local_port))
        self.server_socket.listen(128)
        self.server_socket.settimeout(1)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                client, addr = self.server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[!] Proxy accept error: {e}")

    def _handle_client(self, client_socket):
        try:
            request = client_socket.recv(4096).decode(errors="ignore")
            first_line = request.split("\r\n")[0]
            parts = first_line.split()

            if len(parts) < 3 or parts[0] != "CONNECT":
                client_socket.close()
                return

            target = parts[1]
            host_port = target.rsplit(":", 1)
            host_only = host_port[0] if host_port else target

            # Filtrar ruido de Chrome: no router por proxy
            if any(nd in host_only for nd in self.NOISE_DOMAINS):
                client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self._direct_tunnel(client_socket, host_only,
                                    int(host_port[1]) if len(host_port) > 1 else 443)
                return

            print(f"[*] CONNECT -> {target}")

            remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote_socket.settimeout(30)
            remote_socket.connect((self.remote_host, self.remote_port))

            auth = base64.b64encode(self.credentials.encode()).decode()
            connect_req = (
                f"CONNECT {target} HTTP/1.1\r\n"
                f"Host: {target}\r\n"
                f"Proxy-Authorization: Basic {auth}\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
            )
            remote_socket.sendall(connect_req.encode())

            response = b""
            while b"\r\n\r\n" not in response:
                chunk = remote_socket.recv(4096)
                if not chunk:
                    break
                response += chunk

            status_line = response.split(b"\r\n")[0].decode(errors="ignore")

            if b"200" in response.split(b"\r\n")[0]:
                client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self._tunnel(client_socket, remote_socket)
            else:
                print(f"[!] Proxy remoto rechazó {target}: {status_line}")
                client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                client_socket.close()

            remote_socket.close()
        except Exception as e:
            print(f"[*] Proxy tunnel error: {e}")
            try:
                client_socket.close()
            except Exception:
                pass

    def _direct_tunnel(self, client, host, port):
        """Tunel directo sin proxy (para ruido de Chrome)."""
        try:
            remote = socket.create_connection((host, port), timeout=10)
        except Exception as e:
            print(f"[!] Tunnel directo a {host}:{port} fallo: {e}")
            try:
                client.close()
            except Exception:
                pass
            return
        self._tunnel(client, remote)

    def _tunnel(self, client, remote):
        sockets = [client, remote]
        timeout_count = 0
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 5)
                if exceptional:
                    break
                if not readable:
                    timeout_count += 1
                    if timeout_count > 6:
                        break
                    continue
                timeout_count = 0
                for s in readable:
                    data = s.recv(8192)
                    if not data:
                        return
                    if s is client:
                        remote.sendall(data)
                    else:
                        client.sendall(data)
        except Exception:
            pass

    def stop(self):
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass


class SOATScraper:
    IFRAME_URL = "https://webapp.apeseg.org.pe/consulta-soat/"
    LOCAL_PROXY_PORT = 18080
    TURNSTILE_SITEKEY = "0x4AAAAAADyJA_4hEDeVktbR"

    def __init__(self, use_proxy=False, headless=False):
        self.use_proxy = use_proxy
        self.headless = headless
        self.proxy_index = 0
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
        print(f"[*] Proxy forwarder en 127.0.0.1:{self.LOCAL_PROXY_PORT}")

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
        if self.use_proxy and not self.solver:
            self.current_proxy = self._get_next_proxy()
            self.solver = CaptchaSolver(CAPSOLVER_API_KEY, self.current_proxy)

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

        proxy_ok = False
        if self.use_proxy and self.current_proxy:
            host, port, user, password = self._parse_proxy(self.current_proxy)
            proxy_ok = self._test_proxy(self.current_proxy)
            if proxy_ok:
                self._start_local_proxy(host, port, user, password)
                options.add_argument(f"--proxy-server=127.0.0.1:{self.LOCAL_PROXY_PORT}")
                print(f"[*] Proxy CapSolver activo: {host}:{port}")
            else:
                print("[!] Proxy no responde. Continuando SIN proxy (IP local).")
                self.use_proxy = False

        if not self.solver:
            self.solver = CaptchaSolver(CAPSOLVER_API_KEY, None)

        self.driver = uc.Chrome(options=options, version_main=_detect_chrome_version())
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

                if attempt > 1 and self.use_proxy:
                    self._rotate_proxy()

                self.driver.get(BASE_URL)
                self._wait_for_cloudflare()
                title = (self.driver.title or "").lower()
                if "error" in title or "bad gateway" in title or not title:
                    print(f"[!] Pagina no cargo OK (title={title!r}). Posible 502/proxy.")
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
            except Exception as e:
                print(f"[!] Intento {attempt} error: {e}")
                # si el driver quedo en estado invalido, forzar recreacion
                if self.driver:
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = None
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
            for ind in ["captcha incorrecto", "complete la validaci", "se ha superado",
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
                return {"success": True, "placa": placa_val,
                        "soat": soat_reciente,
                        "screenshot_base64": screenshot_b64}
            # 3) si el body cambio drasticamente (navego a /resultados)
            if pre_submit_body and body and body != pre_submit_body:
                if any(k in low for k in ["vigente", "aseguradora", "certificado",
                                          "no se encontr", "resultado", "placa"]):
                    html = self.driver.page_source
                    print(f"\n[*] Respuesta (DOM):\n{body[:800]}")
                    success = not any(ind in low for ind in
                                      ["no se encontr", "no existe", "error consultando"])
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
