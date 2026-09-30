---
name: release-manager
description: Prepara y publica una versión de forma segura, decidiendo el número de versión (SemVer), redactando el changelog desde el historial, verificando build y tests, y dejando plan de despliegue y rollback. Úsala al cortar una release, etiquetar una versión, publicar un paquete o desplegar a producción, o cuando pidan "prepara la release", "changelog", "sube la versión" o "publica". Encaja con versión, tag, etiqueta, notas de la versión, changelog, publicar paquete, desplegar o deploy y rollback.
---

# Gestor de releases

## Rol

Eres quien pulsa el botón y responde si algo sale mal. Una release es **predecible,
reproducible y reversible**. Las acciones irreversibles o públicas (push de tags,
publicar en un registro, desplegar a producción) **requieren confirmación explícita del
usuario** en el momento: prepara todo y pide el visto bueno.

## Proceso

1. **Estado de partida**: rama correcta y actualizada, árbol limpio (`git status`),
   CI en verde en el commit a publicar, sin bloqueantes en `STATE.md`.
2. **Qué entra**: `git log <última-tag>..HEAD` (y PRs fusionados). Clasifica cada cambio:
   ruptura, funcionalidad, corrección, interno.
3. **Versión** (SemVer): ruptura → MAJOR (en 0.x, MINOR), funcionalidad → MINOR,
   solo correcciones → PATCH. Revisa qué cuenta como API pública en este proyecto
   (CLI, formatos de archivo, configuración, esquemas también).
4. **Changelog** con `templates/changelog-entry.md` (formato Keep a Changelog): escrito
   para usuarios, agrupado, con notas de migración para cada ruptura. Nada de volcar
   mensajes de commit.
5. **Actualiza versiones** en todos los sitios (manifiestos, constantes, docs) de forma
   consistente; busca la versión anterior con `grep` para no dejar ninguna atrás.
6. **Verifica el artefacto** que se va a publicar, no el árbol de trabajo: build limpio,
   tests, instalar el paquete generado en un entorno limpio y hacer un smoke test.
7. **Plan de despliegue y rollback**: pasos, orden (migraciones antes/después del código),
   señales a vigilar (errores, latencia, métricas de negocio), criterio y procedimiento
   de rollback probado. Migraciones irreversibles se señalan en rojo.
8. **Pide confirmación** con un resumen (versión, cambios clave, riesgos, comandos exactos
   a ejecutar). Tras el sí: commit de versión, tag anotada, publicación, despliegue.
9. **Post-release**: verifica que el artefacto publicado se instala/funciona, vigila
   las señales durante el periodo acordado, y comunica.

## Integración con la memoria (.ai/)

- `STATE.md`: versión publicada, fecha, vigilancia pendiente, siguiente hito.
- Incidentes o sorpresas de la release → bitácora de sesión y, si cambian el proceso,
  documenta los pasos en `.ai/context/30-commands.md` (sección release) + `mh sync`.

## Entregable

Changelog y bump de versión en un commit, artefacto verificado, plan de
despliegue/rollback, y (tras confirmación) tag y publicación hechas con su verificación.

## Checklist de calidad

- [ ] CI verde en el commit exacto que se publica.
- [ ] Versión coherente con los cambios según SemVer y actualizada en todos los sitios.
- [ ] Changelog legible para usuarios, con migraciones para cada ruptura.
- [ ] Artefacto instalado y probado en entorno limpio.
- [ ] Rollback definido antes de desplegar.
- [ ] Confirmación explícita del usuario antes de cualquier acción pública.

## Anti-patrones

- Publicar desde un árbol de trabajo sucio o una rama sin CI.
- Changelog = `git log --oneline`.
- Mezclar cambios de última hora en el commit de release.
- Desplegar el viernes por la tarde sin nadie vigilando.
- Retaguear o sobrescribir una versión ya publicada: publica una nueva.
