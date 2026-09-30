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
from .analysis import Analyzer, Snapshot, Window
from .band import Band, Harmony
from .brain import AGENT_OPTIONS, Decision, DecisionWorker
from .context import BandMemory, build_state
from .keyfinder import KeyTracker
from .midi_out import Scheduler

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
                 fixed_key: tuple[int, str] | None = None, recorder=None):
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
        self.decision: Decision | None = None
        self.stats = {"bars": 0, "jev_on_time": 0, "jev_late": 0, "jev_errors": 0, "latencies_ms": [],
                      "bar_starts": []}
        self._audio_q: queue.Queue = queue.Queue(maxsize=4000)
        self._an_anchor = (time.monotonic(), 0.0)  # (monotónico, tiempo del analizador) del último bloque
        self._stop = threading.Event()
        self._last_harmony: Harmony | None = None
        self.beats: list[Beat] = []  # pulsos de la banda, alineados: el índice 0 es un pulso 1
        self._sent: dict[int, tuple[dict, float]] = {}  # compás → (estado enviado a Jev, instante)
        self.key_tracker = None if fixed_key else KeyTracker(bars_per_phrase=4)
        threading.Thread(target=self._analysis_loop, daemon=True, name="analysis").start()

    # ----------------------------------------------------------- audio → análisis
    def on_audio(self, block: np.ndarray) -> None:
        """Llamado desde el callback de audio: solo encola (nada de cálculo ni disco en el hilo de audio)."""
        try:
            self._audio_q.put_nowait((time.monotonic(), block))
        except queue.Full:
            pass

    def _analysis_loop(self) -> None:
        while not self._stop.is_set():
            try:
                mono, block = self._audio_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.recorder:
                self.recorder.write_audio(mono, block)
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
        if self.verbose:
            print(f"♪ escuchando a {bpm:.0f} BPM; la banda entra en {bar_start - time.monotonic():.1f} s")
        while not self._stop.is_set() and (max_bars is None or bar < max_bars):
            beat = 60 / bpm
            # 1) Plazo de la decisión de este compás.
            self._sleep_until(bar_start - 0.12)
            decision = self._collect(pending, bar)
            # 2) Armonía y notas del compás `bar`, programadas en su hora exacta.
            harmony, mode = self._harmony(bar)
            known = mode != "waiting"
            parts = dict(decision.parts)
            if not known:
                # Aún no sabemos qué acorde viene: bajo y teclado esperan (tocarían un compás tarde).
                parts.update({a: "tacet" for a in HARMONIC_AGENTS})
            if decision.human_stopped > 0.6:
                events = []
            else:
                events = self.band.render_bar(bar, parts, decision.energy, harmony, None,
                                              self.bpb, decision.leave_space > 0.6)
            for e in events:
                self.scheduler.note(bar_start + e.beat * beat, e.dur * beat, e.channel, e.note, e.velocity)
            self.memory.record(decision.parts)
            self.memory.bars_in_section += 1
            if decision.section_change > 0.7 and self.memory.bars_in_section > 2:
                self.memory.section += 1
                self.memory.bars_in_section = 0
            self._print(bar, decision, harmony, bpm, mode)
            # 3) Escuchamos el compás pulso a pulso en NUESTRA rejilla. Tras el pulso 1
            #    pedimos a Jev la decisión del compás siguiente.
            self._sleep_until(bar_start)
            self.analyzer.take_window()  # descarta lo anterior al pulso 1
            ask_after = self._ask_after_beats(beat)
            for i in range(self.bpb):
                end = bar_start + (i + 1) * beat
                self._sleep_until(end - 0.03 if i < self.bpb - 1 else end - 0.16)
                self.beats.append(self._take_beat())
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
            if self.key_tracker:
                bar_chroma = sum(b.window.chroma for b in heard)
                bc = self.analyzer.chord_of(bar_chroma)
                self.key_tracker.update(theory.chord_name(*bc[:2]) if bc else "N", bar_chroma)
            self._record_bar(bar, bar_start, bpm, harmony, mode, parts, decision, events, heard)
            # 4) Seguimos al humano: tempo y fase se corrigen poco a poco, nunca de golpe.
            bpm, bar_start = self._follow(self.analyzer.snapshot(), bpm, bar_start + self.bpb * beat)
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
                if self.verbose:
                    print(f"  ↷ alineo el pulso 1 con los cambios de acorde (+{shift} pulsos)")
            self.stats["bar_starts"].append(bar_start)
            bar += 1

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
                d = self._stabilize(d)
                self.stats["jev_on_time"] += 1
                self.stats["latencies_ms"].append(d.latency_ms)
                self.decision = d
                return d
            except Exception as exc:  # red, 429, timeout…: la música sigue
                self.stats["jev_errors"] += 1
                if self.verbose:
                    print(f"  ! Jev error en compás {bar}: {type(exc).__name__}: {exc}")
        else:
            self.stats["jev_late"] += 1
            pending.cancel()
        if self.decision is None:  # aún no hay ninguna decisión de Jev: la banda espera
            return Decision(bar=bar, parts={a: "tacet" for a in AGENT_OPTIONS}, confidence={}, energy=0.0,
                            section_change=0.0, leave_space=0.0, human_stopped=0.0, latency_ms=0.0, reused=True)
        prev = self.decision
        return Decision(**{**asdict(prev), "bar": bar, "reused": True})

    def _stabilize(self, d: Decision) -> Decision:
        """Histéresis: con poca confianza (y sin cambio de sección) se mantiene el papel anterior."""
        if self.decision is None or d.section_change > 0.7:
            return d
        parts = dict(d.parts)
        for agent, conf in d.confidence.items():
            if conf < self.min_confidence:
                parts[agent] = self.decision.parts.get(agent, parts[agent])
        d.parts = parts
        return d

    # Modos armónicos, de más a menos fiable:
    #   predicted  la progresión se repite y anticipamos el acorde del próximo compás
    #   following  seguimos el último acorde oído (va un compás tarde si el humano cambia)
    #   tonic      no oímos acordes claros pero la tonalidad es fija: sostenemos la tónica
    #   waiting    aún no sabemos nada: bajo y teclado esperan
    HARMONY_LABELS = {"predicted": "", "following": " · sigo el último acorde oído",
                      "tonic": " · sin acordes claros: sostengo la tónica", "waiting": " · aprendiendo la progresión"}

    def _harmony(self, bar: int, patience_bars: int = 4) -> tuple[Harmony, str]:
        """Armonía del próximo compás y cómo se ha decidido (ver HARMONY_LABELS)."""
        snap = self.analyzer.snapshot()
        key = self._key(snap)
        key = key if key and key[2] > 0.3 else (0, "major", 0.0)
        bars = self.bar_chords()
        predicted = predict_next_chord(bars)
        if predicted:
            mode, (root, quality) = "predicted", _CHORDS[predicted]
        elif bar >= patience_bars and bars and bars[-1] != "N":
            mode, (root, quality) = "following", _CHORDS[bars[-1]]
        elif bar >= patience_bars and self.analyzer.fixed_key:
            tonic, key_mode = self.analyzer.fixed_key
            mode, root, quality = "tonic", tonic, "maj" if key_mode == "major" else "min"
        elif self._last_harmony:
            mode, root, quality = "waiting", self._last_harmony.root, self._last_harmony.quality
        else:
            mode, root, quality = "waiting", key[0], "maj" if key[1] == "major" else "min"
        h = Harmony(root, quality, key[0], key[1])
        self._last_harmony = h
        return h, mode

    def _follow(self, snap: Snapshot, bpm: float, next_bar: float) -> tuple[float, float]:
        if self.fixed_bpm:
            new_bpm = self.fixed_bpm
        elif snap.bpm and snap.tempo_confidence > 0.2:
            ratio = snap.bpm / bpm
            # Ignoramos saltos de octava de tempo (doble/mitad); seguimos derivas suaves.
            new_bpm = bpm + (snap.bpm - bpm) * 0.25 if 0.85 < ratio < 1.15 else bpm
        else:
            new_bpm = bpm
        if snap.beat_phase_time is not None:
            beat = 60 / bpm
            human_beat = self._mono(snap.beat_phase_time)
            err = ((next_bar - human_beat + beat / 2) % beat) - beat / 2  # >0: vamos tarde
            next_bar -= float(np.clip(err * 0.3, -0.03, 0.03))
        return new_bpm, next_bar

    def _sleep_until(self, t: float) -> None:
        while not self._stop.is_set():
            dt = t - time.monotonic()
            if dt <= 0:
                return
            time.sleep(min(dt, 0.01))

    # ------------------------------------------------------------------ salida
    def _print(self, bar: int, d: Decision, h: Harmony, bpm: float, mode: str) -> None:
        known = mode != "waiting"
        self.stats["bars"] += 1
        if not self.verbose:
            return
        chord = theory.chord_name(h.root, h.quality) if known else "—"
        bars = self.bar_chords()
        heard = bars[-1] if bars else "—"
        src = "↺ mantiene" if d.reused else f"jev {d.latency_ms:4.0f} ms"
        src += self.HARMONY_LABELS[mode]
        parts = " ".join(f"{a}={p}" for a, p in d.parts.items())
        print(f"compás {bar:3d} | {bpm:5.1f} BPM | oí {heard:6s} → toco {chord:6s} en "
              f"{theory.key_name(h.key_tonic, h.key_mode):9s} | energía {d.energy:3.1f} | {parts} | {src}")

    def _record_bar(self, bar, bar_start, bpm, harmony, mode, parts, decision, events, heard) -> None:
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
            },
            "band": {
                "chord": theory.chord_name(harmony.root, harmony.quality),
                "chord_known": mode != "waiting",
                "harmony_mode": mode,
                "key": theory.key_name(harmony.key_tonic, harmony.key_mode),
                "parts_played": parts,
                "notes": dict(Counter({9: "drums", 0: "bass", 1: "keys"}.get(e.channel, e.channel) for e in events)),
            },
            "jev": {"state_sent": state, "sent_at_s": rec.rel(sent_at) if sent_at else None,
                    "decision": asdict(decision)},
        })

    def stop(self) -> None:
        self._stop.set()
