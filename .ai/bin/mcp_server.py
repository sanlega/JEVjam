#!/usr/bin/env python3
"""Servidor MCP (stdio) de metaharness.

Expone la memoria compartida, las skills y la capa de decisión Jev a cualquier
cliente MCP (Claude Code/Desktop, Cursor, Codex, Gemini CLI, Windsurf...), incluso
a los que no leen AGENTS.md. Transporte stdio con JSON-RPC 2.0 delimitado por
líneas. Solo biblioteca estándar.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
HERE = os.path.dirname(os.path.abspath(__file__))
MH = os.path.join(HERE, "mh")


def root():
    r = jev.find_root(os.environ.get("MH_ROOT") or os.getcwd()) or jev.find_root(HERE)
    if not r:
        raise RuntimeError("no se encuentra un proyecto metaharness")
    return r


def mh(*args, stdin=None):
    p = subprocess.run([MH] + list(args), cwd=root(), input=stdin, capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip())
    return (p.stdout + p.stderr).strip()


def read(rel):
    with open(os.path.join(root(), rel), encoding="utf-8") as f:
        return f.read()


def skill_path(name):
    name = os.path.basename(name)  # evita salir de .ai/skills
    path = os.path.join(root(), ".ai", "skills", name, "SKILL.md")
    if not os.path.isfile(path):
        raise RuntimeError("no existe la skill %s" % name)
    return path


# --------------------------------------------------------------------- herramientas
def t_brief(_):
    return mh("brief")


def t_read_state(_):
    return read(".ai/memory/STATE.md")


def t_write_state(a):
    content = a["content"]
    if not content.lstrip().startswith("#"):
        raise RuntimeError("STATE.md debe empezar con un título Markdown")
    with open(os.path.join(root(), ".ai", "memory", "STATE.md"), "w", encoding="utf-8") as f:
        f.write(content if content.endswith("\n") else content + "\n")
    return "STATE.md actualizado"


def t_handoff(a):
    return mh("handoff", "-a", a.get("agent", "mcp"), "-t", a["title"], stdin=a["body"])


def t_decision(a):
    return mh("decision", a["title"], stdin=a["body"])


def t_lesson(a):
    return mh("learn", "-a", a.get("agent", "mcp"), a["lesson"])


def t_list_skills(_):
    return "\n".join("- %s: %s" % kv for kv in jev.read_skills(root()).items())


def t_get_skill(a):
    with open(skill_path(a["name"]), encoding="utf-8") as f:
        return f.read()


def t_route(a):
    return json.dumps(jev.route(a["task"], root()), ensure_ascii=False, indent=2)


def t_decide(a):
    res = jev.decide(a["state"], a["questions"], root=root())
    return json.dumps(res, ensure_ascii=False, indent=2)


def t_guard(a):
    decision, reason = jev.guard_decision(
        {"tool_name": "Bash", "tool_input": {"command": a["command"]}}, root=root())
    return json.dumps({"decision": decision or "no-objection", "reason": reason},
                      ensure_ascii=False)


S = {"type": "string"}
TOOLS = [
    ("mh_brief", "Contexto de inicio de sesión: estado, lecciones, skills, sesiones recientes y git. Llámala al empezar.", {}, [], t_brief),
    ("mh_read_state", "Lee .ai/memory/STATE.md (estado actual y próximos pasos).", {}, [], t_read_state),
    ("mh_write_state", "Reescribe .ai/memory/STATE.md completo al terminar o cambiar el estado del trabajo.", {"content": S}, ["content"], t_write_state),
    ("mh_handoff", "Registra la bitácora de la sesión en .ai/memory/sessions/.", {"title": S, "body": S, "agent": S}, ["title", "body"], t_handoff),
    ("mh_decision", "Añade una decisión de arquitectura o convención a DECISIONS.md.", {"title": S, "body": S}, ["title", "body"], t_decision),
    ("mh_learn", "Guarda una lección breve y accionable en LESSONS.md (memoria de la automejora).", {"lesson": S, "agent": S}, ["lesson"], t_lesson),
    ("mh_list_skills", "Lista las skills del proyecto con su descripción.", {}, [], t_list_skills),
    ("mh_get_skill", "Devuelve el SKILL.md completo de una skill para seguirlo.", {"name": S}, ["name"], t_get_skill),
    ("mh_route", "Elige la skill adecuada para una tarea (Jev o motor léxico local) con su confianza.", {"task": S}, ["task"], t_route),
    ("jev_decide", "Decisión tipada con Jev: state + questions {id: {type: noul|choice|score, instructions, criteria}}. Devuelve probabilidades calibradas y banda auto/confirm/human.",
     {"state": {}, "questions": {"type": "object"}}, ["state", "questions"], t_decide),
    ("mh_guard", "Evalúa el riesgo de un comando de shell antes de ejecutarlo (deny/ask/no-objection).", {"command": S}, ["command"], t_guard),
]

RESOURCES = [
    ("mh://protocol", "Protocolo de trabajo", ".ai/protocol.md"),
    ("mh://state", "Estado actual", ".ai/memory/STATE.md"),
    ("mh://decisions", "Registro de decisiones", ".ai/memory/DECISIONS.md"),
    ("mh://lessons", "Lecciones aprendidas", ".ai/memory/LESSONS.md"),
    ("mh://agents", "Contexto completo (AGENTS.md)", "AGENTS.md"),
]


# --------------------------------------------------------------------- JSON-RPC
def handle(msg):
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if mid is None:  # notificación
        return None
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "metaharness", "version": "0.3.0"},
                "instructions": "Memoria compartida entre IAs. Al empezar llama a mh_brief; "
                                "al terminar mh_write_state + mh_handoff. Usa mh_route para "
                                "elegir skill y jev_decide para decisiones tipadas."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": {
            "type": "object", "properties": props, "required": req}}
            for n, d, props, req, _ in TOOLS]}
    if method == "tools/call":
        fn = {n: f for n, _, _, _, f in TOOLS}.get(params.get("name"))
        if not fn:
            raise LookupError("herramienta desconocida: %s" % params.get("name"))
        try:
            text, err = fn(params.get("arguments") or {}), False
        except (Exception, SystemExit) as e:  # errores de herramienta van al modelo
            text, err = "error: %s" % e, True
        return {"content": [{"type": "text", "text": text}], "isError": err}
    if method == "resources/list":
        out = [{"uri": u, "name": n, "mimeType": "text/markdown"} for u, n, _ in RESOURCES]
        for name, desc in jev.read_skills(root()).items():
            out.append({"uri": "mh://skills/" + name, "name": "Skill " + name,
                        "description": desc, "mimeType": "text/markdown"})
        return {"resources": out}
    if method == "resources/read":
        uri = params.get("uri", "")
        if uri.startswith("mh://skills/"):
            with open(skill_path(uri[len("mh://skills/"):]), encoding="utf-8") as f:
                text = f.read()
        else:
            rel = {u: p for u, _, p in RESOURCES}.get(uri)
            if not rel:
                raise LookupError("recurso desconocido: %s" % uri)
            text = read(rel) if os.path.isfile(os.path.join(root(), rel)) else ""
        return {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}
    raise NotImplementedError(method)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "JSON inválido"}}
        else:
            try:
                result = handle(msg)
                if result is None:
                    continue
                reply = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
            except NotImplementedError as e:
                reply = {"jsonrpc": "2.0", "id": msg.get("id"),
                         "error": {"code": -32601, "message": "método no soportado: %s" % e}}
            except Exception as e:
                reply = {"jsonrpc": "2.0", "id": msg.get("id"),
                         "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
