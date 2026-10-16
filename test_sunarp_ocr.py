"""Pruebas de sunarp_ocr sin Tesseract real (se simula pytesseract). Uso: python test_sunarp_ocr.py"""
import pytesseract
from PIL import Image

import sunarp_ocr
from test_sunarp_parser import REAL

img = Image.new("RGB", (100, 50), "white")

# preprocesado: binaria y ampliada
p = sunarp_ocr.preprocesar(img)
assert p.mode == "L" and p.size == (200, 100) and set(p.get_flattened_data() if hasattr(p, 'get_flattened_data') else p.getdata()) <= {0, 255}
print("ok preprocesar")

# elige la mejor lectura entre psm 6 y 4 (4 lee mejor); gana la primera en empate
MALA = "MARCA: TOYOTA"
llamadas = []
def fake(image, lang=None, config=""):
    llamadas.append((image.mode, config))
    return REAL if "--psm 4" in config else MALA
pytesseract.image_to_string = fake
assert sunarp_ocr.ocr_tarjeta(img) == REAL
assert [c for _, c in llamadas] == ["--psm 6", "--psm 4"] and llamadas[0][0] == "L"
print("ok compara psm 6 vs 4")

# procesado vacio -> fallback a la imagen original (RGB)
llamadas.clear()
def fake2(image, lang=None, config=""):
    llamadas.append(image.mode)
    return "" if image.mode == "L" else REAL
pytesseract.image_to_string = fake2
assert sunarp_ocr.ocr_tarjeta(img) == REAL
assert llamadas == ["L", "L", "RGB"]
print("ok fallback sin preprocesar")

# Tesseract no instalado -> excepcion propia
def boom(*a, **k): raise pytesseract.TesseractNotFoundError()
pytesseract.image_to_string = boom
try:
    sunarp_ocr.ocr_tarjeta(img)
    raise SystemExit("debio fallar")
except sunarp_ocr.TesseractNoInstalado as e:
    assert "no instalado" in str(e)
print("ok tesseract no instalado")

# vacio total -> ''
pytesseract.image_to_string = lambda *a, **k: ""
assert sunarp_ocr.ocr_tarjeta(img) == ""
print("ok ocr vacio")
