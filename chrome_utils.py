"""Utilidades compartidas para lanzar Chrome con undetected_chromedriver.

Resuelve el error clasico al arrancar cualquier scraper:

    SessionNotCreatedException: This version of ChromeDriver only supports
    Chrome version 150. Current browser version is 152.0.7977.65

undetected_chromedriver descarga el ChromeDriver de la version mayor que se le
indique en ``version_main``; si esa version no coincide con el Chrome instalado
la sesion no arranca. Este modulo:

1. ``detect_chrome_version()``: detecta la version mayor del Chrome instalado.
   - Windows: metadatos (VERSIONINFO) del chrome.exe, carpeta de instalacion
     ``<Application>\\<version>`` o registro (BLBeacon / Google Update).
   - Linux / macOS: ``chrome --version``.
   Se puede forzar con la variable de entorno ``CHROME_VERSION_MAIN``
   (por ejemplo ``CHROME_VERSION_MAIN=152``).
2. ``create_driver(options)``: lanza ``uc.Chrome`` con esa version y, si aun
   asi el driver no coincide (por ejemplo Chrome se acaba de actualizar), lee
   la version real del mensaje de error y reintenta una vez con ella.

Todos los scrapers (SOAT, MTC, Sunarp) crean el navegador a traves de
``create_driver`` para compartir este comportamiento.
"""
import copy
import os
import re
import struct
import subprocess
import sys
import threading
import time

import undetected_chromedriver as uc
from selenium.common.exceptions import SessionNotCreatedException

try:
    from dotenv import load_dotenv

    load_dotenv()  # permite definir CHROME_VERSION_MAIN en .env
except ImportError:  # python-dotenv es opcional para este modulo
    pass

ENV_VERSION_MAIN = "CHROME_VERSION_MAIN"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")
# Mensaje de chromedriver cuando no coincide con el navegador:
# "... Current browser version is 152.0.7977.65; For documentation ..."
_MISMATCH_RE = re.compile(r"Current browser version is (\d+)\.")

_IS_WINDOWS = sys.platform.startswith("win")

# uc.Chrome parchea y copia el mismo chromedriver en disco al arrancar; varios
# hilos a la vez chocan por ese archivo (WinError 32 / 183). Se serializa el arranque.
_DRIVER_LOCK = threading.Lock()


def _major(text):
    """Extrae la version mayor (int) de un texto tipo "152.0.7977.65"."""
    m = _VERSION_RE.search(text or "")
    return int(m.group(1)) if m else None


def _uc_chrome_executable():
    """Binario de Chrome que undetected_chromedriver va a lanzar (o None)."""
    finder = getattr(uc, "find_chrome_executable", None)
    if not finder:
        return None
    try:
        return finder()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _win_file_version(path):
    """Lee la version (recurso VERSIONINFO) de un .exe con la API de Windows."""
    import ctypes
    from ctypes import wintypes

    ver = ctypes.windll.version
    ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, wintypes.LPDWORD]
    ver.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    ver.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    ]
    ver.GetFileVersionInfoW.restype = wintypes.BOOL
    ver.VerQueryValueW.argtypes = [
        wintypes.LPCVOID, wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.UINT),
    ]
    ver.VerQueryValueW.restype = wintypes.BOOL

    size = ver.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(path, 0, size, data):
        return None
    ptr = wintypes.LPVOID()
    length = wintypes.UINT()
    if not ver.VerQueryValueW(data, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    if length.value < 16:
        return None
    # VS_FIXEDFILEINFO: dwSignature, dwStrucVersion, dwFileVersionMS, dwFileVersionLS, ...
    signature, _, ms, ls = struct.unpack("<4I", ctypes.string_at(ptr, 16))
    if signature != 0xFEEF04BD:
        return None
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def _win_install_dir_version(exe_path):
    """Chrome instala sus binarios en <Application>\\<version>\\ ; leemos esa carpeta."""
    app_dir = os.path.dirname(exe_path)
    found = []
    try:
        for name in os.listdir(app_dir):
            if _VERSION_RE.fullmatch(name) and os.path.isdir(os.path.join(app_dir, name)):
                found.append(tuple(int(part) for part in name.split(".")))
    except OSError:
        return None
    return ".".join(str(part) for part in max(found)) if found else None


def _win_registry_version():
    """Version registrada por Chrome / Google Update en el registro de Windows."""
    import winreg

    chrome_guid = "{8A69D345-D564-463C-AFF1-A69D9E530F96}"  # Google Chrome (stable)
    keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon", "version"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Update\Clients\%s" % chrome_guid, "pv"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Update\Clients\%s" % chrome_guid, "pv"),
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Update\Clients\%s" % chrome_guid, "pv"),
    )
    for hive, path, name in keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        version = _major(str(value))
        if version:
            return version
    return None


