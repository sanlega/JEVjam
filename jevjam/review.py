"""Revisión de una sesión grabada: ¿la banda siguió al humano?

    python -m jevjam.review recordings/session-X            # tabla por compás + resumen
    python -m jevjam.review recordings/session-X --reanalyze   # vuelve a analizar input.wav
                                                             # con el código actual (para afinar)
    python -m jevjam.review                                 # la sesión más reciente

Escribe `review.csv` en la carpeta de la sesión.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

import numpy as np

from . import theory
from .analysis import Analyzer
from .recording import read_wav


def load_session(folder: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((folder / "meta.json").read_text()) if (folder / "meta.json").exists() else {}
    bars = [json.loads(line) for line in (folder / "bars.jsonl").read_text().splitlines() if line.strip()]
    return meta, bars


def reanalyze(folder: Path, bars: list[dict], key: tuple[int, str] | None) -> list[dict]:
    """Recalcula el acorde de cada compás del humano con el análisis actual sobre input.wav."""
    audio, sr = read_wav(folder / "input.wav")
    an = Analyzer(sr=sr, fixed_key=key)
    out, pos = [], 0
    for b in bars:
        start = int(b["bar_start_s"] * sr)
        beat = int(b["beat_s"] * sr)
        if start < pos:
            start = pos
        an.feed(audio[pos:start])
        an.take_window()
        chroma, rms = np.zeros(12), []
        for i in range(4):
            end = start + (i + 1) * beat
            an.feed(audio[start + i * beat:end])
            w = an.take_window()
            chroma += w.chroma
            rms.append(w.rms_db)
        pos = start + 4 * beat
        ch = an.chord_of(chroma)
        out.append({"bar_chord": theory.chord_name(*ch[:2]) if ch else "N",
                    "candidates": theory.chord_candidates(chroma, 3, an._allowed_chords),
                    "rms_db": float(np.mean(rms))})
    return out


def whole_file_key(folder: Path) -> list[tuple[str, float]]:
    """Las 3 tonalidades más probables sobre toda la grabación (Krumhansl-Schmuckler)."""
    audio, sr = read_wav(folder / "input.wav")
    an = Analyzer(sr=sr)
    total = np.zeros(12)
    step = sr * 2
    for i in range(0, len(audio), step):
        an.feed(audio[i:i + step])
        total += an.take_window().chroma
    total = total / (total.sum() + 1e-12)
    scores = []
    for mode, profile in (("major", theory._MAJOR_PROFILE), ("minor", theory._MINOR_PROFILE)):
        for tonic in range(12):
            scores.append((theory.key_name(tonic, mode), float(np.corrcoef(total, np.roll(profile, tonic))[0, 1])))
    return sorted(scores, key=lambda s: -s[1])[:3]


def input_quality(folder: Path, band_start_s: float | None = None) -> dict:
    """¿Sirve la entrada para analizar? Nivel, cuánto se oye la propia banda y si hay notas con altura."""
    from .recording import read_midi
    from .synth import SynthEngine

    x, sr = read_wav(folder / "input.wav")
    if len(x) < sr:
        return {}
    half = int(sr * 0.5)
    rms_db = np.array([20 * np.log10(np.sqrt(np.mean(x[i:i + half] ** 2)) + 1e-9)
                       for i in range(0, len(x) - half, half)])
    q = {"level_db": float(np.percentile(rms_db, 75)), "floor_db": float(np.percentile(rms_db, 10)),
         "clipped_pct": float(100 * np.mean(np.abs(x) > 0.99))}
    # Planitud espectral de los tramos con señal: ~0 = notas (armónicos), ~1 = ruido/golpes.
    n = 8192
    f = np.fft.rfftfreq(n, 1 / sr)
    band = (f > 60) & (f < 5000)
    flats = []
    for i in range(0, len(x) - n, n):
        seg = x[i:i + n]
        if 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9) < q["floor_db"] + 10:
            continue
        mag = np.abs(np.fft.rfft(seg * np.hanning(n)))[band] + 1e-9
        flats.append(float(np.exp(np.mean(np.log(mag))) / np.mean(mag)))
    q["flatness"] = float(np.median(flats)) if flats else None
    # Fuga de la banda al micro. Tocar sincronizados ya correlaciona las envolventes, de forma
    # ancha y a muchos retardos; el eco acústico da un pico estrecho a un retardo fijo (20-250 ms)
    # que cae casi a cero 100 ms después. Medimos esa caída, no la correlación bruta.
    midi = folder / "band.mid"
    if midi.exists() and band_start_s is not None:
        band_audio = SynthEngine(sr).render(read_midi(midi), len(x) / sr + 1)[:len(x)]
        seg = slice(int(band_start_s * sr), len(x))
        step = int(sr * 0.0025)

        def env(sig):
            sig = np.abs(sig[: len(sig) // step * step]).reshape(-1, step).mean(1)
            return sig - sig.mean()

        ea, eb = env(x[seg]), env(band_audio[seg])
        if len(ea) > 800 and np.std(eb) > 0:
            def corr(k):
                a, b = ea[k:], eb[:len(eb) - k]
                return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

            curve = np.array([corr(k) for k in range(0, 150)])  # 0-375 ms
            k = int(np.argmax(curve[:100]))
            q["band_bleed"] = max(0.0, float(curve[k] - curve[k + 32:k + 48].mean()))
            q["band_bleed_delay_ms"] = k * 2.5
    return q


def quality_advice(q: dict) -> list[str]:
    tips = []
    if not q:
        return tips
    if q.get("band_bleed", 0) > 0.25:
        tips.append(f"el micro oye a la banda (eco a {q['band_bleed_delay_ms']:.0f} ms, índice {q['band_bleed']:.2f}): "
                    f"usa auriculares; si no, el análisis escucha a la banda en vez de a ti")
    if q["level_db"] < -32:
        tips.append(f"la entrada llega muy baja ({q['level_db']:.0f} dB, ruido de fondo {q['floor_db']:.0f} dB): "
                    f"acerca el instrumento al micro, sube la ganancia o usa una interfaz de audio")
    if q["clipped_pct"] > 0.5:
        tips.append(f"la entrada satura ({q['clipped_pct']:.1f} % de muestras): baja la ganancia")
    if q.get("flatness") is not None and q["flatness"] > 0.4:
        tips.append(f"casi no hay notas con altura definida (planitud {q['flatness']:.2f}; <0,3 es un instrumento "
                    f"afinado): lo que entra es sobre todo ruido o golpes, así que no se pueden oír acordes")
    return tips


def _corr(a: list[float], b: list[float]) -> float | None:
    if len(a) < 4 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jevjam.review", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", nargs="?", help="carpeta de la sesión (por defecto, la más reciente)")
    p.add_argument("--reanalyze", action="store_true", help="recalcula los acordes del humano con el código actual")
    p.add_argument("--key", help="tonalidad fija para --reanalyze (por defecto la de la sesión)")
    args = p.parse_args(argv)

    folder = Path(args.folder) if args.folder else max(Path("recordings").glob("session-*/"), default=None)
    if folder is None or not (folder / "bars.jsonl").exists():
        p.error("no encuentro la sesión (¿carpeta con bars.jsonl?)")
    meta, bars = load_session(folder)
    if not bars:
        p.error("la sesión no tiene compases (¿la banda llegó a entrar?)")
    key_arg = args.key or meta.get("key")
    fixed_key = theory.parse_key(key_arg) if key_arg else None
    redo = reanalyze(folder, bars, fixed_key) if args.reanalyze else None

    print(f"sesión {folder}  ·  {len(bars)} compases  ·  {bars[0]['bpm']:.0f} BPM  ·  "
          f"tonalidad {'fija ' + key_arg if key_arg else 'detectada'}")
    head = (f"{'cmp':>3} {'t(s)':>6} | {'humano':7} {'sim':>4} {'candidatos':30} {'dB':>6} {'at/p':>4} | "
            f"{'volumen vs jam':24} {'tendencia':18} | {'E':>3} {'batería':10} {'bajo':11} {'teclado':13} | "
            f"{'banda':6} {'ok':2}")
    print(head)
    print("-" * len(head))
    rows_csv = []
    band_vs_human, energy, loud, dens = [], [], [], []
    for i, b in enumerate(bars):
        h, band, jev = b["human"], b["band"], b["jev"]
        d = jev["decision"]
        st = (jev.get("state_sent") or {}).get("human_player", {})
        human_chord = redo[i]["bar_chord"] if redo else h["bar_chord"]
        cands = redo[i]["candidates"] if redo else h["candidates"]
        rms = float(np.mean(h["beat_rms_db"]))
        onsets = sum(h["beat_onsets"]) / max(1, len(h["beat_onsets"]))
        ok = ""
        if band["chord_known"] and human_chord != "N":  # ¿tocó la banda el acorde que tocó el humano?
            same = band["chord"] == human_chord
            ok = "✓" if same else "✗"
            band_vs_human.append(same)
        energy.append(d["energy"])
        loud.append(rms)
        dens.append(onsets)
        cand_txt = " ".join(f"{c}:{s:.2f}" for c, s in cands)
        sim = h.get("bar_chord_similarity")
        print(f"{b['bar']:3d} {b['bar_start_s']:6.1f} | {human_chord:7s} {sim if sim is None else round(sim, 2)!s:>4} "
              f"{cand_txt[:30]:30} {rms:6.1f} {onsets:4.1f} | "
              f"{st.get('loudness_compared_to_this_jam', '')[:24]:24} {st.get('loudness_trend', '')[:18]:18} | "
              f"{d['energy']:3.1f} {band['parts_played'].get('drums', '')[:10]:10} "
              f"{band['parts_played'].get('bass', '')[:11]:11} {band['parts_played'].get('keys', '')[:13]:13} | "
              f"{(band['chord'] if band['chord_known'] else '—'):6} {ok}")
        rows_csv.append({"bar": b["bar"], "t_s": round(b["bar_start_s"], 2), "human_chord": human_chord,
                         "candidates": cand_txt, "rms_db": round(rms, 1), "onsets_per_beat": round(onsets, 2),
                         "loudness_vs_jam": st.get("loudness_compared_to_this_jam"),
                         "density_vs_jam": st.get("note_density_compared_to_this_jam"),
                         "trend": st.get("loudness_trend"), "energy": round(d["energy"], 2),
                         "drums": band["parts_played"].get("drums"), "bass": band["parts_played"].get("bass"),
                         "keys": band["parts_played"].get("keys"), "band_chord": band["chord"],
                         "band_chord_known": band["chord_known"], "match": ok,
                         "jev_latency_ms": round(d["latency_ms"]), "reused": d["reused"]})
    with (folder / "review.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_csv[0]))
        w.writeheader()
        w.writerows(rows_csv)

    # ------------------------------------------------------------------ resumen
    human_chords = [r["human_chord"] for r in rows_csv]
    clear = sum(c != "N" for c in human_chords)
    print("\nRESUMEN")
    print(f"· Acorde del humano reconocido en {clear}/{len(bars)} compases "
          f"({100 * clear / len(bars):.0f} %). Más frecuentes: {Counter(human_chords).most_common(6)}")
    if band_vs_human:
        print(f"· La banda tocó el mismo acorde que el humano en {sum(band_vs_human)}/{len(band_vs_human)} compases "
              f"comparables ({100 * sum(band_vs_human) / len(band_vs_human):.0f} %)")
    known = sum(b["band"]["chord_known"] for b in bars)
    print(f"· La banda conocía la progresión (bajo y teclado tocando) en {known}/{len(bars)} compases")
    from .keyfinder import key_from_chords

    by_chords = key_from_chords(human_chords, [np.array(b["human"]["chroma"]) for b in bars])
    band_keys = Counter(b["band"]["key"] for b in bars)
    print(f"· Tonalidad por acordes (la que usa la banda sin --key): "
          f"{theory.key_name(*by_chords[:2]) + f' (confianza {by_chords[2]:.2f})' if by_chords else '—'}; "
          f"solo por croma: " + ", ".join(f"{k} ({s:.2f})" for k, s in whole_file_key(folder)))
    print(f"· Tonalidad con la que tocó la banda: {band_keys.most_common(3)}")
    # La energía que decide Jev para el compás N se pidió con lo oído hasta el N-1.
    r_loud = _corr(loud[:-1], energy[1:])
    r_dens = _corr(dens[:-1], energy[1:])
    fmt = lambda r: "—" if r is None else f"{r:+.2f}"
    print(f"· ¿La energía de la banda sigue al humano? correlación con su volumen {fmt(r_loud)}, "
          f"con su densidad {fmt(r_dens)} (1 = sigue perfecto, 0 = no sigue)")
    # Pregunta y respuesta: ¿las notas de la frase de respuesta caen en huecos del humano?
    ans_total = ans_in_gap = 0
    for b in bars:
        gaps = b["human"].get("gaps") or []
        if b["band"]["parts_played"].get("keys") == "answer_phrase" and gaps:
            for beat in b["band"].get("keys_beats", []):
                ans_total += 1
                ans_in_gap += bool(beat < len(gaps) and gaps[beat])
    if ans_total:
        print(f"· Pregunta y respuesta: {ans_in_gap}/{ans_total} pulsos de respuesta del teclado cayeron en huecos "
              f"del humano ({100 * ans_in_gap / ans_total:.0f} %)")
    asyncs = [a for b in bars for a in (b.get("sync") or {}).get("asyncs_ms", [])]
    if len(asyncs) >= 8:
        print(f"· Sincronía con el humano: su ataque cae a {np.median(asyncs):+.0f} ms del pulso de la banda "
              f"(dispersión {np.std(asyncs):.0f} ms; entre músicos humanos es típico ±20-30 ms) en "
              f"{len(asyncs)} pulsos medidos")
    lat = [b["jev"]["decision"]["latency_ms"] for b in bars if not b["jev"]["decision"]["reused"]]
    reused = sum(b["jev"]["decision"]["reused"] for b in bars)
    if lat:
        print(f"· Jev: mediana {statistics.median(lat):.0f} ms, máx {max(lat):.0f} ms; "
              f"{reused} compases con la decisión anterior mantenida")
    q = input_quality(folder, bars[0]["bar_start_s"])
    if q:
        bleed = q.get("band_bleed")
        print(f"· Entrada: nivel {q['level_db']:.0f} dB (ruido {q['floor_db']:.0f} dB), "
              f"saturación {q['clipped_pct']:.2f} %, planitud {q['flatness'] if q['flatness'] is None else round(q['flatness'], 2)}"
              f", eco de la banda en el micro {'—' if bleed is None else f'{bleed:.2f} (>0,25 = sí)'}")
        for tip in quality_advice(q):
            print(f"  ⚠ {tip}")
    print(f"\nDetalle en {folder / 'review.csv'} · escucha {folder / 'mix.wav'} (humano a la izquierda, banda a la derecha)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
