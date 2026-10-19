import base64
import select
import socket
import threading


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
        self.local_port = self.server_socket.getsockname()[1]
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

            remote_socket = None
            try:
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
                while b"\r\n\r\n" not in response and len(response) < 8192:
                    chunk = remote_socket.recv(4096)
                    if not chunk:
                        break
                    response += chunk

                status_line = response.split(b"\r\n")[0].decode(errors="ignore")
                head, _, extra = response.partition(b"\r\n\r\n")

                if " 200" in status_line:
                    client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    if extra:
                        client_socket.sendall(extra)
                    self._tunnel(client_socket, remote_socket)
                else:
                    print(f"[!] Proxy remoto rechazó {target}: {status_line}")
                    client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            finally:
                if remote_socket:
                    try:
                        remote_socket.close()
                    except Exception:
                        pass
                try:
                    client_socket.close()
                except Exception:
                    pass
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
        finally:
            for s in (client, remote):
                try:
                    s.close()
                except Exception:
                    pass

    def stop(self):
        self._running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
