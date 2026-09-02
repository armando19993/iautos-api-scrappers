import undetected_chromedriver as uc
import json, time
from chrome_utils import create_driver

options = uc.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
driver = create_driver(options)

# Interceptar requests ANTES de cargar la pagina
driver.execute_cdp_cmd("Network.enable", {})

# Cargar pagina
driver.get("https://consultavehicular.sunarp.gob.pe/consulta-vehicular")
time.sleep(5)

# Obtener cookies
cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})
print("=== COOKIES ===")
for c in cookies.get("cookies", []):
    print(f"  {c['name']} = {c['value'][:60]}... domain={c.get('domain','')}")

# Buscar scripts de Angular
scripts = driver.execute_script(
    "return Array.from(document.querySelectorAll('script[src]')).map(s=>s.src)"
)
print("\n=== SCRIPTS ===")
for s in scripts:
    print(f"  {s}")

# Buscar configuracion de API en scripts inline
config = driver.execute_script("""
    var results = [];
    var scripts = document.querySelectorAll('script');
    scripts.forEach(function(s) {
        var text = s.textContent || '';
        if (text.includes('api') || text.includes('client') || text.includes('secret') || text.includes('token') || text.includes('header')) {
            if (text.length > 10 && text.length < 5000) {
                results.push(text.substring(0, 1000));
            }
        }
    });
    return results;
""")
print("\n=== INLINE SCRIPTS ===")
for i, c in enumerate(config[:5]):
    print(f"  [{i}] {c[:300]}...")

# Buscar en Angular environment/config
env_config = driver.execute_script("""
    var results = [];
    // Buscar variables globales de Angular
    try { if (window.__env) results.push(JSON.stringify(window.__env)); } catch(e) {}
    try { if (window.environment) results.push(JSON.stringify(window.environment)); } catch(e) {}
    // Buscar en el source de los scripts bundle
    var perf = performance.getEntriesByType('resource');
    var jsFiles = perf.filter(function(e) { return e.name.endsWith('.js'); });
    return jsFiles.map(function(f) { return f.name; });
""")
print("\n=== JS BUNDLES ===")
for item in env_config:
    print(f"  {item[:150]}")

driver.quit()
