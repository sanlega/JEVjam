# Instalación de metaharness

- **Fecha**: 2026-09-30 14:07
- **Agente**: claude
- **Rama**: HEAD @ sin commits

## Hecho
- Instalado metaharness en la máquina (~/metaharness, `mh` en ~/.local/bin).
- `mh init` en JEVjam: .ai/, adaptadores (Claude, Codex/AGENTS, Gemini, Copilot, Cursor), 15 skills, hooks de Claude Code y servidor MCP.
- Nombre del proyecto en .ai/context/10-project.md; STATE.md actualizado.
- Verificado: `mh sync` + `mh check` OK; hooks `brief` y `guard` probados a mano.

## Pendiente
- Definir objetivo/stack de JEVjam en .ai/context/ y `mh sync`.
- Primer commit (no hecho: esperando confirmación del usuario).
- `mh profile` no ejecutado (afecta a la config global).

## Retro
- Bien: el README basta para instalar sin fricción; el repo es privado y hubo que clonar con `gh` en vez de https.
- Mejorable: el hook Stop marca como "sin reflejar" los archivos generados por el propio `mh init` en un repo sin commits.
