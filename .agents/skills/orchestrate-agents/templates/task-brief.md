# Encargo: <nombre-corto>

- **Plan**: `.ai/memory/plans/<plan>.md` · **Tareas**: T<n>, T<m>
- **Sesión / rama**: `session/<nombre>` · **Skill**: `<skill>` · **Agente sugerido**: <herramienta>

## Objetivo
<qué debe existir al terminar, en 1-3 frases>

## Contexto imprescindible
- <decisiones, contratos y rutas que necesitas; enlaza a .ai/ en vez de repetir>

## Alcance
- **Puedes modificar**: <rutas>
- **No toques**: <rutas o contratos que pertenecen a otros encargos>

## Criterios de aceptación
1.

## Verificación obligatoria
```sh
<comandos exactos que deben pasar>
```

## Entrega
1. Commits en `session/<nombre>` con tests en verde.
2. Tareas marcadas en el plan.
3. `.ai/bin/mh handoff -a <agente> -t "<encargo>"` con: qué hiciste, decisiones,
   desviaciones del encargo y pendientes.
4. Si te bloqueas: no improvises fuera de alcance; documenta el bloqueo en la bitácora y para.
