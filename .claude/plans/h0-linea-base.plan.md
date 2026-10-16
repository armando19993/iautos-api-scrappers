# Plan H0 · Rama de trabajo y test de contrato

PRD: `.claude/prds/estructura-por-procesos.prd.md` · Estado: **Completado (16/10/2026)**

Objetivo: tener una red de seguridad antes de mover nada. Si el contrato de la API cambia,
un test lo dice.

## Tareas

| # | Tarea | Validación | Estado |
|---|---|---|---|
| 0.1 | Crear rama `refactor/estructura-procesos` desde `main` actualizado | `git status` limpio sobre la rama | Hecho |
| 0.2 | Escribir `tests/contrato/test_openapi.py`: genera `app.openapi()`, lo serializa como JSON respetando el orden (es el orden de /docs) y lo compara con `tests/contrato/openapi.snapshot.json`; si difiere, imprime el diff y termina con error | Corre contra el código actual (sin snapshot falla, como se esperaba) | Hecho |
| 0.3 | Generar el snapshot desde el código actual (`--actualizar`) y commitearlo | 14 operaciones / 14 schemas / 18 rutas en el snapshot | Hecho |
| 0.4 | Comprobar que el test detecta cambios: alterar a mano un `summary` en memoria y ver que falla | Detecta summary editado, orden de rutas cambiado y docs sin Basic Auth | Hecho |
| 0.5 | Registrar en el PRD el resultado de los 3 tests existentes | parser 9 ok · ocr 14 ok · sync 18 ok | Hecho |

## Notas
- El test de contrato queda en el repo para siempre: cualquier PR que cambie la API sin
  querer lo verá fallar; si el cambio es intencional se regenera el snapshot y el diff
  queda visible en el PR.
- No toca código de producción.

## Resultado

- `python -m tests.contrato.test_openapi` en verde sobre `main` (`2088194`).
- Hallazgo: la respuesta 401 de `/docs` envía `WWW-Authenticate: Basic realm="Documentación"`
  en latin-1. Es válido en HTTP, pero `TestClient` de Starlette no lo decodifica; el test
  verifica la protección con una llamada ASGI directa. No se cambió el middleware.
