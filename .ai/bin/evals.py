#!/usr/bin/env python3
"""Evaluaciones de metaharness: la señal objetiva de la automejora.

  routing   ¿se elige la skill correcta para cada petición? (.ai/evals/routing.jsonl)
  run       ejecuta casos de comportamiento con un agente y los califica
            (.ai/evals/cases/*.json) usando Jev o un modelo juez
  report    evolución de las puntuaciones guardadas en .ai/evals/results/

Formato de un caso (.ai/evals/cases/<id>.json):
  {"id": "...", "skill": "debug-issue", "prompt": "...",
   "criteria": ["Reproduce el fallo antes de cambiar código", "..."]}

Los resultados se guardan como JSON en .ai/evals/results/ (versionados: son la
evidencia de que una mejora lo es). Solo biblioteca estándar.
"""
import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402


def die(msg, code=2):
    sys.stderr.write("eval: %s\n" % msg)
    sys.exit(code)


def save(root, kind, payload):
    d = os.path.join(root, ".ai", "evals", "results")
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, "%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), kind))
    path, i = base + ".json", 2
    while os.path.exists(path):  # la evidencia nunca se sobrescribe
        path, i = "%s-%d.json" % (base, i), i + 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return os.path.relpath(path, root)


# --------------------------------------------------------------------- routing
def eval_routing(root, cases_path, lexical):
    cases = []
    with open(cases_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                cases.append(json.loads(line))
    if not cases:
        die("sin casos en %s" % cases_path)
    policy = jev.load_policy(root)
    policy["log"] = False
    ok, misses, per_skill = 0, [], {}
    engine = None
    for c in cases:
        r = jev.route(c["text"], root, policy=policy, force_lexical=lexical)
        engine = r["engine"]
        hit = r["skill"] == c["skill"]
        ok += hit
        s = per_skill.setdefault(c["skill"], [0, 0])
        s[0] += 1
        s[1] += hit
        if not hit:
            misses.append({"text": c["text"], "expected": c["skill"], "got": r["skill"],
                           "confidence": r["confidence"]})
    return {"kind": "routing", "engine": engine, "cases": os.path.relpath(cases_path, root),
            "n": len(cases),
            "accuracy": round(ok / len(cases), 4),
            "per_skill": {k: round(v[1] / v[0], 3) for k, v in sorted(per_skill.items())},
            "misses": misses}


# --------------------------------------------------------------------- run
JUDGE_PROMPT = """Eres un evaluador estricto. Evalúa si la RESPUESTA de un agente cumple
cada CRITERIO. Responde SOLO con JSON: {"results": [true|false, ...]} en el mismo
orden que los criterios. Sin explicaciones.

TAREA:
%s

CRITERIOS:
%s

RESPUESTA DEL AGENTE:
%s
"""


def judge_with_jev(case, output, root):
    policy = jev.load_policy(root)
    policy["log"] = False
    qs = {"c%d" % i: jev.noul("¿La respuesta del agente en `output` cumple este criterio: %s?" % c)
          for i, c in enumerate(case["criteria"])}
    res = jev.decide({"task": case["prompt"], "output": output[-100000:]}, qs,
                     root=root, policy=policy)
    return [res["answers"]["c%d" % i]["value"] for i in range(len(case["criteria"]))]


def judge_with_cmd(case, output, cmd, timeout):
    crit = "\n".join("%d. %s" % (i + 1, c) for i, c in enumerate(case["criteria"]))
    prompt = JUDGE_PROMPT % (case["prompt"], crit, output[-60000:])
    out = subprocess.run(shlex.split(cmd) + [prompt], capture_output=True, text=True,
                         timeout=timeout).stdout
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise ValueError("el juez no devolvió JSON")
    results = json.loads(m.group(0))["results"]
    if len(results) != len(case["criteria"]):
        raise ValueError("el juez devolvió %d resultados para %d criterios"
                         % (len(results), len(case["criteria"])))
    return [bool(x) for x in results]


def eval_run(root, pattern, agent, judge, timeout, skill):
    files = sorted(glob.glob(os.path.join(root, pattern)))
    cases = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        if skill and c.get("skill") != skill:
            continue
        cases.append(c)
    if not cases:
        die("sin casos que coincidan con %s" % pattern)
    results, total, passed = [], 0, 0
    for c in cases:
        sys.stderr.write("eval: %s ...\n" % c["id"])
        started = time.time()
        try:
            proc = subprocess.run(shlex.split(agent) + [c["prompt"]], cwd=root,
                                  capture_output=True, text=True, timeout=timeout)
            output = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.returncode else "")
        except subprocess.TimeoutExpired:
            output = "[timeout]"
        try:
            verdicts = (judge_with_jev(c, output, root) if judge == "jev"
                        else judge_with_cmd(c, output, judge, timeout))
            err = None
        except Exception as e:  # el caso cuenta como fallido, no aborta la batería
            verdicts, err = [False] * len(c["criteria"]), str(e)
        total += len(verdicts)
        passed += sum(verdicts)
        results.append({"id": c["id"], "skill": c.get("skill"),
                        "score": round(sum(verdicts) / len(verdicts), 3),
                        "criteria": dict(zip(c["criteria"], verdicts)),
                        "seconds": round(time.time() - started, 1), "error": err})
    return {"kind": "run", "agent": agent, "judge": judge, "n": len(cases),
            "score": round(passed / total, 4) if total else 0.0, "cases": results}


