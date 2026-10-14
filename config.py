import os
from dotenv import load_dotenv

load_dotenv()

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")
BASE_URL = "https://www.apeseg.org.pe/consultas-soat/"
MTC_BASE_URL = "https://rec.mtc.gob.pe"
SUNARP_URL = "https://consultavehicular.sunarp.gob.pe"

CAPSOLVER_PROXIES = [
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_7zPSq3W7KP:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_VsX3yr5SYa:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_NCMKbSuPvI:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_WMV80ODSI5:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_w3coDMMWoF:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_K1acTzFE0l:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_xcc5ePeAU5:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_houshocq2m:2O0jDAt2",
    "proxy.capsolver.com:36583:84BC6CBF8DABAA37-resi-country_PE-rotate_0m-session_bdZDkqU7w7:2O0jDAt2",
]