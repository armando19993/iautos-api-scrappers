"""Compatibilidad: `uvicorn api:app` y `python api.py` siguen funcionando.

La aplicacion vive en app/main.py (ver docs/adr/0001-estructura-por-procesos.md).
Para arrancar usar: uvicorn app.main:app
"""
from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
