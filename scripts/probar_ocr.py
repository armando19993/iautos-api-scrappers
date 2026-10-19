"""Compara variantes de OCR sobre una imagen de tarjeta Sunarp (herramienta manual).

Uso: python scripts/probar_ocr.py ruta/a/imagen.png

Variantes: sin preprocesar | 2x + umbral 150 | 2x + umbral 120 | 2x + umbral 180,
cada una con psm 6 y psm 4. Solo imprime las lineas MOTOR, SERIE y MODELO.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytesseract
from PIL import Image

import app.procesos.sunarp.ocr as sunarp_ocr  # configura TESSERACT_CMD / TESSDATA_PREFIX
from app.procesos.sunarp.parser import _LABEL_RE

CAMPOS = ("SERIE", "MOTOR", "MODELO")
ESCALA = 2


def binarizar(img, umbral):
    gray = img.convert("L").resize((img.width * ESCALA, img.height * ESCALA), Image.LANCZOS)
    return gray.point(lambda p: 255 if p > umbral else 0)


def leer(img, psm):
    cfg = f"--psm {psm}"
    try:
        return pytesseract.image_to_string(img, lang="spa", config=cfg)
    except pytesseract.TesseractNotFoundError:
        raise
    except Exception:
        return pytesseract.image_to_string(img, config=cfg)  # sin paquete 'spa'


def lineas_clave(texto):
    out = []
    for line in texto.splitlines():
        m = _LABEL_RE.match(line.strip())
        if m and m.group(1).upper() in CAMPOS:
            out.append(line.strip())
    return out or ["(no se leyeron lineas MOTOR/SERIE/MODELO)"]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    img = Image.open(sys.argv[1])
    variantes = [
        ("sin preprocesar", img),
        ("2x umbral 150", binarizar(img, 150)),
        ("2x umbral 120", binarizar(img, 120)),
        ("2x umbral 180", binarizar(img, 180)),
    ]
    try:
        for nombre, im in variantes:
            for psm in (6, 4):
                print(f"== {nombre} | psm {psm}")
                for line in lineas_clave(leer(im, psm)):
                    print(f"   {line}")
    except pytesseract.TesseractNotFoundError:
        sys.exit("Tesseract no instalado o no encontrado (defina TESSERACT_CMD)")


if __name__ == "__main__":
    main()
