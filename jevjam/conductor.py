"""Conductor: une escucha, Jev, músicos y MIDI en un reloj musical.

Línea temporal de cada compás N (4/4 por defecto):

    pulso 1 de N        pulso 2 de N                       fin de N - margen      inicio de N+1
    |-------------------|-----------------------------------|---------------------|
                        ^ ventana del pulso 1 → petición a Jev para N+1
                                                            ^ plazo: si Jev no ha respondido
                                                              se mantiene su última decisión;
                                                              se generan y programan las notas de N+1

La escucha se resume por pulso de la banda (croma, volumen y ataques de TODO el pulso) y
por compás (suma de sus pulsos), no por instantes sueltos: con instrumentos reales un
instante de 0,3 s casi nunca contiene un acorde limpio.

La latencia de Jev (0,2–0,9 s medidos desde aquí) nunca toca el audio: solo decide si el
papel de cada músico cambia en el compás siguiente, como haría un músico humano.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np

from . import theory
from .analysis import Analyzer, LevelMeter, Snapshot, Window
from .band import Band, Harmony, NoteEvent
from .brain import AGENT_OPTIONS, Decision, DecisionWorker
from .context import BandMemory, build_state
from .dialogue import GapProfile, answer_register
from .keyfinder import KeyTracker
from .midi_out import Scheduler
from .phrasing import Plan, PhrasePlanner
from .sync import BeatSync, SyncResult

HARMONIC_AGENTS = ("bass", "keys")
_CHORDS = {theory.chord_name(r, q): (r, q) for q in theory.CHORD_QUALITIES for r in range(12)}


def predict_next_chord(bars: list[str], periods=(4, 2, 8, 3), min_agreement: float = 0.75) -> str | None:
    """Acorde del próximo compás si la progresión se repite (un acorde por compás, "N" = no claro).

    Compara las dos últimas vueltas de cada periodo candidato ignorando compases sin acorde;
    si coinciden lo bastante, el próximo compás es el que abrió la vuelta anterior.
    """
    for p in periods:
        if len(bars) < 2 * p:
            continue
        pairs = [(a, b) for a, b in zip(bars[-p:], bars[-2 * p:-p]) if a != "N" and b != "N"]
        if len(pairs) < max(2, (3 * p + 3) // 4):
            continue
        if sum(a == b for a, b in pairs) / len(pairs) >= min_agreement:
            for candidate in (bars[-p], bars[-2 * p]):
                if candidate != "N":
                    return candidate
    # Vamp: el mismo acorde tres compases seguidos.
    if len(bars) >= 3 and bars[-1] != "N" and bars[-1] == bars[-2] == bars[-3]:
        return bars[-1]
    return None


def _loudness(beats: list["Beat"]) -> float:
    power = np.mean([10 ** (b.window.rms_db / 10) for b in beats])
    return float(10 * np.log10(power + 1e-24))


@dataclass
class Beat:
    label: str  # acorde del pulso ("N" si no está claro)
    window: Window


class Conductor:
    def __init__(self, worker: DecisionWorker, scheduler: Scheduler, sr: int = 48000,
                 beats_per_bar: int = 4, fixed_bpm: float | None = None, input_latency_s: float = 0.0,
                 min_confidence: float = 0.25, verbose: bool = True,
                 fixed_key: tuple[int, str] | None = None, recorder=None, on_bar=None, on_message=None,
                 on_level=None, phrase_bars: int = 4, output_latency_s: float = 0.0):
        self.worker, self.scheduler = worker, scheduler
        self.analyzer = Analyzer(sr=sr, fixed_key=fixed_key)
        self.band = Band()
        self.memory = BandMemory()
        self.bpb = beats_per_bar
        self.fixed_bpm = fixed_bpm
        self.input_latency_s = input_latency_s
        self.min_confidence = min_confidence
        self.verbose = verbose
        self.recorder = recorder
        # Avisos para interfaces (la app web): on_bar(dict) por compás, on_message(texto, nivel).
        self.on_bar, self.on_message = on_bar, on_message
        self.on_level = on_level  # on_level({"rms_db", "peak_db"}) ~20 veces por segundo (vúmetro)
        self._level = LevelMeter(sr)
        self.decision: Decision | None = None
        self.stats = {"bars": 0, "jev_on_time": 0, "jev_late": 0, "jev_errors": 0, "latencies_ms": [],
                      "bar_starts": [], "audio_dropped": 0}
        self._audio_q: queue.Queue = queue.Queue(maxsize=4000)
        self._an_anchor = (time.monotonic(), 0.0)  # (monotónico, tiempo del analizador) del último bloque
        self._stop = threading.Event()
        self._last_harmony: Harmony | None = None
        self.beats: list[Beat] = []  # pulsos de la banda, alineados: el índice 0 es un pulso 1
        self._sent: dict[int, tuple[dict, float]] = {}  # compás → (estado enviado a Jev, instante)
        self.key_tracker = None if fixed_key else KeyTracker(bars_per_phrase=4)
        # Los papeles cambian por frases (ver phrasing.py), no compás a compás.
        self.planner = PhrasePlanner(phrase_bars=phrase_bars)
        self.memory.phrase_len = phrase_bars
        # Sincronía por corrección de fase/periodo (sync.py); con tempo fijo solo corrige la fase.
        self.sync = BeatSync(follow_tempo=not fixed_bpm)
        self.output_latency_s = output_latency_s  # lo que tarda en oírse la banda (el humano la sigue a ella)
        self.last_sync = SyncResult()
        self.gaps = GapProfile(beats_per_bar)  # huecos y registro del humano (pregunta y respuesta)
        self._last_gaps: list[bool] = []
        self._harmonic_ok = False  # bajo y teclado pueden tocar (se decide al empezar cada grupo de 4)
        self.anticipation_threshold = 0.6  # confianza mínima para tocar un acorde reconocido por progresión
        self.progression_name: str | None = None
        threading.Thread(target=self._analysis_loop, daemon=True, name="analysis").start()

    # ----------------------------------------------------------- audio → análisis
    def on_audio(self, block: np.ndarray) -> None:
        """Llamado desde el callback de audio: solo encola (nada de cálculo ni disco en el hilo de audio)."""
        try:
            self._audio_q.put_nowait((time.monotonic(), block))
        except queue.Full:
            self.stats["audio_dropped"] += 1  # el análisis no da abasto

    def _analysis_loop(self) -> None:
        while not self._stop.is_set():
            try:
                mono, block = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.recorder:
                self.recorder.write_audio(mono, block)
            if self.on_level and (level := self._level.feed(block)):
                self.on_level(level)
            self.analyzer.feed(block)
            self._an_anchor = (mono - self.input_latency_s, self.analyzer.now)

    def _mono(self, analyzer_time: float) -> float:
        mono, an = self._an_anchor
        return mono - (an - analyzer_time)

    # ------------------------------------------------------------ escucha por compás
    @property
    def chords(self) -> list[str]:
        """Acorde por pulso de la banda."""
        return [b.label for b in self.beats]

    def bar_chords(self) -> list[str]:
        """Un acorde por compás completo, a partir del croma sumado de sus pulsos."""
        out = []
        for k in range(len(self.beats) // self.bpb):
            chroma = sum(b.window.chroma for b in self.beats[k * self.bpb:(k + 1) * self.bpb])
            ch = self.analyzer.chord_of(chroma)
            out.append(theory.chord_name(ch[0], ch[1]) if ch else "N")
        return out

    def _take_beat(self) -> Beat:
        w = self.analyzer.take_window()
        loud = w.rms_db > self.analyzer.silence_db
        ch = self.analyzer.chord_of(w.chroma) if loud else None
        return Beat(theory.chord_name(ch[0], ch[1]) if ch else "N", w)

    def _key(self, snap: Snapshot) -> tuple[int, str, float] | None:
        """Tonalidad: la fija, la del rastreador por acordes o, al principio, la del croma."""
        if self.analyzer.fixed_key:
            return snap.key
        if self.key_tracker and self.key_tracker.key:
            return (*self.key_tracker.key, self.key_tracker.confidence)
        return snap.key

    def _snap(self) -> Snapshot:
        snap = self.analyzer.snapshot()
        snap.key = self._key(snap)
        snap.chord_history = self.chords
        bars = self.bar_chords()
        if bars and bars[-1] != "N":  # el acorde del último compás es más fiable que el del instante
            snap.chord = (*_CHORDS[bars[-1]], 1.0)
        return snap

    # ----------------------------------------------------------------- bucle
    def wait_for_groove(self, timeout: float = 30.0) -> Snapshot:
        """Escucha hasta tener tempo (o usa el fijo) y algo sonando."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout and not self._stop.is_set():
            snap = self.analyzer.snapshot()
            ready_tempo = self.fixed_bpm or (snap.bpm and snap.tempo_confidence > 0.2 and snap.time > 4)
            if ready_tempo and snap.silence_seconds < 0.5 and snap.beat_phase_time is not None:
                return snap
            time.sleep(0.05)
        raise TimeoutError("No detecto tempo ni sonido. ¿Está el micrófono activo? Prueba --bpm.")

    def _request(self, bar: int) -> object:
        state = build_state(self._snap(), self.memory, self.bpb)
        self._sent[bar] = (state, time.monotonic())
        return self.worker.request(bar, state)

    def run(self, max_bars: int | None = None) -> None:
        snap = self.wait_for_groove()
        bpm = self.fixed_bpm or snap.bpm
        beat = 60 / bpm
        # Primer compás: el siguiente pulso del humano con al menos 1,5 s para la primera decisión.
        bar_start = self._mono(snap.beat_phase_time)
        while bar_start < time.monotonic() + 1.5:
            bar_start += beat
        pending = self._request(0)
        bar = 0
        self._say(f"♪ escuchando a {bpm:.0f} BPM; la banda entra en {bar_start - time.monotonic():.1f} s")
        while not self._stop.is_set() and (max_bars is None or bar < max_bars):
            beat = 60 / bpm
            # 1) Plazo de la decisión de este compás.
            self._sleep_until(bar_start - 0.12)
            decision = self._collect(pending, bar)
            fresh = not decision.reused
            plan = self.planner.plan(bar, decision.raw if fresh else None, decision.energy if fresh else None,
                                     decision.section_change if fresh else 0.0)
            # 2) Armonía y notas del compás `bar`, programadas en su hora exacta.
            harmony, mode = self._harmony(bar)
            known = mode != "waiting"
            if plan.phrase_pos % 4 == 0:
                # Bajo y teclado solo entran (o se retiran por no saber la armonía) al empezar un
                # grupo de 4 compases, nunca a mitad: así también su entrada respeta la frase.
                self._harmonic_ok = known
            parts = dict(plan.parts)
            if not self._harmonic_ok:
                parts.update({a: "tacet" for a in HARMONIC_AGENTS if a in parts})
            answer_beats = self.gaps.answer_beats() if len(self.gaps.bars) >= 2 else None
            register_range = answer_register(self.gaps.register())
            self._answer_beats = answer_beats
            render_now = dict(parts)
            reactive = None
            if mode == "reactive":
                # Bajo y teclado se deciden tras oír el pulso 1; ahora solo la batería.
                reactive = {a: render_now.pop(a) for a in HARMONIC_AGENTS if a in render_now}
            events = self.band.render_bar(bar, render_now, plan.energy, harmony, None, self.bpb,
                                          decision.leave_space > 0.6, answer_beats, register_range) if parts else []
            for e in events:
                self.scheduler.note(bar_start + e.beat * beat, e.dur * beat, e.channel, e.note, e.velocity)
            self.memory.record(parts)
            if plan.reason == "section":
                self.memory.section += 1
            self.memory.phrase_pos = (plan.phrase_pos + 1) % plan.phrase_bars  # del compás que se decide ahora
            if plan.changed and plan.reason:
                what = ", ".join(f"{a}: {parts.get(a, '—')}" for a in plan.changed_agents)
                self._say(("↻ cambio de sección" if plan.reason == "section" else "↻ frase nueva") + f" → {what}")
            self._print(bar, decision, harmony, bpm, mode if self._harmonic_ok or mode == "waiting" else "waiting",
                        plan, parts)
            # 3) Escuchamos el compás pulso a pulso en NUESTRA rejilla. Tras el pulso 1
            #    pedimos a Jev la decisión del compás siguiente.
            self._sleep_until(bar_start)
            self.analyzer.take_window()  # descarta lo anterior al pulso 1
            ask_after = self._ask_after_beats(beat)
            for i in range(self.bpb):
                end = bar_start + (i + 1) * beat
                self._sleep_until(end - 0.03 if i < self.bpb - 1 else end - 0.16)
                self.beats.append(self._take_beat())
                if i == 0 and reactive:
                    reacted = self._react(bar, bar_start, beat, reactive, plan, decision, answer_beats,
                                          register_range, harmony)
                    if reacted:
                        harmony, extra = reacted
                        events += extra
                if i + 1 == ask_after:
                    # Lo que ya ha sonado de este compás también cuenta: si no, reaccionaríamos
                    # a un cambio del humano dos compases tarde en vez de uno.
                    so_far = self.beats[-(i + 1):]
                    self.memory.now_rms_db, self.memory.now_onsets_per_beat = _loudness(so_far), \
                        sum(b.window.onsets for b in so_far) / len(so_far)
                    pending = self._request(bar + 1)
            self.beats = self.beats[-64:]  # múltiplo del compás: se mantiene la alineación
            heard = self.beats[-self.bpb:]
            self.memory.record_input(_loudness(heard), sum(b.window.onsets for b in heard) / self.bpb)
            self._last_gaps = self.gaps.add_bar([b.window for b in heard])
            self.memory.phrasing = self.gaps.phrasing_words()
            self.memory.last_bar_phrasing = self.gaps.last_bar_words()
            if self.key_tracker:
                bar_chroma = sum(b.window.chroma for b in heard)
                bc = self.analyzer.chord_of(bar_chroma)
                self.key_tracker.update(theory.chord_name(*bc[:2]) if bc else "N", bar_chroma)
            # 4) Seguimos al humano: tempo y fase se corrigen poco a poco, nunca de golpe.
            next_bpm, next_start = self._follow(bpm, bar_start, beat)
            self._record_bar(bar, bar_start, bpm, harmony, mode, parts, decision, events, heard, plan)
            bpm, bar_start = next_bpm, next_start
            # 5) Pulso 1: si los cambios de acorde caen siempre en otro pulso, nos desplazamos.
            shift = self._downbeat_shift()
            if shift:
                bar_start += shift * 60 / bpm
                # La lista pasa a empezar en un pulso 1 del humano. El compás humano en curso
                # queda a medias (sus últimos pulsos caen en el hueco): lo completamos con su
                # último pulso para no saltarnos un compás en la predicción.
                self.beats = self.beats[shift:]
                rem = len(self.beats) % self.bpb
                if rem:
                    self.beats += [self.beats[-1]] * (self.bpb - rem)
                self._say(f"↷ alineo el pulso 1 con los cambios de acorde (+{shift} pulsos)")
            self.stats["bar_starts"].append(bar_start)
            bar += 1

    def _react(self, bar, bar_start, beat, parts, plan, decision, answer_beats, register_range, provisional):
        """Modo reactivo: con el acorde del pulso 1, bajo y teclado tocan desde el pulso 2."""
        label = self.beats[-1].label
        if label != "N":
            root, quality = _CHORDS[label]
        elif self.analyzer.fixed_key:
            root, quality = self.analyzer.fixed_key[0], "maj" if self.analyzer.fixed_key[1] == "major" else "min"
        else:
            return None  # no sabemos qué suena: mejor callar este compás que tocar un acorde a ciegas
        h = Harmony(root, quality, provisional.key_tonic, provisional.key_mode)
        self._last_harmony = h
        events = self.band.render_bar(bar, parts, plan.energy, h, None, self.bpb, decision.leave_space > 0.6,
                                      answer_beats, register_range)
        out = []
        for e in events:
            if e.beat >= 1.0:
                out.append(e)
            elif e.beat + e.dur > 1.05:  # notas largas (colchón, notas largas): entran en el pulso 2
                out.append(NoteEvent(1.0, e.beat + e.dur - 1.0, e.channel, e.note, e.velocity))
        for e in out:
            self.scheduler.note(bar_start + e.beat * beat, e.dur * beat, e.channel, e.note, e.velocity)
        if self.on_bar:
            self.on_bar({"bar": bar, "update": True, "playing": label if label != "N" else theory.chord_name(root, quality)})
        return h, out

    def _ask_after_beats(self, beat: float, worst_latency_s: float = 0.9) -> int:
        """Pedir a Jev lo más tarde posible (más reciente = reacciona antes) sin arriesgar el plazo."""
        for n in range(self.bpb - 1, 0, -1):
            if (self.bpb - n) * beat - 0.12 - 0.03 >= worst_latency_s:
                return n
        return 1

    def _downbeat_shift(self, min_changes: int = 3, dominance: float = 0.7) -> int:
        """Pulsos que hay que retrasar la rejilla para que los cambios de acorde caigan en el pulso 1."""
        c = self.chords
        pos = [i % self.bpb for i in range(1, len(c)) if c[i] != c[i - 1] and "N" not in (c[i], c[i - 1])]
        if len(pos) < min_changes:
            return 0
        top, n = Counter(pos).most_common(1)[0]
        return top if top != 0 and n / len(pos) >= dominance else 0

    def _collect(self, pending, bar: int) -> Decision:
        if pending.done():
            try:
                d = pending.result()
                self.stats["jev_on_time"] += 1
                self.stats["latencies_ms"].append(d.latency_ms)
                self.decision = d
                return d
            except Exception as exc:  # red, 429, timeout…: la música sigue
                self.stats["jev_errors"] += 1
                self._say(f"Jev error en compás {bar}: {type(exc).__name__}: {exc}", "warning")
        else:
            self.stats["jev_late"] += 1
            pending.cancel()
        if self.decision is None:  # aún no hay ninguna decisión de Jev: la banda espera
            return Decision(bar=bar, parts={a: "tacet" for a in AGENT_OPTIONS}, confidence={}, energy=0.0,
                            section_change=0.0, leave_space=0.0, human_stopped=0.0, latency_ms=0.0, reused=True)
        prev = self.decision
        return Decision(**{**asdict(prev), "bar": bar, "reused": True})

    # Modos armónicos, de más a menos fiable:
    #   predicted  la progresión se repite y anticipamos el acorde del próximo compás
    #   anticipated  aún no se ha repetido, pero encaja con una progresión habitual (theory)
    #   reactive   no se puede anticipar: bajo y teclado escuchan el pulso 1 del humano y
    #              entran en el pulso 2 con ese acorde (como un músico que no conoce los
    #              cambios); si el pulso 1 no trae un acorde claro, ese compás no tocan
    #              (con tonalidad fija, tónica). Sustituye a "seguir el último acorde", que
    #              iba siempre un compás tarde (jam real 17:22: 0 aciertos con acordes que
    #              no se repiten) y mantenía acordes a ciegas cuando el humano tocaba otra cosa.
    HARMONY_LABELS = {"predicted": "", "anticipated": " · reconozco la progresión",
                      "reactive": " · escucho tu acorde y entro en el pulso 2",
                      "waiting": " · aprendiendo la progresión"}

    def _harmony(self, bar: int) -> tuple[Harmony, str]:
        """Armonía del próximo compás y cómo se ha decidido (ver HARMONY_LABELS)."""
        snap = self.analyzer.snapshot()
        key = self._key(snap)
        key = key if key and key[2] > 0.3 else (0, "major", 0.0)
        bars = self.bar_chords()
        predicted = predict_next_chord(bars)
        anticipated = None
        if not predicted and (self.analyzer.fixed_key or key[2] >= 0.5):
            anticipated = theory.anticipate_chord(bars, key[0], key[1])
            if anticipated and anticipated[1] < self.anticipation_threshold:
                anticipated = None
        self.progression_name = anticipated[2] if anticipated else None
        if predicted:
            mode, (root, quality) = "predicted", _CHORDS[predicted]
        elif anticipated:
            mode, (root, quality) = "anticipated", _CHORDS[anticipated[0]]
        else:
            # No podemos anticiparla: bajo y teclado escucharán el pulso 1 del humano y entrarán
            # en el pulso 2 con ese acorde (ver run). Aquí solo queda un marcador provisional.
            last = self._last_harmony
            mode, root, quality = "reactive", (last.root if last else key[0]), (last.quality if last else "maj")
        h = Harmony(root, quality, key[0], key[1])
        self._last_harmony = h
        return h, mode

    def _follow(self, bpm: float, bar_start: float, beat: float) -> tuple[float, float]:
        """Tempo y pulso 1 del próximo compás a partir de la asincronía con el humano en este."""
        beats = [bar_start + i * beat for i in range(self.bpb)]
        mono_now, an_now = self._an_anchor
        to_an = lambda t: an_now - (mono_now - t)  # monotónico → tiempo del analizador
        onsets = [self._mono(t) - self.output_latency_s
                  for t in self.analyzer.onsets_between(to_an(beats[0] - beat / 2), to_an(beats[-1] + beat / 2))]
        r = self.last_sync = self.sync.update(beats, onsets, beat)
        next_bar, period = bar_start + self.bpb * beat + r.phase_shift_s, r.period_s
        # Re-enganche grueso: si el tempo estimado por autocorrelación difiere mucho (el humano
        # cambió de tempo de verdad y sus ataques ya caen fuera de la ventana), nos acercamos a él.
        snap = self.analyzer.snapshot()
        if not self.fixed_bpm and snap.bpm and snap.tempo_confidence > 0.2:
            ratio = snap.bpm / (60 / period)
            if 1.08 < ratio < 1.25 or 0.8 < ratio < 0.92:
                period = 60 / (60 / period + (snap.bpm - 60 / period) * 0.25)
                self.sync.base_period = period
        return (self.fixed_bpm or 60 / period), next_bar

    def _sleep_until(self, t: float) -> None:
        while not self._stop.is_set():
            dt = t - time.monotonic()
            if dt <= 0:
                return
            time.sleep(min(dt, 0.01))

    # ------------------------------------------------------------------ salida
    def plan_ahead(self, first: str, n: int = 4) -> list[str]:
        """Los próximos `n` acordes que la banda espera tocar (para enseñarlos, como ReaLJam)."""
        snap_key = self._key(self.analyzer.snapshot())
        bars, plan = self.bar_chords() + [first], [first]
        for _ in range(n - 1):
            nxt = predict_next_chord(bars)
            if not nxt and snap_key and (self.analyzer.fixed_key or snap_key[2] >= 0.5):
                a = theory.anticipate_chord(bars, snap_key[0], snap_key[1])
                nxt = a[0] if a and a[1] >= self.anticipation_threshold else None
            if not nxt:
                break
            plan.append(nxt)
            bars.append(nxt)
        return plan

    def _say(self, text: str, level: str = "info") -> None:
        if self.on_message:
            self.on_message(text, level)
        if self.verbose:
            print(("  ! " if level == "warning" else "  ") + text)

    def _print(self, bar: int, d: Decision, h: Harmony, bpm: float, mode: str, plan: Plan,
               parts: dict[str, str]) -> None:
        self.stats["bars"] += 1
        known = mode != "waiting"
        chord = theory.chord_name(h.root, h.quality) if known else "—"
        bars = self.bar_chords()
        heard = bars[-1] if bars else "—"
        key = theory.key_name(h.key_tonic, h.key_mode)
        if self.on_bar:
            self.on_bar({"bar": bar, "bpm": round(bpm, 1), "heard": heard, "playing": chord, "key": key,
                         "key_fixed": bool(self.analyzer.fixed_key), "energy": plan.energy,
                         "jev_energy": round(d.energy, 2), "parts": parts, "jev_parts": d.parts,
                         "phrase_pos": plan.phrase_pos, "phrase_bars": plan.phrase_bars,
                         "changed": plan.changed, "change_reason": plan.reason, "fill": plan.fill,
                         "confidence": d.confidence, "latency_ms": round(d.latency_ms),
                         "reused": d.reused, "harmony_mode": mode, "progression": self.progression_name,
                         "sync_ms": round(self.last_sync.mean_s * 1000, 1),
                         "phrasing": self.memory.phrasing, "answer_beats": self.gaps.answer_beats(),
                         "plan": self.plan_ahead(chord) if known else [],
                         "section_change": round(d.section_change, 2), "leave_space": round(d.leave_space, 2)})
        if not self.verbose:
            return
        src = "↺ mantiene" if d.reused else f"jev {d.latency_ms:4.0f} ms"
        src += self.HARMONY_LABELS[mode]
        txt = " ".join(f"{a}={p}" for a, p in parts.items())
        print(f"compás {bar:3d} | frase {plan.phrase_pos + 1}/{plan.phrase_bars} | {bpm:5.1f} BPM | oí {heard:6s} → "
              f"toco {chord:6s} en {key:9s} | energía {plan.energy:3.1f} | {txt} | {src}")

    def _record_bar(self, bar, bar_start, bpm, harmony, mode, parts, decision, events, heard, plan) -> None:
        if not self.recorder:
            return
        rec = self.recorder
        state, sent_at = self._sent.pop(bar, (None, None))
        chroma = sum(b.window.chroma for b in heard)
        human_bar = self.analyzer.chord_of(chroma)
        rec.write_bar({
            "bar": bar,
            "bar_start_s": rec.rel(bar_start),
            "bpm": bpm,
            "beat_s": 60 / bpm,
            "human": {
                "bar_chord": theory.chord_name(*human_bar[:2]) if human_bar else "N",
                "bar_chord_similarity": human_bar[2] if human_bar else None,
                "candidates": theory.chord_candidates(chroma, 3, self.analyzer._allowed_chords),
                "beat_chords": [b.label for b in heard],
                "beat_rms_db": [round(b.window.rms_db, 1) for b in heard],
                "beat_onsets": [b.window.onsets for b in heard],
                "chroma": (chroma / (chroma.sum() + 1e-12)).round(3),
                "gaps": self._last_gaps,
                "register": round(self.gaps.register(), 1) if self.gaps.register() else None,
            },
            "band": {
                "chord": theory.chord_name(harmony.root, harmony.quality),
                "chord_known": mode != "waiting",
                "harmony_mode": mode,
                "key": theory.key_name(harmony.key_tonic, harmony.key_mode),
                "parts_played": parts,
                "energy_played": plan.energy,
                "phrase": {"pos": plan.phrase_pos, "bars": plan.phrase_bars, "changed": plan.changed,
                           "reason": plan.reason, "fill": plan.fill},
                "notes": dict(Counter({9: "drums", 0: "bass", 1: "keys"}.get(e.channel, e.channel) for e in events)),
                "keys_beats": sorted({int(e.beat) for e in events if e.channel == 1}),
                "answer_beats": getattr(self, "_answer_beats", None),
            },
            "sync": {"asyncs_ms": [round(a * 1000, 1) for a in self.last_sync.asyncs_s],
                     "mean_ms": round(self.last_sync.mean_s * 1000, 1),
                     "phase_shift_ms": round(self.last_sync.phase_shift_s * 1000, 1),
                     "latency_ms": round(self.last_sync.bias_s * 1000, 1),
                     "bpm_next": round(60 / self.last_sync.period_s, 2)},
            "jev": {"state_sent": state, "sent_at_s": rec.rel(sent_at) if sent_at else None,
                    "decision": asdict(decision)},
        })

    def stop(self) -> None:
        self._stop.set()
