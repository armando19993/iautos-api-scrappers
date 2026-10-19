from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import rutas as rutas_core
from app.core.openapi import API_DESCRIPTION, instalar_openapi, tags_metadata
from app.core.seguridad import BasicAuthMiddleware
from app.procesos.mtc import rutas as rutas_mtc
from app.procesos.soat import rutas as rutas_soat
from app.procesos.sunarp import rutas as rutas_sunarp
from app.procesos.sunarp.pool import cerrar_pool

app = FastAPI(
    title="Api Scrappers IAUTOS",
    description=API_DESCRIPTION,
    version="1.2.0",
    contact={
        "name": "IAUTOS",
        "url": "https://next.iautos.pe",
    },
    license_info={
        "name": "Uso privado — IAUTOS",
    },
    servers=[
        {"url": "http://localhost:8000", "description": "Local (desarrollo)"},
        {"url": "http://200.234.233.170:8000", "description": "Producción"},
    ],
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(BasicAuthMiddleware)

instalar_openapi(app)

# el orden de include_router es el orden de las rutas en el OpenAPI y en /docs
app.include_router(rutas_core.router)
app.include_router(rutas_soat.router)
app.include_router(rutas_mtc.router)
app.include_router(rutas_sunarp.router)


@app.on_event("shutdown")
def shutdown():
    cerrar_pool()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
