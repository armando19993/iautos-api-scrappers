"""Prueba de estabilidad Sunarp con validacion y reporte HTML en vivo (NO envia al webhook).

Uso:
  python -m tests.carga.test_sunarp [--total 30] [--workers 5] [--modo http|browser] [--headless 1|0]

- modo http: SunarpHTTP, el mismo cliente que usa el pool de POST /sunarp.
- modo browser: SunarpScraper (Chrome). Con --headless 0 se ve el navegador.
Las placas se eligen al azar de PLACAS. El reporte se reescribe tras cada consulta
en reportes/sunarp_<fecha>.html y se recarga solo cada 3s.
"""
import argparse
import base64
import html
import io
import json
import os
import queue
import random
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PIL import Image

warnings.filterwarnings("ignore")

PLACAS = [
    "C5Y146", "F4E332", "C3Q151", "BTF227", "CAN029", "CKH548", "CLS145", "BWL634",
    "BKI238", "CMX151", "W5L610", "BFQ547", "Z6V347", "AZC613", "AXW051", "D6Q555",
    "BYM383", "CNN500", "BCO474", "CCY022", "CJP006", "CHS280",
]

ESTADO_COLOR = {"OK": "#1a7f37", "ADVERTENCIA": "#9a6700", "FALLO": "#cf222e", "EN CURSO": "#57606a"}


