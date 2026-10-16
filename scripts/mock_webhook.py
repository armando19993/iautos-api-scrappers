"""Receptor local de prueba para el webhook de Sunarp (solo desarrollo).

Uso: python scripts/mock_webhook.py [puerto] [--modo ok|error|sin-id|5xx]
Imprime cada payload recibido y responde segun el modo:
  ok      {"success": true, "vehiculoId": N, "accion": "insertado"}  (default; N incrementa)
  error   {"success": false, "error": "error simulado"}
  sin-id  {"success": true}
  5xx     HTTP 503
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PORT = int(args[0]) if args else 9000
MODO = sys.argv[sys.argv.index("--modo") + 1] if "--modo" in sys.argv else "ok"
contador = [1000]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        print(f"\n<< {self.headers.get('Authorization', '(sin Authorization)')}")
        print(json.dumps(body, ensure_ascii=False, indent=2), flush=True)
        code = 200
        if MODO == "error":
            out = {"success": False, "error": "error simulado"}
        elif MODO == "sin-id":
            out = {"success": True}
        elif MODO == "5xx":
            out, code = {"success": False, "error": "503 simulado"}, 503
        else:
            contador[0] += 1
            out = {"success": True, "vehiculoId": contador[0], "accion": "insertado"}
        data = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        print(f">> {code} {out}", flush=True)


print(f"Mock webhook en http://127.0.0.1:{PORT}/hook  (modo={MODO}). Ctrl+C para salir.")
HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
