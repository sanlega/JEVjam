#!/usr/bin/env python3
"""Bucle de automejora recursiva con aceptación aplicada por código.

  mh improve run --agent claude [--iterations N] [--metric routing|behavior|CMD]
                 [--gate CMD]... [--min-gain X] [--tolerance X] [--no-merge]

Cada iteración:
  1. crea un worktree aislado (rama improve/<id>) desde HEAD
  2. mide la línea base (métrica objetivo + enrutado visible y reservado)
  3. lanza al agente, sin supervisión, con la skill self-improve, la línea base y el
     historial de intentos (aceptados y rechazados) para no repetirlos
  4. comprueba en código los invariantes: ningún archivo protegido modificado
     (evaluaciones, protocolo, guardián, umbrales, sección de invariantes...)
  5. regenera adaptadores y pasa las compuertas (`mh check` + --gate)
  6. vuelve a medir y aplica el trinquete: métrica objetivo +min-gain y ninguna
     regresión mayor que la tolerancia en el resto (incluidos los reservados)
  7. archiva la variante (.ai/memory/improvements/I-NNN.patch), registra la entrada
     I-NNN con padre y métricas en IMPROVEMENTS.md, e integra si se acepta

El agente propone; el arnés decide. Así el sistema puede mejorarse a sí mismo sin
supervisión y sin poder rebajar su propio listón. Solo biblioteca estándar.
"""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autonomy  # noqa: E402
import evals  # noqa: E402
import jev  # noqa: E402

# Invariantes: el agente no puede tocar a su juez ni a sus guardas.
PROTECTED = (
    ".ai/evals/", "template/.ai/evals/",            # evaluaciones (juez)
    ".ai/protocol.md", "template/.ai/protocol.md",  # protocolo (solo humano)
    ".ai/bin/", "bin/",                             # arnés, guardián y este bucle
    ".ai/jev.json", "template/.ai/jev.json",        # umbrales de decisión
    ".claude/settings.json", "template/.claude/",   # hooks y permisos
    ".ai/memory/IMPROVEMENTS.md", ".ai/memory/improvements/",  # registro (lo escribe el arnés)
    ".github/",                                     # CI
)
INVARIANT_FILES = (".ai/skills/self-improve/SKILL.md", "template/.ai/skills/self-improve/SKILL.md")


def die(msg, code=2):
    sys.stderr.write("improve: %s\n" % msg)
    sys.exit(code)


def log(msg):
    sys.stderr.write("improve: %s\n" % msg)
    sys.stderr.flush()


def git(cwd, *args, check=True):
    p = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout


