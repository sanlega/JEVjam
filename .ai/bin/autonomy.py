#!/usr/bin/env python3
"""Autonomía de metaharness: que las IAs ejecuten en lugar de pedir permiso.

  level [NIVEL]    muestra o fija el nivel de autonomía del proyecto
  agent IA TAREA   lanza una IA sin supervisión (claude, codex, gemini o un comando)
  stop-check       hook Stop de Claude Code: no terminar sin cumplir el protocolo

Niveles (se guardan en .ai/config como AUTONOMY=...):
  supervised  (por defecto) la herramienta pregunta según su configuración
  standard    edita archivos sin preguntar; comandos de lectura/test permitidos
  autonomous  edita y ejecuta sin preguntar; el guardián (mh guard)
              deniega lo catastrófico y solo pregunta en lo irreversible/externo
  full        sin ninguna comprobación de permisos (solo contenedores o CI
              desechables); el guardián sigue pudiendo denegar

La política de permisos se escribe en .claude/settings.json (fusionando: nunca se
borran reglas del usuario) y los flags equivalentes se usan con Codex y Gemini.
Solo biblioteca estándar.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402

LEVELS = ("supervised", "standard", "autonomous", "full")
DEFAULT_LEVEL = "supervised"

# Reglas de permiso que gestiona metaharness (se quitan/añaden al cambiar de nivel).
SAFE_READ = [
    "Bash(.ai/bin/mh:*)", "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
    "Bash(git show:*)", "Bash(git branch:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)",
    "Bash(rg:*)", "Bash(find:*)", "Bash(npm test:*)", "Bash(npm run test:*)",
    "Bash(npm run lint:*)", "Bash(pnpm test:*)", "Bash(yarn test:*)", "Bash(pytest:*)",
    "Bash(python3 -m pytest:*)", "Bash(python3 -m unittest:*)", "Bash(go test:*)",
    "Bash(cargo test:*)", "Bash(make test:*)", "mcp__metaharness",
]
BROAD = ["Bash", "WebFetch", "WebSearch", "mcp__metaharness"]
MANAGED = set(SAFE_READ) | set(BROAD)
POLICY = {
    "supervised": (None, []),
    "standard": ("acceptEdits", SAFE_READ),
    "autonomous": ("acceptEdits", BROAD),
    "full": ("bypassPermissions", BROAD),
}

AUTONOMY_PROMPT = (
    "Completa la tarea de principio a fin en este proyecto metaharness y verifica el "
    "resultado. Pide confirmación antes de acciones irreversibles o externas (publicar, "
    "desplegar, pagar, borrar datos, enviar mensajes, push forzado). Sigue "
    ".ai/protocol.md y cierra con STATE.md + mh handoff.\n\nTarea: "
)


def die(msg, code=2):
    sys.stderr.write("mh: %s\n" % msg)
    sys.exit(code)


def need_root():
    root = jev.find_root()
    if not root:
        die("no estás dentro de un proyecto metaharness")
    return root


# --------------------------------------------------------------------- nivel
def read_level(root):
    path = os.path.join(root, ".ai", "config")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*AUTONOMY="?([a-z]+)"?\s*$', line)
                if m and m.group(1) in LEVELS:
                    return m.group(1)
    return DEFAULT_LEVEL


def write_level(root, level):
    path = os.path.join(root, ".ai", "config")
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if not re.match(r"\s*AUTONOMY=", l)]
    lines.append('AUTONOMY="%s"' % level)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def apply_claude(root, level):
    """Fusiona la política del nivel en .claude/settings.json sin tocar lo ajeno."""
    path = os.path.join(root, ".claude", "settings.json")
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    perms = data.setdefault("permissions", {})
    allow = [r for r in perms.get("allow", []) if r not in MANAGED]
    mode, rules = POLICY[level]
    allow.extend(rules)
    if allow:
        perms["allow"] = allow
    else:
        perms.pop("allow", None)
    if mode:
        perms["defaultMode"] = mode
    elif perms.get("defaultMode") in ("acceptEdits", "bypassPermissions"):
        perms.pop("defaultMode")
    if not perms:
        data.pop("permissions")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


HOOKS = {
    "SessionStart": [{"hooks": [{"type": "command",
                                 "command": "\"$CLAUDE_PROJECT_DIR\"/.ai/bin/mh brief --no-state"}]}],
    "PreToolUse": [{"matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.ai/bin/mh guard",
                               "timeout": 10}]}],
    "Stop": [{"hooks": [{"type": "command",
                         "command": "\"$CLAUDE_PROJECT_DIR\"/.ai/bin/mh stop-check", "timeout": 10}]}],
}


def ensure_hooks(root):
    """Añade los hooks de metaharness que falten sin tocar los del usuario."""
    path = os.path.join(root, ".claude", "settings.json")
    data = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    hooks = data.setdefault("hooks", {})
    added = []
    for event, groups in HOOKS.items():
        existing = json.dumps(hooks.get(event, []))
        marker = groups[0]["hooks"][0]["command"].split("/.ai/bin/")[1]
        if ".ai/bin/" + marker not in existing:
            hooks.setdefault(event, []).extend(groups)
            added.append(event)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return added


# --------------------------------------------------------------------- agentes
def agent_command(agent, level, task):
    """Comando para ejecutar `task` con la IA indicada sin supervisión."""
    prompt = AUTONOMY_PROMPT + task
    override = os.environ.get("MH_AGENT_" + agent.upper().replace("-", "_"))
    if override:
        return shlex.split(override) + [prompt]
    if agent == "claude":
        mode = {"full": ["--dangerously-skip-permissions"],
                "supervised": []}.get(level, ["--permission-mode", "acceptEdits"])
        return ["claude", "-p"] + mode + [prompt]
    if agent == "codex":
        mode = {"full": ["--dangerously-bypass-approvals-and-sandbox"],
                "supervised": []}.get(level, ["--full-auto"])
        return ["codex", "exec"] + mode + [prompt]
    if agent == "gemini":
        mode = {"full": ["--yolo"], "autonomous": ["--yolo"],
                "supervised": []}.get(level, ["--approval-mode", "auto_edit"])
        return ["gemini"] + mode + ["-p", prompt]
    return shlex.split(agent) + [prompt]  # cualquier otro CLI: CMD <prompt>


# --------------------------------------------------------------------- stop-check
def git(root, *args):
    p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


GENERATED_PREFIXES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
                      ".cursor/", ".claude/skills/", ".agents/skills/", ".claude/commands/",
                      ".gemini/commands/")


def stop_check(event, root):
    """Devuelve el motivo para no terminar todavía, o None."""
    if event.get("stop_hook_active") or os.environ.get("MH_STOP_CHECK") == "0":
        return None  # ya se bloqueó una vez: nunca en bucle
    status = git(root, "status", "--porcelain")
    if not status:
        return None
    changed = [l[3:].strip().strip('"') for l in status.splitlines() if len(l) > 3]
    work = [p for p in changed if not p.startswith(".ai/") and not p.startswith(GENERATED_PREFIXES)]
    if not work:
        return None
    if any(p == ".ai/memory/STATE.md" for p in changed):
        return None
    return ("Protocolo metaharness: hay cambios sin reflejar en la memoria compartida (%s). "
            "Antes de terminar: verifica (tests/lint), actualiza .ai/memory/STATE.md y "
            "registra la sesión con `.ai/bin/mh handoff` (incluye ## Retro)." % ", ".join(work[:5]))


# --------------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(prog="mh autonomy", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    lv = sub.add_parser("level")
    lv.add_argument("level", nargs="?", choices=LEVELS)
    ag = sub.add_parser("agent")
    ag.add_argument("agent", help="claude, codex, gemini o un comando ('aider --yes')")
    ag.add_argument("task", nargs="+")
    ag.add_argument("--dry-run", action="store_true", help="muestra el comando sin ejecutarlo")
    ag.add_argument("--timeout", type=int, default=0)
    sub.add_parser("stop-check")
    sub.add_parser("install", help="fusiona los hooks de metaharness en .claude/settings.json")
    args = p.parse_args(argv)

    if args.cmd == "level":
        root = need_root()
        if not args.level:
            print(read_level(root))
            return 0
        write_level(root, args.level)
        path = apply_claude(root, args.level)
        print("autonomía: %s (%s actualizado)" % (args.level, os.path.relpath(path, root)))
        return 0
    if args.cmd == "agent":
        root = need_root()
        cmd = agent_command(args.agent, read_level(root), " ".join(args.task))
        if args.dry_run:
            print(json.dumps(cmd, ensure_ascii=False))
            return 0
        try:
            return subprocess.run(cmd, cwd=root, timeout=args.timeout or None).returncode
        except FileNotFoundError:
            die("no encuentro '%s' en el PATH" % cmd[0], 127)
    if args.cmd == "install":
        root = need_root()
        added = ensure_hooks(root)  # la política de permisos solo cambia con `mh autonomy`
        print("hooks añadidos: %s" % (", ".join(added) or "ninguno"))
        return 0
    if args.cmd == "stop-check":
        try:
            event = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 0
        root = jev.find_root(event.get("cwd")) or jev.find_root()
        reason = stop_check(event, root) if root else None
        if reason:
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
