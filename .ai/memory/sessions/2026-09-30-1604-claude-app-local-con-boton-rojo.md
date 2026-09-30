# App local con botón rojo

- **Fecha**: 2026-09-30 16:04
- **Agente**: claude
- **Rama**: main @ ae8b92e

## Hecho
- session.py (Session/SessionConfig/list_devices) compartido por CLI y app; conductor emite on_bar/on_message.
- app.py: ThreadingHTTPServer en 127.0.0.1, SSE para el directo, una jam a la vez, validación de opciones, protección de origen (CSRF) y de rutas en la revisión.
- web/index.html: opciones completas, botón rojo, directo, sesiones (revisar/repetir); preferencias en localStorage. Probado con Jev real vía API y con capturas (escritorio y 500 px).
- 9 tests nuevos (57).

## Retro
- Bien: probar la API con curl + SSE antes de mirar la página separó fallos de servidor y de interfaz.
- Mejorable: Chrome headless no baja de 500 px de ancho; una captura "móvil" a 390 px engaña. Medir innerWidth antes de fiarse.