def invariants_section(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^## Invariantes.*?(?=^## )", text, re.S | re.M)
    return m.group(0) if m else ""


# --------------------------------------------------------------------- métricas
def measure(wt, metric, behavior_agent, judge, timeout):
    """Devuelve {'target': x, 'routing': x, 'holdout': x|None}."""
    policy_env = os.environ.get("TYPESAFE_API_KEY")
    lexical = not policy_env
    out = {}
    vis = evals.eval_routing(wt, os.path.join(wt, ".ai/evals/routing.jsonl"), lexical)
    out["routing"] = vis["accuracy"]
    hold = os.path.join(wt, ".ai/evals/holdout/routing.jsonl")
    out["holdout"] = evals.eval_routing(wt, hold, lexical)["accuracy"] if os.path.isfile(hold) else None
    if metric == "routing":
        out["target"] = out["routing"]
    elif metric == "behavior":
        res = evals.eval_run(wt, ".ai/evals/cases/*.json", behavior_agent, judge, timeout, None)
        out["target"] = res["score"]
    else:
        p = subprocess.run(metric, shell=True, cwd=wt, capture_output=True, text=True,
                           timeout=timeout)
        nums = re.findall(r"-?\d+(?:\.\d+)?", p.stdout)
        if p.returncode != 0 or not nums:
            raise RuntimeError("la métrica '%s' no devolvió un número" % metric)
        out["target"] = float(nums[-1])
    return out


# --------------------------------------------------------------------- registro
def next_id(root):
    path = os.path.join(root, ".ai", "memory", "IMPROVEMENTS.md")
    n = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            n = len(re.findall(r"^## I-\d+", f.read(), re.M))
    return n + 1


def history(root, limit=8):
    path = os.path.join(root, ".ai", "memory", "IMPROVEMENTS.md")
    if not os.path.isfile(path):
        return "(sin iteraciones previas)"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    entries = re.findall(r"^## (I-\d+ · .+?)$(.*?)(?=^## I-|\Z)", text, re.S | re.M)
    lines = []
    for title, body in entries[-limit:]:
        verdict = re.search(r"\*\*Veredicto\*\*: ([^\n]+)", body)
        lines.append("- %s → %s" % (title, verdict.group(1) if verdict else "?"))
    return "\n".join(lines) or "(sin iteraciones previas)"


def parse_report(stdout):
    hyp = re.findall(r"^HIPOTESIS:\s*(.+)$", stdout, re.M)
    chg = re.findall(r"^CAMBIO:\s*(.+)$", stdout, re.M)
    return (hyp[-1].strip() if hyp else "(el agente no declaró hipótesis)",
            chg[-1].strip() if chg else "(sin descripción)")


def fmt(x):
    return "—" if x is None else "%.3f" % x


def record(root, iid, parent, agent, hypothesis, change, files, before, after, verdict, reason,
           metric):
    path = os.path.join(root, ".ai", "memory", "IMPROVEMENTS.md")
    rows = []
    for key, label in (("target", "objetivo (%s)" % metric), ("routing", "enrutado visible"),
                       ("holdout", "enrutado reservado")):
        if key == "routing" and metric == "routing":
            continue
        b, a = before.get(key), (after or {}).get(key)
        delta = "—" if b is None or a is None else "%+.3f" % (a - b)
        rows.append("  | %s | %s | %s | %s |" % (label, fmt(b), fmt(a), delta))
    entry = """
## I-%03d · %s

- **Fecha**: %s · **Agente**: %s · **Modo**: automático (`mh improve run`)
- **Padre**: %s
- **Hipótesis**: %s
- **Archivos**: %s
- **Evaluación**:
  | Métrica | Antes | Después | Δ |
  |---|---|---|---|
%s
- **Veredicto**: %s — %s
- **Variante archivada**: `.ai/memory/improvements/I-%03d.patch`
""" % (iid, change[:90], datetime.date.today().isoformat(), agent, parent or "ninguno",
       hypothesis, ", ".join(files[:12]) or "(ninguno)", "\n".join(rows), verdict, reason, iid)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


# --------------------------------------------------------------------- iteración
PROMPT = """Eres el meta-agente de metaharness en modo autónomo. Ejecuta UNA iteración de
automejora siguiendo .ai/skills/self-improve/SKILL.md, de principio a fin.

- Métrica objetivo: {metric}. Línea base: {baseline}.
- Señales: .ai/memory/LESSONS.md, secciones "## Retro" de .ai/memory/sessions/,
  resultados en .ai/evals/results/ y `.ai/bin/mh eval routing --no-save` (puedes medir).
- Historial de iteraciones (no repitas lo rechazado):
{history}
- Puedes modificar skills (.ai/skills/, o template/.ai/skills/ si existe: edita ambas
  copias igual), .ai/context/ y .ai/prompts/. NO modifiques: {protected}; ni la sección
  "Invariantes" de self-improve; no leas .ai/evals/holdout/; no hagas commit (lo hace el
  arnés, que medirá y decidirá).
- Un solo cambio pequeño y atribuible.

Al terminar imprime exactamente estas dos líneas:
HIPOTESIS: <si cambio X, la métrica sube porque Y>
CAMBIO: <resumen de una línea>
{extra}"""


def run_iteration(root, args, parent):
    iid = next_id(root)
    stamp = time.strftime("%Y%m%d%H%M%S")
    branch = "improve/I-%03d-%s" % (iid, stamp)
    wt = os.path.join(os.path.dirname(root), "%s--improve-%03d-%s" % (os.path.basename(root), iid, stamp))
    base = git(root, "rev-parse", "HEAD").strip()
    git(root, "worktree", "add", "-b", branch, wt, base)
    log("I-%03d en %s" % (iid, wt))
    keep_branch = False
    try:
        before = measure(wt, args.metric, args.behavior_agent, args.judge, args.timeout)
        log("línea base: %s" % json.dumps(before))
        inv_before = {p: invariants_section(os.path.join(wt, p)) for p in INVARIANT_FILES}
        prompt = PROMPT.format(metric=args.metric, baseline=json.dumps(before),
                               history=history(root), protected=", ".join(PROTECTED),
                               extra=args.prompt_extra or "")
        cmd = autonomy.agent_command(args.agent, autonomy.read_level(root), "")
        cmd[-1] = prompt  # el prompt del bucle sustituye a la plantilla genérica
        started = time.time()
        try:
            proc = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=args.timeout)
            stdout = proc.stdout
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
        log("agente terminó en %.0fs" % (time.time() - started))
        hypothesis, change = parse_report(stdout)

        # Cambios (incluye commits que el agente hiciera pese a la instrucción).
        git(wt, "add", "-A")
        files = [f for f in git(wt, "diff", "--cached", "--name-only", base).splitlines() if f]
        patch = git(wt, "diff", "--cached", base)
        after, verdict, reason = None, "rechazada", ""
        violations = [f for f in files if f.startswith(PROTECTED)]
        for pth, sec in inv_before.items():
            if sec is not None and invariants_section(os.path.join(wt, pth)) != sec:
                violations.append(pth + " (sección Invariantes)")
        if not files:
            reason = "el agente no produjo cambios"
        elif violations:
            reason = "viola invariantes: %s" % ", ".join(violations)
        else:
            subprocess.run([os.path.join(wt, ".ai", "bin", "mh"), "sync"], cwd=wt,
                           capture_output=True, text=True)
            gates = [".ai/bin/mh check"] + list(args.gate)
            if os.path.isdir(os.path.join(wt, "template", ".ai", "skills")):
                gates.append("diff -r template/.ai/skills .ai/skills")  # el propio framework
            failed = [g for g in gates if subprocess.run(g, shell=True, cwd=wt, capture_output=True,
                                                         timeout=args.timeout).returncode != 0]
            if failed:
                reason = "compuertas fallidas: %s" % ", ".join(failed)
            else:
                after = measure(wt, args.metric, args.behavior_agent, args.judge, args.timeout)
                gain = after["target"] - before["target"]
                regress = [k for k in ("routing", "holdout")
                           if before.get(k) is not None and after.get(k) is not None
                           and after[k] < before[k] - args.tolerance]
                if gain < args.min_gain:
                    reason = "ganancia %+.3f < mínimo %.3f" % (gain, args.min_gain)
                elif regress:
                    reason = "regresión en %s" % ", ".join(regress)
                else:
                    verdict, reason = "aceptada", "ganancia %+.3f sin regresiones" % gain

        # Archivo de variantes (aceptadas y rechazadas) + registro con linaje.
        arch = os.path.join(root, ".ai", "memory", "improvements")
        os.makedirs(arch, exist_ok=True)
        with open(os.path.join(arch, "I-%03d.patch" % iid), "w", encoding="utf-8") as f:
            f.write(patch)
        merged = False
        if verdict == "aceptada":
            git(wt, "add", "-A")
            git(wt, "commit", "-q", "-m", "improve: I-%03d %s" % (iid, change[:60]))
            if args.merge:
                git(root, "merge", "-q", "--no-edit", branch)
                merged = True
        if verdict == "aceptada" and not merged:
            keep_branch = True
            reason += " (pendiente de integrar: git merge %s)" % branch
        record(root, iid, parent, args.agent, hypothesis, change, files, before, after,
               verdict, reason, args.metric)
        git(root, "add", ".ai/memory/IMPROVEMENTS.md", ".ai/memory/improvements/")
        git(root, "commit", "-q", "-m", "improve: registro I-%03d (%s)" % (iid, verdict))
        log("I-%03d %s: %s" % (iid, verdict, reason))
        return {"id": "I-%03d" % iid, "verdict": verdict, "reason": reason, "files": files,
                "before": before, "after": after, "merged": merged}
    finally:
        git(root, "worktree", "remove", "--force", wt, check=False)
        shutil.rmtree(wt, ignore_errors=True)
        git(root, "worktree", "prune", check=False)
        # Rechazadas e integradas viven en el .patch y en la historia; su rama sobra.
        if not keep_branch:
            git(root, "branch", "-q", "-D", branch, check=False)