# --------------------------------------------------------------------- report
def report(root):
    rows = []
    for path in sorted(glob.glob(os.path.join(root, ".ai", "evals", "results", "*.json"))):
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        metric = r.get("accuracy", r.get("score"))
        label = r.get("engine") or "%s/%s" % (r.get("agent"), r.get("judge"))
        if r["kind"] == "routing" and "holdout" in str(r.get("cases", "")):
            label += " (reservados)"
        rows.append("%s  %-8s %-28s n=%-4s %.3f" % (os.path.basename(path)[:15], r["kind"],
                                                    label[:28], r.get("n"), metric))
    return "\n".join(rows) or "(sin resultados todavía: mh eval routing)"


def main(argv=None):
    p = argparse.ArgumentParser(prog="mh eval", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("routing", help="precisión del enrutado de skills")
    r.add_argument("--cases", default=".ai/evals/routing.jsonl")
    r.add_argument("--lexical", action="store_true", help="motor local aunque haya clave")
    r.add_argument("--no-save", action="store_true")
    x = sub.add_parser("run", help="casos de comportamiento con un agente real")
    x.add_argument("--agent", required=True, help="p. ej. 'claude -p', 'codex exec', 'gemini -p'")
    x.add_argument("--judge", default="jev", help="'jev' o un comando (p. ej. 'claude -p')")
    x.add_argument("--cases", default=".ai/evals/cases/*.json")
    x.add_argument("--skill", help="solo los casos de esta skill")
    x.add_argument("--timeout", type=int, default=900)
    x.add_argument("--no-save", action="store_true")
    sub.add_parser("report", help="histórico de resultados")
    args = p.parse_args(argv)

    root = jev.find_root()
    if not root:
        die("no estás dentro de un proyecto metaharness")
    if args.cmd == "routing":
        res = eval_routing(root, os.path.join(root, args.cases), args.lexical)
    elif args.cmd == "run":
        if args.judge == "jev" and not jev.api_key():
            die("el juez 'jev' necesita TYPESAFE_API_KEY (o usa --judge 'claude -p')")
        res = eval_run(root, args.cases, args.agent, args.judge, args.timeout, args.skill)
    elif args.cmd == "report":
        print(report(root))
        return 0
    else:
        p.print_help()
        return 1
    if not args.no_save:
        res["saved"] = save(root, res["kind"], res)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
