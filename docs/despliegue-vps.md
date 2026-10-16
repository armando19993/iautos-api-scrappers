# Guia de despliegue VPS (Ubuntu, 1-2GB RAM)

Stack: Docker + Docker Compose + Nginx Proxy Manager (GUI) para multiples APIs/DBs/frontends con SSL automatico.

## 1. Preparacion del VPS

```bash
# Actualizar sistema
apt update && apt upgrade -y

# Instalar utilidades basicas
apt install -y curl git nano ufw htop unzip

# Firewall: solo abrir lo necesario
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw allow 81 && ufw allow 22 && ufw allow 21 && ufw --force enable
```

## 2. Instalar Docker + Docker Compose

```bash
# Script oficial (instala Docker Engine + Compose plugin)
curl -fsSL https://get.docker.com | sh

# Habilitar Docker al arranque
systemctl enable docker
systemctl start docker

# Verificar
docker --version
docker compose version
```

## 3. Crear red compartida para los contenedores

```bash
docker network create proxy-net
```

Todos los contenedores (APIs, DBs, NPM) usaran esta red para comunicarse entre si.

## 4. Nginx Proxy Manager (reverse proxy con GUI)

```bash
mkdir -p /opt/npm && cd /opt/npm
```

Crear `docker-compose.yml`:

```yaml
services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: npm
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    environment:
      - DB_SQLITE_FILE=/data/database.sqlite
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    networks:
      - proxy-net

networks:
  proxy-net:
    external: true
```

Levantar:

```bash
docker compose up -d
```

Acceder al panel: `http://<IP-VPS>:81`
- Login por defecto: `admin@example.com` / `changeme`
- **Cambiar email y clave al primer login** (te las pide).

## 5. Desplegar la API SOAT Scraper

### 5.1. Subir el codigo al VPS

```bash
# En tu maquina local, desde el directorio del scraper:
scp -r soat-scraper/ root@200.234.233.170:/opt/soat-api/
```

O via git si usas un repo privado.

### 5.2. Crear Dockerfile

En `/opt/soat-api/Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Dependencias del sistema para Chrome (headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 ca-certificates fonts-liberation libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxkbcommon0 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Instalar Chrome estable
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list && \
    apt-get update && apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.3. Crear docker-compose para la API

En `/opt/soat-api/docker-compose.yml`:

```yaml
services:
  soat-api:
    build: .
    container_name: soat-api
    restart: unless-stopped
    environment:
      - CAPSOLVER_API_KEY=CAP-ED00676810599281FD08281DE8F067C0470247E8CA2A439C29EF35C651EC04BB
    networks:
      - proxy-net

networks:
  proxy-net:
    external: true
```

### 5.4. Levantar la API

```bash
cd /opt/soat-api
docker compose up -d --build
docker compose logs -f   # ver logs (Ctrl+C para salir)
```

Verificar que responde dentro del VPS:

```bash
docker exec soat-api curl -s http://localhost:8000/health
# debe responder: {"status":"ok"}
```

## 6. Configurar dominio + SSL en Nginx Proxy Manager

1. Apuntar un subdominio (ej `soat.tudominio.com`) al IP del VPS en tu DNS (registro A).
2. En el panel NPM (`http://<IP-VPS>:81`):
   - **Hosts** -> **Proxy Hosts** -> **Add Proxy Host**
   - **Domain Names**: `soat.tudominio.com`
   - **Forward Hostname**: `soat-api`   (nombre del contenedor)
   - **Forward Port**: `8000`
   - Pestania **SSL**: seleccionar "Request a new SSL Certificate", marcar "Force SSL", aceptar terminos, guardar.
3. Esperar ~30s a que Let's Encrypt emita el certificado.

Probar: `https://soat.tudominio.com/health` -> `{"status":"ok"}`

## 7. Probar la API

```bash
# Sincrono (espera ~30-40s)
curl -X POST https://soat.tudominio.com/soat \
  -H "Content-Type: application/json" \
  -d '{"placa":"ABC123"}'

# Async (202 inmediato, scraper en background)
curl -X POST https://soat.tudominio.com/soat/async \
  -H "Content-Type: application/json" \
  -d '{"placa":"ABC123"}'

# Atajo GET
curl https://soat.tudominio.com/soat/ABC123
```

Docs interactivas: `https://soat.tudominio.com/docs`

## 8. Anadir otros servicios despues

Para cada nueva API/DB/frontend, repite el patron:
1. Crear otro directorio bajo `/opt/` con su `docker-compose.yml`.
2. Usar la misma red externa `proxy-net`.
3. Levantar con `docker compose up -d`.
4. Agregar Proxy Host en NPM con el nombre del contenedor y puerto.

Ejemplo PostgreSQL:

```yaml
# /opt/db/docker-compose.yml
services:
  db:
    image: postgres:16-alpine
    container_name: mi-db
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: secreto
    volumes:
      - ./pgdata:/var/lib/postgresql/data
    networks:
      - proxy-net
networks:
  proxy-net:
    external: true
```

## 9. Comandos utiles

```bash
# Ver contenedores activos
docker ps

# Logs de un contenedor
docker logs -f soat-api

# Reiniciar un servicio
cd /opt/soat-api && docker compose restart

# Parar todo
cd /opt/soat-api && docker compose down

# Actualizar codigo: subir nuevos archivos y reconstruir
cd /opt/soat-api && docker compose up -d --build

# Espacio en disco
docker system df
docker system prune -a   # limpiar lo no usado (cuidado)

# Memoria usada
free -h
docker stats --no-stream
```

## 10. Notas importantes

- **RAM**: con 1-2GB,_monitora con `free -h`. Docker + NPM + la API + Chrome headless pueden sumar ~600-800MB. Si agregas DBs, vigila el swap.
- **Swap** (si tienes 1GB RAM, recomendado):
  ```bash
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ```
- **Chrome en Docker**: el Dockerfile instala Chrome estable y sus deps. `undetected-chromedriver` descargara el ChromeDriver correspondiente automaticamente al arrancar.
- **CapSolver**: la API key va en `docker-compose.yml` (environment). No la subas a git.
- **Webhook**: las URLs de SOAT/MTC estan en `app/compartido/webhook.py`; la de Sunarp en `WEBHOOK_SUNARP_URL`.


## 10. Deploy Produccion
Comando 1:  scp -r C:\Users\Armando.Campos\Documents\Proyectos\Scrapper\soat-scraper\* root@200.234.233.170:/opt/soat-api/
Comando 2:  cd /opt/soat-api && docker compose up -d --build