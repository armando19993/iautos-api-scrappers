"""OCR (Tesseract) de la tarjeta vehicular de Sunarp, con preprocesado configurable.

Variables de entorno (ver config.py):
  TESSERACT_CMD           ruta a tesseract(.exe); si no se define se busca en rutas tipicas de Windows / PATH
  SUNARP_OCR_PREPROCESS   1/0: escala de grises + ampliacion + umbral (default 1)
  SUNARP_OCR_SCALE        factor de ampliacion (default 2, entre 1 y 4)
  SUNARP_OCR_THRESHOLD    umbral 0-255 para binarizar (default 150; quita la marca de agua gris)
  SUNARP_OCR_PSM          "auto" (prueba 6 y 4 y elige la mejor lectura), "6" o "4"
"""
import os

import pytesseract
from PIL import Image

from app.core.config import (
    TESSERACT_CMD,
    SUNARP_OCR_PREPROCESS,
    SUNARP_OCR_SCALE,
    SUNARP_OCR_THRESHOLD,
    SUNARP_OCR_PSM,
)
from app.procesos.sunarp.parser import parse_ocr_text, puntaje


class TesseractNoInstalado(RuntimeError):
    """No se encontro el ejecutable de Tesseract."""


def _configurar_tesseract():
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    else:
        for p in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break
    user_tessdata = os.path.expanduser(r"~\.tesseract\tessdata")
    if os.path.exists(user_tessdata):
        os.environ["TESSDATA_PREFIX"] = user_tessdata


_configurar_tesseract()


def preprocesar(img: Image.Image) -> Image.Image:
    """Gris -> ampliar -> umbral. Devuelve una imagen binaria ('L')."""
    gray = img.convert("L")
    if SUNARP_OCR_SCALE > 1:
        gray = gray.resize(
            (int(gray.width * SUNARP_OCR_SCALE), int(gray.height * SUNARP_OCR_SCALE)),
            Image.LANCZOS,
        )
    return gray.point(lambda p: 255 if p > SUNARP_OCR_THRESHOLD else 0)


def _leer(img: Image.Image, psm: int) -> str:
    cfg = f"--psm {psm}"
    try:
        text = pytesseract.image_to_string(img, lang="spa", config=cfg)
    except pytesseract.TesseractNotFoundError:
        raise
    except Exception:
        text = pytesseract.image_to_string(img, config=cfg)  # sin paquete de idioma 'spa'
    return text.strip()


def _psms() -> list:
    return [6, 4] if SUNARP_OCR_PSM == "auto" else [int(SUNARP_OCR_PSM)]


def ocr_tarjeta(img: Image.Image) -> str:
    """Devuelve el texto OCR ('' si no se leyo nada). Lanza TesseractNoInstalado si falta el binario."""
    try:
        candidatos = []
        if SUNARP_OCR_PREPROCESS:
            proc = preprocesar(img)
            candidatos = [t for t in (_leer(proc, psm) for psm in _psms()) if t]
        if not candidatos:
            # sin preprocesado, o el procesado devolvio vacio: lectura original
            raw = _leer(img, _psms()[0])
            candidatos = [raw] if raw else []
    except pytesseract.TesseractNotFoundError:
        raise TesseractNoInstalado(
            "Tesseract no instalado o no encontrado (instálelo o defina TESSERACT_CMD)"
        )
    if not candidatos:
        return ""
    # la primera lectura gana los empates (psm 6 va primero)
    return max(candidatos, key=lambda t: puntaje(parse_ocr_text(t, 0, "X")))
