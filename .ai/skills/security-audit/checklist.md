# Checklist de seguridad (basada en OWASP Top 10 y ASVS)

## Control de acceso (A01)
- [ ] Cada endpoint/acción comprueba autorización en el servidor.
- [ ] Acceso a recursos por ID verifica propiedad/tenant (IDOR/BOLA).
- [ ] Denegar por defecto; roles comprobados de forma centralizada.
- [ ] Sin escalada vía campos asignables en masa (`role`, `isAdmin`, `ownerId`).
- [ ] CORS restrictivo; sin `*` con credenciales.

## Criptografía (A02)
- [ ] Contraseñas con argon2/bcrypt/scrypt, nunca hash rápido ni cifrado reversible.
- [ ] TLS en tránsito; datos sensibles cifrados en reposo cuando aplica.
- [ ] Aleatoriedad criptográfica para tokens; sin algoritmos obsoletos (MD5, SHA1, ECB).

## Inyección (A03)
- [ ] SQL/NoSQL parametrizado; sin concatenar entrada en consultas.
- [ ] Sin shell con entrada del usuario (o argumentos como lista, sin `shell=True`).
- [ ] Rutas de archivo normalizadas y confinadas (path traversal).
- [ ] Salida HTML escapada por contexto (XSS); plantillas sin `safe`/`raw` sobre entrada.
- [ ] Sin deserialización insegura (pickle, YAML load, `eval`) de datos externos.
- [ ] Cabeceras y logs sin inyección de CRLF.

## Diseño inseguro (A04)
- [ ] Límites de tasa en login, registro, recuperación y operaciones caras.
- [ ] Flujos de negocio sin atajos (pagos, cambios de email, invitaciones).

## Configuración (A05)
- [ ] Sin modo debug ni trazas en producción; errores genéricos al cliente.
- [ ] Cabeceras: CSP, HSTS, X-Content-Type-Options, frame-ancestors.
- [ ] Cookies `Secure`, `HttpOnly`, `SameSite`.
- [ ] Credenciales por defecto eliminadas; mínimo privilegio en contenedores e IAM.

## Componentes vulnerables (A06)
- [ ] Auditoría de dependencias sin vulnerabilidades alcanzables altas/críticas.
- [ ] Versiones fijadas (lockfile) y fuentes de paquetes confiables.

## Autenticación (A07)
- [ ] Sesiones/tokens con expiración, rotación al hacer login e invalidación al logout.
- [ ] JWT: algoritmo fijado, firma verificada, `exp` comprobado, sin `none`.
- [ ] Mensajes de error que no revelan si el usuario existe.
- [ ] MFA disponible para cuentas privilegiadas.

## Integridad (A08)
- [ ] Webhooks con firma verificada; actualizaciones y artefactos firmados.
- [ ] CI sin secretos expuestos a PRs de forks.

## Registro y monitorización (A09)
- [ ] Eventos de seguridad registrados (login fallido, cambios de permisos).
- [ ] Sin secretos, tokens ni datos personales en logs.

## SSRF (A10)
- [ ] Peticiones salientes a URLs del usuario con allowlist; bloqueadas IPs internas y metadata.

## Secretos
- [ ] Ningún secreto en código, historial git, imágenes o configuración versionada.
- [ ] `.env` y similares en `.gitignore`; secretos desde gestor o variables de entorno.

## Subida de archivos
- [ ] Tipo validado por contenido, tamaño limitado, nombre regenerado, fuera del webroot.
