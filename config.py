import os
from dotenv import load_dotenv

load_dotenv()

CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "")
BASE_URL = "https://www.apeseg.org.pe/consultas-soat/"
MTC_BASE_URL = "https://rec.mtc.gob.pe"
SUNARP_URL = "https://consultavehicular.sunarp.gob.pe"

CAPSOLVER_PROXIES = [
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_lh3uapO7oN:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_Koyxzq6M0L:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_TzufhVGvc6:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_WKCiGwPxCV:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_kFxhLJZGia:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_e7JaWaAgEz:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_mXI80JrsoF:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_D3M2X6185P:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_vThZNkMzWJ:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_GmzOk22eCW:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_HpiSQMBhBb:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_ET2XwzKJkc:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_xT3d8rnFbM:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_layscLPFxr:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_DDugeNBvY9:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_TfzT7Prks1:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_l6hKbtSZzm:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_g2zFet3lm3:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_QcNz35D1Y2:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_0uk3BCX9YT:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_CYCueC7viD:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_129IclXh3k:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_NRsl024oLs:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_rrAVVhgEQs:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_LhKTzdHR16:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_N350mdOHDX:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_ttmY6qqTEw:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_wTZfyJoKbE:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_zJlUK7nxvk:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_NhfBGdzywQ:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_Twi7kiOiaK:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_W11NDZTaec:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_CqJsPwLSmd:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_2bTGvoqos4:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_kvxWt7WVLb:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_3TB4bPJSJt:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_T4Y9EizLuH:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_JlmX86Gqo1:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_LoVM1S8u8U:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_ebsG0bbLnl:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_04DvCLL8xC:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_QtFIrlnUuq:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_AaNR75RR6E:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_1r7FFGtQS9:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_dHpZuPNZZ9:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_WWmEZp3k8K:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_srGaRu7x3F:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_smBbixPT0d:Meches1256",
    "proxy.capsolver.com:36583:A0475E74211D4969-resi-country_PE-rotate_0m-session_T30q4ir4Og:Meches1256",
]