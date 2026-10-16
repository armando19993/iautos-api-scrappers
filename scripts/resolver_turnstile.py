"""Resuelve un Cloudflare Turnstile con CapSolver (herramienta manual).

Uso: python scripts/resolver_turnstile.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import time
from app.core.config import CAPSOLVER_API_KEY, CAPSOLVER_PROXIES


API_URL = "https://api.capsolver.com"


def solve_turnstile(website_url, site_key, proxy=None):
    """Resuelve Cloudflare Turnstile y retorna el token"""
    task = {
        "type": "AntiTurnstileTask",
        "websiteURL": website_url,
        "websiteKey": site_key,
    }
    
    if proxy:
        task["proxy"] = proxy
        print(f"[*] Usando proxy: {proxy}")
    
    payload = {
        "clientKey": CAPSOLVER_API_KEY,
        "task": task,
    }

    resp = requests.post(f"{API_URL}/createTask", json=payload)
    resp_json = resp.json()
    print("[Step 1] createTask response:", resp_json)

    if resp_json.get("errorId") != 0:
        return {"success": False, "error": resp_json.get("errorDescription")}

    task_id = resp_json["taskId"]
    print("[Step 2] Task ID:", task_id)

    deadline = time.time() + 60
    while time.time() < deadline:
        time.sleep(3)
        resp = requests.post(
            f"{API_URL}/getTaskResult",
            json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id}
        )
        resp_json = resp.json()
        print("[Step 3] getTaskResult:", resp_json)

        if resp_json.get("status") == "ready":
            solution = resp_json.get("solution", {})
            token = solution.get("token", "")
            print("[Step 4] Token:", token[:50] + "...")
            return {"success": True, "token": token}

        if resp_json.get("status") == "failed":
            return {"success": False, "error": resp_json.get("errorDescription")}

    return {"success": False, "error": "Timeout"}


response_cloudflare = solve_turnstile(
    "https://webapp.apeseg.org.pe/consulta-soat/",
    "TU_SITEKEY_AQUI"  # Reemplaza con el sitekey real
)
print("response_cloudflare:", response_cloudflare)
