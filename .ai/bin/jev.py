#!/usr/bin/env python3
"""Cliente de Jev (TypeSafe AI "System One") para metaharness.

Jev no genera texto: recibe un `state` y preguntas tipadas (noul = sí/no,
choice = una de N, score = escala) y devuelve probabilidades calibradas en una
sola pasada (~100 ms). metaharness lo usa como capa de decisión:

  ask          decisión tipada genérica (con bandas de confianza y registro)
  route        qué skill de .ai/skills encaja con una tarea
  guard        hook PreToolUse: reglas deterministas + Jev para acciones de riesgo
  outcome      registra si una decisión registrada acertó (señal de automejora)
  calibration  precisión observada por banda de confianza

Solo biblioteca estándar (Python >= 3.8). Configuración:
  TYPESAFE_API_KEY   clave de la API (sin ella: route usa un motor léxico local,
                     guard solo aplica reglas deterministas, ask falla)
  JEV_ENDPOINT       por defecto https://api.typesafe.ai/v1/systemone; cualquier
                     servidor con el mismo contrato (p. ej. AgentJev/Kev locales)
  JEV_MODEL          por defecto jev-latest
  .ai/jev.json       umbrales de las bandas y registro (ver plantilla)
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_POLICY = {"thresholds": {"auto": 0.9, "confirm": 0.5}, "log": True}
FALLBACK_OPTION = "other"


# --------------------------------------------------------------------- utilidades
def find_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, ".ai", "protocol.md")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_policy(root):
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    if root:
        path = os.path.join(root, ".ai", "jev.json")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            policy["thresholds"].update(user.get("thresholds", {}))
            for k, v in user.items():
                if k != "thresholds":
                    policy[k] = v
    return policy


def band(confidence, policy):
    t = policy["thresholds"]
    if confidence >= t["auto"]:
        return "auto"
    if confidence >= t["confirm"]:
        return "confirm"
    return "human"


def die(msg, code=2):
    sys.stderr.write("jev: %s\n" % msg)
    sys.exit(code)


# --------------------------------------------------------------------- preguntas
def noul(instructions):
    return {"type": "noul", "instructions": instructions}


def choice(instructions, options):
    """options: dict opción -> descripción (o None). Añade siempre 'other'."""
    criteria = dict(options)
    if FALLBACK_OPTION not in criteria and "none_of_the_above" not in criteria:
        criteria[FALLBACK_OPTION] = None
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions, levels):
    if not 2 <= len(levels) <= 10:
        die("score necesita entre 2 y 10 niveles")
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def parse_options(spec):
    """'bug=Algo roto,feature=Nueva función' -> {'bug': 'Algo roto', ...}"""
    out = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        key, _, desc = part.partition("=")
        out[key.strip()] = desc.strip() or None
    return out


# --------------------------------------------------------------------- cliente
class JevError(Exception):
    pass


def api_key():
    return os.environ.get("TYPESAFE_API_KEY", "").strip()


def call_jev(state, questions, model=None, endpoint=None, timeout=30):
    key = api_key()
    if not key:
        raise JevError("falta TYPESAFE_API_KEY")
    body = json.dumps({
        "model": model or os.environ.get("JEV_MODEL", "jev-latest"),
        "state": state,
        "questions": questions,
    }).encode("utf-8")
    url = endpoint or os.environ.get("JEV_ENDPOINT", DEFAULT_ENDPOINT)
    last = None
    for attempt in range(3):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = "HTTP %s: %s" % (e.code, detail)
            if e.code in (429, 529) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise JevError(last)
        except (urllib.error.URLError, OSError) as e:
            last = str(e)
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
    raise JevError(last or "error desconocido")


def normalize(answer):
    """Añade `confidence` y `value` homogéneos a cualquier tipo de respuesta."""
    a = dict(answer)
    if "noul" in a:
        p = float(a["noul"])
        a["value"] = p >= 0.5
        a.setdefault("confidence", abs(2 * p - 1))  # derivada: distancia a 0.5
    elif "choice" in a:
        a["value"] = a["choice"]
        a.setdefault("confidence", max((a.get("probabilities") or {0: 0}).values()))
    elif "score" in a:
        probs = a.get("probabilities") or {}
        a["value"] = int(max(probs, key=probs.get)) if probs else round(float(a["score"]))
        a.setdefault("confidence", max(probs.values()) if probs else 0.0)
    a["confidence"] = round(float(a.get("confidence", 0.0)), 6)  # evita 0.8999... < 0.9
    return a


def log_decisions(root, policy, state, questions, answers):
    ids = {}
    if not (root and policy.get("log", True)):
        return ids
    d = os.path.join(root, ".ai", "local", "jev")
    os.makedirs(d, exist_ok=True)
    sha = hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:16]
    with open(os.path.join(d, "log.jsonl"), "a", encoding="utf-8") as f:
        for qid, a in answers.items():
            did = uuid.uuid4().hex[:12]
            ids[qid] = did
            f.write(json.dumps({
                "id": did, "ts": int(time.time()), "qid": qid,
                "type": questions.get(qid, {}).get("type"),
                "instructions": questions.get(qid, {}).get("instructions"),
                "value": a.get("value"), "confidence": round(a.get("confidence", 0), 4),
                "band": a.get("band"), "state_sha": sha,
            }, ensure_ascii=False) + "\n")
    return ids


def decide(state, questions, root=None, policy=None, dry_run=False):
    root = root or find_root()
    policy = policy or load_policy(root)
    if dry_run:
        return {"engine": "dry-run", "request": {
            "model": os.environ.get("JEV_MODEL", "jev-latest"),
            "state": state, "questions": questions}}
    raw = call_jev(state, questions)
    answers = {}
    for qid, a in (raw.get("answers") or {}).items():
        a = normalize(a)
        a["band"] = band(a["confidence"], policy)
        answers[qid] = a
    ids = log_decisions(root, policy, state, questions, answers)
    for qid, did in ids.items():
        answers[qid]["decision_id"] = did
    return {"engine": "jev", "model": raw.get("model"), "answers": answers,
            "usage": raw.get("usage")}


# --------------------------------------------------------------------- skills
def read_skills(root):
    base = os.path.join(root, ".ai", "skills")
    skills = {}
    if not os.path.isdir(base):
        return skills
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        desc = m.group(1).strip().strip("'\"") if m else ""
        skills[name] = desc
    return skills


_WORD = re.compile(r"[a-záéíóúüñ0-9]{3,}", re.I)
_STOP = set("que con para por los las una uno del sus como cuando esta este pide pidan "
            "usala úsala sobre desde entre sin más muy hay the and".split())


def _tokens(text):
    out = set()
    for w in _WORD.findall(text.lower()):
        if w not in _STOP:
            out.add(w[:6])  # prefijo: tolera flexiones (revisa/revisión)
    return out


def lexical_route(text, skills):
    q = _tokens(text)
    scores = {}
    for name, desc in skills.items():
        d = _tokens(desc) | _tokens(name.replace("-", " "))
        scores[name] = len(q & d) / (len(q) ** 0.5 * len(d) ** 0.5 or 1)
    total = sum(scores.values())
    if total == 0:
        return FALLBACK_OPTION, 0.0, {}
    probs = {k: v / total for k, v in scores.items()}
    best = max(probs, key=probs.get)
    return best, probs[best], probs


def route(text, root, policy=None, force_lexical=False):
    skills = read_skills(root)
    if not skills:
        die("no hay skills en .ai/skills")
    policy = policy or load_policy(root)
    if api_key() and not force_lexical:
        q = {"skill": choice(
            "¿Qué procedimiento (skill) debe seguir el agente para realizar `task`? "
            "Elige 'other' si ninguno encaja.", skills)}
        res = decide({"task": text}, q, root=root, policy=policy)
        a = res["answers"]["skill"]
        return {"engine": "jev", "skill": a["value"], "confidence": a["confidence"],
                "band": a["band"], "probabilities": a.get("probabilities", {})}
    best, conf, probs = lexical_route(text, skills)
    top = dict(sorted(probs.items(), key=lambda kv: -kv[1])[:3])
    # El motor léxico no está calibrado: su "confianza" solo ordena opciones, así que
    # nunca autoriza actuar solo (banda máxima: confirm).
    b = band(conf, policy)
    return {"engine": "lexical", "skill": best, "confidence": round(conf, 3),
            "band": "confirm" if b == "auto" else b, "calibrated": False,
            "probabilities": top}


# --------------------------------------------------------------------- guard
# Reglas deterministas: rápidas, sin red, sin clave. Solo pueden restringir
# (deny/ask): el guardián nunca concede permisos que el usuario no haya dado.
DENY_RULES = [
    (r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+(/|~|\$HOME)(\s|/\*|$)", "borrado recursivo de / o del home"),
    (r"\bmkfs(\.\w+)?\b", "formateo de un sistema de archivos"),
    (r"\bdd\b.*\bof=/dev/(sd|nvme|disk|hd)", "escritura directa en un disco"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"\bchmod\s+-R\s+0?777\s+/(\s|$)", "permisos 777 recursivos en /"),
]
ASK_RULES = [
    (r"\bgit\s+push\b.*(--force\b|\s-f\b|--force-with-lease)", "push forzado"),
    (r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)", "descarta cambios locales"),
    (r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "ejecuta un script descargado"),
    (r"\bsudo\b", "privilegios de administrador"),
    (r"\b(drop|truncate)\s+(database|table|schema)\b", "borra datos de una base de datos"),
    (r"\b(npm|pnpm|yarn)\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b|\bgem\s+push\b", "publica un paquete"),
    (r"\bterraform\s+(apply|destroy)\b|\bkubectl\s+(delete|apply)\b|\bhelm\s+(install|upgrade|uninstall)\b", "cambia infraestructura"),
    (r"(~|\$HOME)/\.(ssh|aws|gnupg|kube)\b|\bid_(rsa|ed25519)\b", "accede a credenciales"),
    (r"(^|[\s/])\.env(\.\w+)?(\s|$)", "lee o modifica secretos (.env)"),
]
GENERATED = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md",
             ".cursor/rules/metaharness.mdc", ".aider.conf.yml")
FROZEN_PREFIXES = (".ai/evals/",)  # invariantes de la automejora: cambios con humano


_RM = re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?rm\s+((?:-[a-zA-Z-]+\s+)*)([^;&|]*)")


def risky_rm(cmd, root):
    """rm recursivo cuyo objetivo sale del proyecto (absoluto ajeno, ~, .., comodín raíz)."""
    for flags, targets in _RM.findall(cmd):
        if not re.search(r"-[a-zA-Z]*[rR]|--recursive", flags):
            continue
        for t in targets.split():
            t = t.strip("'\"")
            if t.startswith(("~", "$HOME", "${HOME}")) or ".." in t.split("/") or t in ("*", ".", "/*"):
                return True
            if t.startswith("/"):
                base = os.path.abspath(root or os.getcwd())
                if not os.path.abspath(t).startswith(base + os.sep):
                    return True
    return False


def _rel(root, path):
    if not path:
        return ""
    ap = os.path.abspath(os.path.join(root or os.getcwd(), path))
    base = os.path.abspath(root or os.getcwd())
    return os.path.relpath(ap, base) if ap.startswith(base + os.sep) else ap


def guard_decision(event, root=None, policy=None, use_jev=True):
    """Devuelve (decisión, motivo) con decisión en {deny, ask, None}."""
    tool = event.get("tool_name", "")
    inp = event.get("tool_input") or {}
    if tool == "Bash":
        cmd = inp.get("command", "")
        for rx, why in DENY_RULES:
            if re.search(rx, cmd):
                return "deny", "metaharness guard: %s" % why
        for rx, why in ASK_RULES:
            if re.search(rx, cmd, re.I):
                return "ask", "metaharness guard: %s" % why
        if risky_rm(cmd, root):
            return "ask", "metaharness guard: borrado recursivo fuera del proyecto"
        if use_jev and api_key():
            policy = policy or load_policy(root)
            try:
                res = decide({"command": cmd, "cwd": event.get("cwd", "")}, {
                    "risk": score("¿Qué riesgo tiene ejecutar `command`?", [
                        "Solo lectura o sin efectos",
                        "Modifica archivos del proyecto de forma reversible (git)",
                        "Efectos fuera del proyecto o difíciles de revertir",
                        "Destructivo, irreversible o expone secretos/datos",
                    ]),
                    "exfiltration": noul("¿`command` envía secretos, credenciales o datos "
                                         "privados a un destino externo?"),
                }, root=root, policy=policy)
            except (JevError, SystemExit):
                return None, ""
            a = res["answers"]
            risk, ex = a.get("risk", {}), a.get("exfiltration", {})
            if ex.get("value") and ex.get("confidence", 0) >= policy["thresholds"]["confirm"]:
                return "ask", "metaharness guard (Jev): posible exfiltración de datos"
            if risk.get("value", 0) >= 3 and risk.get("band") == "auto":
                return "deny", "metaharness guard (Jev): acción destructiva o irreversible"
            if risk.get("value", 0) >= 2:
                return "ask", "metaharness guard (Jev): riesgo %s/3" % risk.get("value")
        return None, ""
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        rel = _rel(root, inp.get("file_path") or inp.get("notebook_path", ""))
        if rel in GENERATED or rel.startswith((".claude/skills/", ".agents/skills/",
                                               ".claude/commands/", ".gemini/commands/")):
            # deny (no ask): el agente recibe el motivo y se corrige sin molestar al humano
            return "deny", ("metaharness guard: %s es un archivo generado; edita la fuente "
                            "en .ai/ y ejecuta .ai/bin/mh sync" % rel)
        if rel.startswith(FROZEN_PREFIXES):
            return "ask", ("metaharness guard: %s es un invariante de la automejora "
                           "(evaluaciones); requiere aprobación humana" % rel)
    return None, ""


# --------------------------------------------------------------------- calibración
def read_log(root):
    path = os.path.join(root, ".ai", "local", "jev", "log.jsonl")
    entries, outcomes = {}, {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                if "outcome_for" in e:
                    outcomes[e["outcome_for"]] = bool(e["correct"])
                else:
                    entries[e["id"]] = e
    return entries, outcomes


def calibration(root):
    entries, outcomes = read_log(root)
    rows = {}
    for did, correct in outcomes.items():
        e = entries.get(did)
        if not e:
            continue
        lo = min(int(e["confidence"] * 10), 9) / 10.0
        for key in ("band:" + str(e.get("band")), "conf:%.1f-%.1f" % (lo, lo + 0.1)):
            r = rows.setdefault(key, [0, 0])
            r[0] += 1
            r[1] += int(correct)
    return {"decisions": len(entries), "with_outcome": len(outcomes),
            "buckets": {k: {"n": v[0], "accuracy": round(v[1] / v[0], 3)}
                        for k, v in sorted(rows.items())}}


# --------------------------------------------------------------------- CLI
def read_state(args):
    if args.state is not None:
        raw = args.state
    elif args.state_file:
        with open(args.state_file, encoding="utf-8") as f:
            raw = f.read()
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        die("falta el state (--state, --state-file o stdin)")
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def main(argv=None):
    p = argparse.ArgumentParser(prog="mh decide", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("ask", help="decisión tipada")
    a.add_argument("--state")
    a.add_argument("--state-file")
    a.add_argument("--questions", help="JSON con {id: {type, instructions, criteria}}")
    a.add_argument("--noul", nargs=2, action="append", metavar=("ID", "PREGUNTA"), default=[])
    a.add_argument("--choice", nargs=3, action="append", metavar=("ID", "PREGUNTA", "OPCIONES"),
                   default=[], help="OPCIONES: 'a=desc,b=desc' ('other' se añade solo)")
    a.add_argument("--score", nargs=3, action="append", metavar=("ID", "PREGUNTA", "NIVELES"),
                   default=[], help="NIVELES: 'bajo|medio|alto' (2-10)")
    a.add_argument("--dry-run", action="store_true", help="muestra la petición sin enviarla")

    r = sub.add_parser("route", help="elige la skill para una tarea")
    r.add_argument("task", nargs="+")
    r.add_argument("--lexical", action="store_true", help="fuerza el motor local")

    sub.add_parser("guard", help="hook PreToolUse (JSON por stdin)")

    o = sub.add_parser("outcome", help="registra si una decisión acertó")
    o.add_argument("decision_id")
    o.add_argument("result", choices=["correct", "incorrect"])

    sub.add_parser("calibration", help="precisión observada por banda de confianza")

    args = p.parse_args(argv)
    root = find_root()

    if args.cmd == "ask":
        questions = {}
        if args.questions:
            with open(args.questions, encoding="utf-8") as f:
                questions.update(json.load(f))
        for qid, text in args.noul:
            questions[qid] = noul(text)
        for qid, text, opts in args.choice:
            questions[qid] = choice(text, parse_options(opts))
        for qid, text, levels in args.score:
            questions[qid] = score(text, [x.strip() for x in levels.split("|") if x.strip()])
        if not questions:
            die("sin preguntas (--noul, --choice, --score o --questions)")
        try:
            res = decide(read_state(args), questions, root=root, dry_run=args.dry_run)
        except JevError as e:
            die(str(e), 3 if "TYPESAFE_API_KEY" in str(e) else 2)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "route":
        if not root:
            die("no estás dentro de un proyecto metaharness")
        try:
            print(json.dumps(route(" ".join(args.task), root, force_lexical=args.lexical),
                             ensure_ascii=False, indent=2))
        except JevError as e:
            die(str(e))
    elif args.cmd == "guard":
        try:
            event = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 0
        decision, reason = guard_decision(event, root=find_root(event.get("cwd")) or root)
        if decision:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason}}, ensure_ascii=False))
    elif args.cmd == "outcome":
        if not root:
            die("no estás dentro de un proyecto metaharness")
        entries, _ = read_log(root)
        if args.decision_id not in entries:
            die("no existe la decisión %s en .ai/local/jev/log.jsonl" % args.decision_id)
        with open(os.path.join(root, ".ai", "local", "jev", "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"outcome_for": args.decision_id,
                                "correct": args.result == "correct", "ts": int(time.time())}) + "\n")
        print("registrado")
    elif args.cmd == "calibration":
        if not root:
            die("no estás dentro de un proyecto metaharness")
        print(json.dumps(calibration(root), ensure_ascii=False, indent=2))
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
