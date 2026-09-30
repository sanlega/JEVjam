# Checklist de revisión

Úsala como guía de búsqueda, no como formulario: reporta solo lo que encuentres.

## Corrección
- [ ] Condiciones límite: vacío, uno, máximo, negativos, off-by-one, desbordamiento.
- [ ] Nulos / undefined / opcionales: ¿cada acceso está protegido o garantizado?
- [ ] Errores: ¿se propagan o se tragan? ¿Mensajes útiles? ¿Se limpia el estado parcial?
- [ ] Ramas: ¿cubre todos los casos de enums/uniones? ¿`default` razonable?
- [ ] Igualdad y comparación: tipos, precisión de flotantes, zonas horarias, mayúsculas.
- [ ] Strings: codificación, Unicode, i18n, formato de fechas y números.

## Estado y concurrencia
- [ ] Condiciones de carrera, check-then-act, estado global mutable.
- [ ] Transacciones: atomicidad, rollback, idempotencia de reintentos.
- [ ] Async: promesas sin await, cancelación, timeouts, backpressure.
- [ ] Caché: invalidación, datos obsoletos, claves correctas.

## Recursos
- [ ] Archivos, conexiones, locks, suscripciones: ¿se liberan también en error?
- [ ] Consultas N+1, bucles con E/S, cargas sin paginar.
- [ ] Complejidad algorítmica con tamaños reales de datos.

## Contratos y datos
- [ ] Cambios de API pública, CLI, formato de archivo o esquema: ¿compatibles o versionados?
- [ ] Migraciones: reversibles, seguras con datos existentes y en despliegue gradual.
- [ ] Validación de entrada en los límites del sistema.
- [ ] Configuración nueva: valores por defecto seguros, documentada.

## Seguridad
- [ ] Inyección (SQL, comandos, rutas, plantillas, deserialización).
- [ ] Autorización comprobada en el servidor para cada recurso.
- [ ] Secretos fuera del código y de los logs.
- [ ] Datos personales: mínimos, protegidos, no registrados.

## Tests
- [ ] Hay tests del comportamiento nuevo y de los casos de error.
- [ ] Los tests fallarían si el código estuviera mal.
- [ ] Sin tests deshabilitados ni aserciones debilitadas.

## Mantenibilidad
- [ ] Reutiliza utilidades existentes en vez de duplicar.
- [ ] Nombres que dicen la verdad; funciones con una responsabilidad.
- [ ] Sin código muerto, comentado, ni restos de depuración.
- [ ] Comentarios explican el porqué, no el qué.
