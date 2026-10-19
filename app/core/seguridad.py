import base64

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DOCS_USER = "waytech"
DOCS_PASSWORD = "iautos2026!"
PROTECTED_PATHS = ("/docs", "/redoc", "/openapi.json")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Middleware que protege las rutas de documentación con HTTP Basic Auth."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in PROTECTED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                user, password = decoded.split(":", 1)
                if user == DOCS_USER and password == DOCS_PASSWORD:
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            content="Credenciales inválidas",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Documentación"'},
        )
