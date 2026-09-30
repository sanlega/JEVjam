# Backends de observación y acción

Elige el más estructurado disponible. La fila "Observación" es lo que se poda y se
envía como `observation` a Jev; la acción la ejecuta siempre código local.

| Plataforma | Observación | Acción | Notas |
|---|---|---|---|
| **Navegador** (cualquier SO) | DOM / árbol de accesibilidad vía Playwright o Chrome DevTools Protocol; servidores MCP de navegador | `locator.click/fill`, navegación | La opción más fiable. Aislar en un perfil de navegador dedicado |
| **macOS** | API de Accesibilidad (AXUIElement) | Fijar `AXValue`, `AXPress`; AppleScript/JXA | Implementación de referencia: `Tewoto1/Computer-use-and-control-with-Jev` (`jevcu observe --app X`, `jevcu run "..." --app X`, modo preview por defecto) |
| **Windows** | UI Automation (pywinauto, FlaUI) | Patrones `Invoke`, `Value` | Evitar SendKeys cuando existe el patrón semántico |
| **Linux** | AT-SPI (pyatspi), `xdotool search` | AT-SPI actions; `xdotool`/`ydotool` | En Wayland la inyección de entrada está restringida |
| **Cualquiera (último recurso)** | Captura + OCR / visión (p. ej. herramienta de computer use de Claude) | Coordenadas | Re-observar antes de cada acción; nunca reutilizar coordenadas antiguas |

## Estado mínimo recomendado para Jev

```json
{
  "step": "Rellenar el email de contacto con el valor del plan",
  "predicate": "El campo 'Email' contiene ana@example.com",
  "observation": {
    "app": "Google Chrome", "url": "https://example.com/contacto",
    "elements": [
      {"id": "e3", "role": "textbox", "label": "Email", "value": ""},
      {"id": "e4", "role": "button", "label": "Enviar"}
    ]
  },
  "recent_actions": ["navigate:https://example.com/contacto"]
}
```

## Modelos de decisión compatibles

`mh decide` habla el contrato de Jev (`POST /v1/systemone` con `state` + `questions`).
`JEV_ENDPOINT` puede apuntar a cualquier servidor con el mismo contrato, como variantes
abiertas tipo AgentJev o Kev ejecutadas en local, útiles para operar sin enviar la
pantalla a terceros.