def _win_chrome_candidates():
    """Rutas posibles de chrome.exe (App Paths del registro + carpetas estandar)."""
    paths = []
    try:
        import winreg

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                    hive, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
                ) as key:
                    paths.append(winreg.QueryValue(key, None))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "PROGRAMW6432"):
        base = os.environ.get(env)
        if base:
            paths.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    return paths


def _detect_windows():
    candidates = []
    found = _uc_chrome_executable()  # primero el binario que uc va a lanzar
    if found:
        candidates.append(found)
    candidates.extend(_win_chrome_candidates())

    seen = set()
    for exe in candidates:
        exe = os.path.normpath(exe)
        if exe.lower() in seen or not os.path.isfile(exe):
            continue
        seen.add(exe.lower())
        for reader in (_win_file_version, _win_install_dir_version):
            try:
                version = _major(reader(exe))
            except Exception:
                version = None
            if version:
                return version, exe

    try:
        version = _win_registry_version()
    except Exception:
        version = None
    return version, None


# ---------------------------------------------------------------------------
# Linux / macOS
# ---------------------------------------------------------------------------

def _posix_binary_version(binary):
    try:
        out = subprocess.check_output(
            [binary, "--version"], stderr=subprocess.DEVNULL, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _major(out.decode(errors="ignore"))


def _detect_posix():
    candidates = []
    found = _uc_chrome_executable()
    if found:
        candidates.append(found)
    candidates += [
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    seen = set()
    for binary in candidates:
        if binary in seen:
            continue
        seen.add(binary)
        version = _posix_binary_version(binary)
        if version:
            return version, binary
    return None, None


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def detect_chrome():
    """Devuelve ``(version_mayor, ruta_binario)``; cualquiera puede ser None."""
    forced = os.environ.get(ENV_VERSION_MAIN, "").strip()
    if forced:
        if forced.isdigit():
            print(f"[Chrome] Version forzada por {ENV_VERSION_MAIN}: {forced}")
            return int(forced), None
        print(f"[Chrome] {ENV_VERSION_MAIN}={forced!r} no es un numero, se ignora")

    try:
        version, binary = _detect_windows() if _IS_WINDOWS else _detect_posix()
    except Exception as e:  # la deteccion nunca debe impedir el arranque
        print(f"[Chrome] Error detectando version: {e}")
        version, binary = None, None

    if version:
        print(f"[Chrome] Version detectada: {version}" + (f" ({binary})" if binary else ""))
    else:
        print("[Chrome] No se pudo detectar la version instalada; "
              "se usara el ChromeDriver estable mas reciente")
    return version, binary


def detect_chrome_version():
    """Version mayor del Chrome instalado (int) o None si no se pudo detectar."""
    return detect_chrome()[0]


def _browser_version_from_error(message):
    m = _MISMATCH_RE.search(message or "")
    return int(m.group(1)) if m else None


def _release_cached_driver(timeout=5.0):
    """Espera a que el ChromeDriver cacheado deje de estar en uso y lo borra.

    Tras un intento fallido Windows puede tardar unos milisegundos en liberar
    el .exe; si undetected_chromedriver no puede reemplazarlo reutiliza el
    driver viejo y el reintento fallaria con el mismo error.
    """
    try:
        path = uc.Patcher().executable_path
    except Exception:
        return False
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)


def create_driver(options=None, version_main=None, retry_on_mismatch=True, **kwargs):
    """Crea un ``uc.Chrome`` con el ChromeDriver que corresponde al Chrome instalado.

    - ``version_main``: version mayor a usar; si es None se detecta automaticamente.
    - ``options`` no se modifica: ``uc.Chrome`` altera el objeto y prohibe
      reutilizarlo, asi que cada intento trabaja sobre una copia.
    - ``kwargs`` se pasan tal cual a ``uc.Chrome`` (user_data_dir, headless, ...).

    Si ChromeDriver no coincide con el navegador (Chrome recien actualizado,
    deteccion incorrecta, etc.) se toma la version real del mensaje de error
    y se reintenta una sola vez con ella.
    """
    if version_main is None:
        version_main = detect_chrome_version()

    with _DRIVER_LOCK:
        try:
            return uc.Chrome(options=copy.deepcopy(options), version_main=version_main, **kwargs)
        except SessionNotCreatedException as exc:
            actual = _browser_version_from_error(str(exc))
            if not retry_on_mismatch or not actual or actual == version_main:
                raise
            print(f"[Chrome] ChromeDriver {version_main or 'auto'} no coincide con Chrome {actual}; "
                  f"reintentando con ChromeDriver {actual}")
            if not kwargs.get("driver_executable_path"):
                _release_cached_driver()
            return uc.Chrome(options=copy.deepcopy(options), version_main=actual, **kwargs)