def main(argv=None):
    p = argparse.ArgumentParser(prog="mh improve run", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", required=True, help="claude, codex, gemini o un comando")
    p.add_argument("--iterations", type=int, default=1)
    p.add_argument("--metric", default="routing",
                   help="routing (defecto), behavior o un comando que imprima un número")
    p.add_argument("--behavior-agent", default="claude -p",
                   help="agente para --metric behavior")
    p.add_argument("--judge", default="jev")
    p.add_argument("--gate", action="append", default=[], help="comando que debe salir con 0")
    p.add_argument("--min-gain", type=float, default=0.005)
    p.add_argument("--tolerance", type=float, default=0.02)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--no-merge", dest="merge", action="store_false",
                   help="deja las variantes aceptadas en su rama sin integrar")
    p.add_argument("--prompt-extra", default="")
    args = p.parse_args(argv)

    root = jev.find_root()
    if not root:
        die("no estás dentro de un proyecto metaharness")
    if git(root, "status", "--porcelain").strip():
        die("el árbol de trabajo tiene cambios sin commit: haz commit antes de automejorar")
    if args.metric == "behavior" and args.judge == "jev" and not jev.api_key():
        die("--metric behavior con juez jev necesita TYPESAFE_API_KEY (o --judge 'claude -p')")
    results, parent = [], None
    for _ in range(args.iterations):
        r = run_iteration(root, args, parent)
        results.append(r)
        if r["verdict"] == "aceptada":
            parent = r["id"]
    print(json.dumps({"iterations": results,
                      "accepted": sum(r["verdict"] == "aceptada" for r in results)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
