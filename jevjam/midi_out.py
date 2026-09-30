"""Salida MIDI: planificador con reloj monótono y destinos intercambiables.

Las notas se generan un compás por adelantado y se envían a su hora exacta desde un hilo
dedicado; cada note_on tiene su note_off garantizado (y `panic()` al salir), así que un
fallo en el cerebro o en el análisis nunca deja notas colgadas.
"""
from __future__ import annotations

import heapq
import itertools
import threading
import time
from typing import Protocol

import mido


class Sink(Protocol):
    def send(self, msg: mido.Message) -> None: ...
    def close(self) -> None: ...


class VirtualPort:
    """Puerto MIDI virtual (CoreMIDI/ALSA) que ven Logic, Ableton, GarageBand o un synth."""

    def __init__(self, name: str = "JEVjam"):
        self.port = mido.open_output(name, virtual=True)

    def send(self, msg: mido.Message) -> None:
        self.port.send(msg)

    def close(self) -> None:
        self.port.close()


class NamedPort:
    """Puerto MIDI existente (p. ej. IAC Driver o un sintetizador hardware)."""

    def __init__(self, name: str):
        self.port = mido.open_output(name)

    def send(self, msg: mido.Message) -> None:
        self.port.send(msg)

    def close(self) -> None:
        self.port.close()


class Recorder:
    """Guarda lo enviado con su instante (para tests y para exportar a .mid)."""

    def __init__(self):
        self.events: list[tuple[float, mido.Message]] = []

    def send(self, msg: mido.Message) -> None:
        self.events.append((time.monotonic(), msg))

    def close(self) -> None:
        pass


class Scheduler:
    def __init__(self, sinks: list[Sink]):
        self.sinks = sinks
        self._heap: list[tuple[float, int, mido.Message]] = []
        self._seq = itertools.count()
        self._cv = threading.Condition()
        self._running = True
        self._active: set[tuple[int, int]] = set()
        self.max_late_ms = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True, name="midi-scheduler")
        self._thread.start()

    def note(self, t_on: float, dur_s: float, channel: int, note: int, velocity: int) -> None:
        with self._cv:
            heapq.heappush(self._heap, (t_on, next(self._seq),
                                        mido.Message("note_on", channel=channel, note=note, velocity=velocity)))
            heapq.heappush(self._heap, (t_on + max(0.02, dur_s), next(self._seq),
                                        mido.Message("note_off", channel=channel, note=note, velocity=0)))
            self._cv.notify()

    def message(self, t: float, msg: mido.Message) -> None:
        with self._cv:
            heapq.heappush(self._heap, (t, next(self._seq), msg))
            self._cv.notify()

    def _emit(self, msg: mido.Message) -> None:
        key = (msg.channel, msg.note) if msg.type in ("note_on", "note_off") else None
        if key:
            if msg.type == "note_on" and msg.velocity > 0:
                if key in self._active:  # re-ataque: cerramos la anterior primero
                    self._send(mido.Message("note_off", channel=key[0], note=key[1]))
                self._active.add(key)
            else:
                self._active.discard(key)
        self._send(msg)

    def _send(self, msg: mido.Message) -> None:
        for s in self.sinks:
            try:
                s.send(msg)
            except Exception:
                pass  # un destino roto no debe parar a los demás

    def _run(self) -> None:
        # time.sleep es preciso en macOS (~0,1 ms); Condition.wait con timeout no (~10 ms).
        while self._running:
            with self._cv:
                if not self._heap:
                    t = None
                else:
                    t, _, msg = self._heap[0]
            if t is None:
                time.sleep(0.002)
                continue
            dt = t - time.monotonic()
            if dt > 0.0015:
                time.sleep(min(dt - 0.001, 0.005))  # tramos cortos: un evento nuevo más temprano se atiende pronto
                continue
            while time.monotonic() < t:  # último milisegundo: espera activa
                pass
            with self._cv:
                if not self._heap or self._heap[0][0] != t:
                    continue
                heapq.heappop(self._heap)
            late = (time.monotonic() - t) * 1000
            if msg.type == "note_on":
                self.max_late_ms = max(self.max_late_ms, late)
            self._emit(msg)

    def clear_future_note_ons(self) -> None:
        """Descarta ataques pendientes (p. ej. el humano se ha parado); mantiene los note_off."""
        with self._cv:
            self._heap = [e for e in self._heap if e[2].type != "note_on"]
            heapq.heapify(self._heap)

    def panic(self) -> None:
        for ch, n in list(self._active):
            self._send(mido.Message("note_off", channel=ch, note=n))
        for ch in range(16):
            self._send(mido.Message("control_change", channel=ch, control=123, value=0))
        self._active.clear()

    def close(self) -> None:
        with self._cv:
            self._running = False
            self._heap.clear()
            self._cv.notify()
        self._thread.join(timeout=1)
        self.panic()
        for s in self.sinks:
            s.close()