def _norm(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _clasificar_error(err):
    e = (err or "").lower()
    if "capsolver" in e or "token" in e:
        return "Turnstile/CapSolver"
    if "timeout" in e or "timed out" in e:
        return "Timeout"
    m = re.search(r"http (\d{3})", e)
    if m:
        return f"HTTP {m.group(1)}"
    if "connect" in e or "network" in e or "ssl" in e:
        return "Red/conexion"
    return "Otro"


def validar(placa, r):
    """Devuelve (estado, checks, notas). checks: lista de (nombre, ok|warn|fail|na, detalle)."""
    checks, notas = [], []
    if not r.get("success"):
        cat = _clasificar_error(r.get("error"))
        checks.append(("success", "fail", f"{cat}: {str(r.get('error'))[:200]}"))
        return "FALLO", checks, notas

    raw = r.get("raw_response")
    if raw is not None:
        cod = raw.get("cod")
        checks.append(("cod == 1", "ok" if cod == 1 else "fail", f"cod={cod} · {raw.get('mensaje')}"))
        model = raw.get("model") or {}
        sedes = model.get("sedes") or []
        placas_sede = [_norm(s.get("placa")) for s in sedes]
        if not sedes:
            checks.append(("placa en sedes", "fail", "sin sedes en la respuesta"))
        elif _norm(placa) in placas_sede:
            checks.append(("placa en sedes", "ok", ", ".join(
                f"{s.get('nombre')} · partida {s.get('numPartida')}" for s in sedes)))
        else:
            checks.append(("placa en sedes", "fail", f"SUNARP devolvio {placas_sede}"))
        if len(sedes) > 1:
            notas.append(f"{len(sedes)} sedes registrales")
        if any(s.get("fgBaja") not in (None, "", "0") for s in sedes):
            notas.append("vehiculo con BAJA (fgBaja)")
        if model.get("msgAlertaRobo"):
            notas.append(f"ALERTA ROBO: {model.get('msgAlertaRobo')}")

    img = r.get("result_image_base64") or ""
    if not img:
        checks.append(("imagen", "fail", "sin imagen"))
    else:
        try:
            raw_b64 = img.split(",", 1)[1] if "," in img else img
            w, h = Image.open(io.BytesIO(base64.b64decode(raw_b64))).size
            ok = w >= 300 and h >= 300
            checks.append(("imagen", "ok" if ok else "warn", f"{w}x{h}"))
        except Exception as e:
            checks.append(("imagen", "fail", f"no decodifica: {e}"))

    ocr = r.get("ocr_text") or ""
    if not ocr:
        checks.append(("OCR", "na", "vacio (tesseract no disponible o sin texto)"))
    elif _norm(placa) in _norm(ocr):
        checks.append(("OCR", "ok", "contiene la placa"))
    else:
        checks.append(("OCR", "warn", "el texto OCR no contiene la placa"))

    niveles = [c[1] for c in checks]
    if "fail" in niveles:
        return "FALLO", checks, notas
    if "warn" in niveles or notas:
        return "ADVERTENCIA", checks, notas
    return "OK", checks, notas


class Reporte:
    def __init__(self, path, meta):
        self.path, self.meta = path, meta
        self.filas, self.lock, self.fin = {}, threading.Lock(), False

    def set(self, i, fila):
        with self.lock:
            self.filas[i] = fila
            self._escribir()

    def cerrar(self, resumen):
        with self.lock:
            self.fin, self.meta["resumen"] = True, resumen
            self._escribir()

    def _escribir(self):
        filas = [self.filas[k] for k in sorted(self.filas)]
        cuenta = {k: sum(1 for f in filas if f["estado"] == k) for k in ESTADO_COLOR}
        refresh = "" if self.fin else '<meta http-equiv="refresh" content="3">'
        chips = " ".join(
            f'<span class="chip" style="background:{c}">{k}: {cuenta[k]}</span>'
            for k, c in ESTADO_COLOR.items() if cuenta[k])
        rows = []
        for f in filas:
            checks = "".join(
                f'<div class="ck {lv}"><b>{html.escape(n)}</b> {html.escape(str(d))}</div>'
                for n, lv, d in f.get("checks", []))
            notas = "".join(f'<div class="nota">{html.escape(n)}</div>' for n in f.get("notas", []))
            img = (f'<a href="{f["img"]}" target="_blank"><img src="{f["img"]}"></a>'
                   if f.get("img") else "")
            rows.append(
                f'<tr><td>{f["i"]:02d}</td><td class="placa">{f["placa"]}</td>'
                f'<td><span class="chip" style="background:{ESTADO_COLOR[f["estado"]]}">{f["estado"]}</span></td>'
                f'<td>{f.get("t", "")}</td><td>{checks}{notas}</td><td>{img}</td></tr>')
        resumen = f'<pre>{html.escape(self.meta.get("resumen", ""))}</pre>' if self.fin else ""
        doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">{refresh}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Prueba Sunarp</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#1f2328}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #d0d7de;padding:6px;vertical-align:top;text-align:left}}
.chip{{color:#fff;border-radius:10px;padding:2px 8px;font-size:12px;white-space:nowrap}}
.placa{{font-family:monospace;font-weight:600}}img{{height:150px;border:1px solid #d0d7de}}
.ck{{font-size:13px}}.ck.ok b{{color:#1a7f37}}.ck.fail b{{color:#cf222e}}.ck.warn b{{color:#9a6700}}.ck.na b{{color:#57606a}}
.nota{{font-size:13px;color:#9a6700;font-weight:600}}pre{{background:#f6f8fa;padding:10px}}
</style></head><body>
<h2>Prueba Sunarp · modo {self.meta['modo']}{' · headless' if self.meta.get('headless') else ''}</h2>
<p>{self.meta['inicio']} · {len(filas)}/{self.meta['total']} consultas · {self.meta['workers']} en paralelo
{'' if self.fin else ' · <i>actualizando…</i>'}</p><p>{chips}</p>{resumen}
<table><tr><th>#</th><th>Placa</th><th>Estado</th><th>Tiempo</th><th>Validacion</th><th>Tarjeta</th></tr>
{''.join(rows)}</table></body></html>"""
        # en Windows el reemplazo falla si el visor tiene el archivo abierto:
        # se reintenta y, si no se puede, se omite esta actualizacion sin cortar la prueba
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(doc)
        for _ in range(10 if self.fin else 3):
            try:
                os.replace(tmp, self.path)
                return
            except PermissionError:
                time.sleep(0.3)
        print("[reporte] no se pudo actualizar el HTML (archivo en uso); se reintenta en la siguiente consulta", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=30)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--modo", choices=["http", "browser"], default="http")
    ap.add_argument("--headless", type=int, default=1)
    args = ap.parse_args()

    os.makedirs("reportes", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.abspath(f"reportes/sunarp_{args.modo}_{stamp}.html")
    rep = Reporte(path, {"modo": args.modo, "headless": args.modo == "browser" and args.headless,
                         "total": args.total, "workers": args.workers,
                         "inicio": datetime.now().strftime("%d/%m/%Y %H:%M:%S")})
    print(f"### REPORTE: {path}", flush=True)

    placas = [random.choice(PLACAS) for _ in range(args.total)]

    if args.modo == "http":
        from app.procesos.sunarp.cliente_http import SunarpHTTP
        pool = queue.Queue()
        clientes = [SunarpHTTP() for _ in range(args.workers)]
        for c in clientes:
            pool.put(c)

        def consultar(placa):
            c = pool.get()
            try:
                return c.consultar(placa)
            finally:
                pool.put(c)
    else:
        from app.procesos.sunarp.scraper_selenium import SunarpScraper
        clientes = []

        def consultar(placa):
            s = SunarpScraper(headless=bool(args.headless))
            try:
                s.start()
                return s.consultar(placa)
            except Exception as e:
                return {"success": False, "placa": placa, "error": f"EXC {e}"}
            finally:
                s.stop()

    partidas, resultados = {}, []
    plock = threading.Lock()

    def run(i):
        placa = placas[i - 1]
        rep.set(i, {"i": i, "placa": placa, "estado": "EN CURSO"})
        t = time.time()
        try:
            r = consultar(placa)
        except Exception as e:
            r = {"success": False, "placa": placa, "error": f"EXC {e}"}
        dt = time.time() - t
        estado, checks, notas = validar(placa, r)
        sedes = ((r.get("raw_response") or {}).get("model") or {}).get("sedes") or []
        partida = ",".join(sorted(str(s.get("numPartida")) for s in sedes))
        if partida:
            with plock:
                previa = partidas.setdefault(placa, partida)
            if previa != partida:
                checks.append(("misma partida que antes", "fail", f"{previa} vs {partida}"))
                estado = "FALLO"
        rep.set(i, {"i": i, "placa": placa, "estado": estado, "t": f"{dt:.1f}s",
                    "checks": checks, "notas": notas, "img": r.get("result_image_base64")})
        detalle = "; ".join(f"{n}={lv}" for n, lv, _ in checks if lv != "ok") or "todo ok"
        print(f"### PRUEBA {i:02d}: {estado} | {placa} | {dt:.1f}s | {detalle}"
              + (f" | {'; '.join(notas)}" if notas else ""), flush=True)
        resultados.append({"i": i, "placa": placa, "estado": estado, "t": round(dt, 1),
                           "checks": checks, "notas": notas, "error": r.get("error"),
                           "cod": (r.get("raw_response") or {}).get("cod"),
                           "mensaje": (r.get("raw_response") or {}).get("mensaje")})

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(run, range(1, args.total + 1)))

    for c in clientes:
        try:
            c.close()
        except Exception:
            pass

    cuenta = {k: sum(1 for r in resultados if r["estado"] == k) for k in ("OK", "ADVERTENCIA", "FALLO")}
    prom = sum(r["t"] for r in resultados) / len(resultados)
    resumen = (f"OK {cuenta['OK']} · ADVERTENCIA {cuenta['ADVERTENCIA']} · FALLO {cuenta['FALLO']} "
               f"de {args.total} · promedio {prom:.1f}s · placas distintas {len(set(placas))}")
    rep.cerrar(resumen)
    with open(path.replace(".html", ".json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(resultados, key=lambda r: r["i"]), fh, ensure_ascii=False, indent=1)
    print(f"### RESUMEN: {resumen}", flush=True)


if __name__ == "__main__":
    main()
