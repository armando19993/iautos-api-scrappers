import requests
import random
import string

# Generamos un ID de sesión aleatorio para asegurar que no esté expirada
random_session = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

# Cambia "zboBDCcwDz" por la nueva sesión aleatoria
username = f"A0475E74211D4969-resi-country_PE-rotate_0m-session_{random_session}"
password = "Meches1256"
host = "proxy.capsolver.com"
port = "36583"

proxy = f'http://{username}:{password}@{host}:{port}'
proxy_dict = {
    "http": proxy,
    "https": proxy
}

print("Iniciando petición a través del proxy...")

try:
    # Añadimos timeout=15 (15 segundos de espera máxima)
    response = requests.get("https://api.ipify.org", proxies=proxy_dict, timeout=15)
    print("¡Éxito! Tu IP con proxy es:", response.text)
except requests.exceptions.ProxyError as e:
    print("Error de conexión al proxy. Revisa si tus credenciales son correctas o si tienes saldo en CapSolver.")
except requests.exceptions.ReadTimeout:
    print("Timeout: El proxy no respondió a tiempo. La sesión o el puerto podrían estar inactivos.")
except Exception as e:
    print("Ocurrió un error inesperado:", e)