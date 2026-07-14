import argparse
import json
from scraper import SOATScraper


def main():
    parser = argparse.ArgumentParser(description="SOAT Scraper - APESEG")
    parser.add_argument("--placa", "-p", type=str, help="Placa del vehiculo")
    parser.add_argument("--placas", type=str, help="Placas separadas por coma")
    parser.add_argument("--output", "-o", type=str, help="Archivo de salida JSON")
    parser.add_argument("--proxy", action="store_true", help="Usar proxy residencial CapSolver (por defecto OFF)")
    parser.add_argument("--headless", action="store_true", help="Navegador headless (sin GUI, para servidores Linux)")
    args = parser.parse_args()

    placas = []
    if args.placa:
        placas = [args.placa.upper()]
    elif args.placas:
        placas = [p.strip().upper() for p in args.placas.split(",")]
    else:
        print("Uso: python main.py --placa ABC123")
        print("     python main.py --placas ABC123,XYZ789,DEF456")
        print("     python main.py --placa ABC123 --proxy   # usar proxy residencial")
        return

    scraper = SOATScraper(use_proxy=args.proxy, headless=args.headless)
    scraper.start()

    results = []
    try:
        for placa in placas:
            try:
                result = scraper.consultar_soat(placa)
                if not result.get("placa"):
                    result["placa"] = placa
                results.append(result)
                print(f"[{'OK' if result.get('success') else 'FAIL'}] {placa}")
            except Exception as e:
                print(f"[ERROR] {placa}: {e}")
                results.append({"placa": placa, "success": False, "error": str(e)})
    finally:
        scraper.stop()

    output_file = args.output or "resultados.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Resultados guardados en: {output_file}")


if __name__ == "__main__":
    main()
