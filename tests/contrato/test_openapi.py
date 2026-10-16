"""Test de contrato: la API publicada no cambia sin que se note.

Compara el OpenAPI y la tabla de rutas de la app contra tests/contrato/openapi.snapshot.json
(como texto, respetando el orden: es el orden en que se ven en /docs) y verifica que la
documentacion siga protegida con Basic Auth.

Uso (desde la raiz del repo):
  python -m tests.contrato.test_openapi              # verificar
  python -m tests.contrato.test_openapi --actualizar # regenerar el snapshot (cambio intencional)
"""
import asyncio
import difflib
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import api

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.snapshot.json")
RUTAS_PROTEGIDAS = ("/docs", "/redoc", "/openapi.json")


def contrato_actual(app=None):
    app = app or api.app
    rutas = [
        {"path": r.path, "methods": sorted(getattr(r, "methods", None) or []),
         "en_schema": getattr(r, "include_in_schema", True)}
        for r in app.routes
    ]
    return {"openapi": app.openapi(), "rutas": rutas}


def serializar(contrato):
    return json.dumps(contrato, ensure_ascii=False, indent=2) + "\n"


def comparar(contrato, esperado_txt):
    """Devuelve el diff (lista de lineas) entre el contrato y el snapshot; vacio si son iguales."""
    actual_txt = serializar(contrato)
    if actual_txt == esperado_txt:
        return []
    return list(difflib.unified_diff(
        esperado_txt.splitlines(), actual_txt.splitlines(),
        fromfile="snapshot", tofile="actual", lineterm="", n=2))


async def _status_sin_auth(app, path):
    # llamada ASGI directa: TestClient no decodifica el header WWW-Authenticate
    # (realm="Documentación" viaja en latin-1, valido en HTTP)
    estado = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            estado["status"] = msg["status"]

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
             "query_string": b"", "headers": [], "client": ("test", 1), "server": ("test", 80)}
    await app(scope, receive, send)
    return estado.get("status")


def verificar_docs_protegidas(app=None):
    app = app or api.app
    estados = {p: asyncio.run(_status_sin_auth(app, p)) for p in RUTAS_PROTEGIDAS}
    abiertas = {p: s for p, s in estados.items() if s != 401}
    assert not abiertas, f"rutas de documentacion sin Basic Auth: {abiertas}"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    contrato = contrato_actual()

    if "--actualizar" in sys.argv:
        with open(SNAPSHOT, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(serializar(contrato))
        ops = sum(len(v) for v in contrato["openapi"]["paths"].values())
        print(f"snapshot actualizado: {ops} operaciones, {len(contrato['rutas'])} rutas")
        return 0

    if not os.path.exists(SNAPSHOT):
        print(f"FALLO: no existe {SNAPSHOT}; generarlo con --actualizar")
        return 1
    with open(SNAPSHOT, encoding="utf-8") as fh:
        diff = comparar(contrato, fh.read())
    if diff:
        print("FALLO: el contrato de la API cambio respecto al snapshot")
        print("\n".join(diff[:200]))
        if len(diff) > 200:
            print(f"... ({len(diff) - 200} lineas mas)")
        print("Si el cambio es intencional: python -m tests.contrato.test_openapi --actualizar")
        return 1
    print("ok contrato OpenAPI y rutas iguales al snapshot")

    verificar_docs_protegidas()
    print("ok /docs, /redoc y /openapi.json piden Basic Auth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
