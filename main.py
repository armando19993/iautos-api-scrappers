import argparse
import json
from app.procesos.soat.scraper import SOATScraper
from app.procesos.mtc.scraper import MTCScraper
from app.procesos.sunarp.scraper_selenium import SunarpScraper


def main():
    parser = argparse.ArgumentParser(
        description="Scraper - SOAT (APESEG) / CITV (MTC) / Sunarp (consulta vehicular)"
    )
    parser.add_argument("--placa", "-p", type=str, help="Placa del vehiculo")
    parser.add_argument("--placas", type=str, help="Placas separadas por coma")
    parser.add_argument("--output", "-o", type=str, help="Archivo de salida JSON")
    parser.add_argument("--proxy", action="store_true", help="Usar proxy residencial CapSolver (solo SOAT)")
    parser.add_argument("--headless", action="store_true", help="Navegador headless (solo SOAT)")
    parser.add_argument("--mtc", action="store_true", help="Usar scraper MTC CITV (no requiere navegador)")
    parser.add_argument("--sunarp", action="store_true", help="Usar scraper Sunarp consulta vehicular (Selenium + OCR)")
    args = parser.parse_args()

    if not args.placa and not args.placas:
        print("Uso: python main.py --placa ABC123")
        print("     python main.py --placas ABC123,XYZ789")
        print("     python main.py --placa ABC123 --mtc   # MTC CITV")
        print("     python main.py --placa ABC123 --sunarp   # Sunarp vehicular")
        return

    placas = []
    if args.placa:
        placas = [args.placa.upper()]
    elif args.placas:
        placas = [p.strip().upper() for p in args.placas.split(",")]

    if args.sunarp:
        _run_sunarp(placas, args.output or "resultados_sunarp.json")
    elif args.mtc:
        _run_mtc(placas, args.output or "resultados_mtc.json")
    else:
        _run_soat(placas, args.output or "resultados.json", args.proxy, args.headless)


def _run_soat(placas, output_file, use_proxy, headless):
    scraper = SOATScraper(use_proxy=use_proxy, headless=headless)
    scraper.start()
    results = []
    try:
        for placa in placas:
            try:
                result = scraper.consultar_soat(placa)
                if not result.get("placa"):
                    result["placa"] = placa
                results.append(result)
                print(f"[{'OK' if result.get('success') else 'FAIL'}] SOAT {placa}")
            except Exception as e:
                print(f"[ERROR] SOAT {placa}: {e}")
                results.append({"placa": placa, "success": False, "error": str(e)})
    finally:
        scraper.stop()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Resultados SOAT guardados en: {output_file}")


def _run_sunarp(placas, output_file):
    scraper = SunarpScraper()
    scraper.start()
    results = []
    try:
        for placa in placas:
            try:
                result = scraper.consultar(placa)
                if not result.get("placa"):
                    result["placa"] = placa
                results.append(result)
                print(f"[{'OK' if result.get('success') else 'FAIL'}] Sunarp {placa}")
            except Exception as e:
                print(f"[ERROR] Sunarp {placa}: {e}")
                results.append({"placa": placa, "success": False, "error": str(e)})
    finally:
        scraper.stop()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Resultados Sunarp guardados en: {output_file}")


def _run_mtc(placas, output_file):
    scraper = MTCScraper()
    scraper.start()
    results = []
    try:
        for placa in placas:
            try:
                result = scraper.consultar(placa)
                if not result.get("placa"):
                    result["placa"] = placa
                results.append(result)
                print(f"[{'OK' if result.get('success') else 'FAIL'}] MTC {placa}")
            except Exception as e:
                print(f"[ERROR] MTC {placa}: {e}")
                results.append({"placa": placa, "success": False, "error": str(e)})
    finally:
        scraper.stop()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[+] Resultados MTC guardados en: {output_file}")


if __name__ == "__main__":
    main()
