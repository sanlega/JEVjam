"""Sincronía con el humano: corrección de fase y de periodo, como entre músicos.

Modelo de la psicología del ritmo (Vorberg; Wing, Endo, Bradbury y Vorberg 2014, "Optimal
feedback correction in string quartet synchronization"): cada músico mide la asincronía
entre su ataque y el del otro y corrige una fracción α de ella en el siguiente (fase) y,
más despacio, una fracción β en su tempo (periodo). B-Keeper (Robertson y Plumbley) usa
la misma idea para que un secuenciador siga a un batería, con el tempo limitado a ±5 %.

Aquí la banda corrige una vez por compás (programa un compás por adelantado) con la
asincronía media de sus pulsos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SyncResult:
    asyncs_s: list[float] = field(default_factory=list)  # por pulso: ataque del humano − pulso de la banda
    mean_s: float = 0.0
    phase_shift_s: float = 0.0  # se suma al inicio del próximo compás
    period_s: float = 0.5  # periodo de pulso para el próximo compás


class BeatSync:
    def __init__(self, alpha: float = 0.4, beta: float = 0.1, window: float = 0.25, max_shift_s: float = 0.05,
                 max_tempo_step: float = 0.02, max_tempo_drift: float = 0.15, follow_tempo: bool = True):
        self.alpha, self.beta = alpha, beta
        self.window = window  # fracción del pulso en la que un ataque cuenta como "de ese pulso"
        self.max_shift_s = max_shift_s
        self.max_tempo_step = max_tempo_step  # cambio máx. de tempo por compás (fracción)
        self.max_tempo_drift = max_tempo_drift  # respecto al tempo inicial (evita derivas sin fin)
        self.follow_tempo = follow_tempo
        self.base_period: float | None = None

    def asynchronies(self, beat_times: list[float], onsets: list[float], period: float) -> list[float]:
        """Para cada pulso, el ataque del humano más cercano dentro de la ventana (o nada)."""
        out = []
        on = np.asarray(sorted(onsets))
        for t in beat_times:
            if not len(on):
                break
            i = int(np.argmin(np.abs(on - t)))
            a = float(on[i] - t)
            if abs(a) <= self.window * period:
                out.append(a)
        return out

    def update(self, beat_times: list[float], onsets: list[float], period: float) -> SyncResult:
        if self.base_period is None:
            self.base_period = period
        asyncs = self.asynchronies(beat_times, onsets, period)
        if len(asyncs) < 2:  # poca evidencia (silencio, pocos ataques): no tocamos nada
            return SyncResult(asyncs, 0.0, 0.0, period)
        # Mediana: un ataque suelto (adorno, rasgueo a contratiempo) no arrastra la corrección.
        mean = float(np.median(asyncs))
        shift = float(np.clip(self.alpha * mean, -self.max_shift_s, self.max_shift_s))
        new_period = period
        # El tempo solo se corrige si la rejilla es creíble: casi todos los pulsos tienen un ataque
        # del humano cerca. Con una rejilla equivocada (tempo mal detectado) los pocos ataques que
        # caen cerca son casuales y corregir el periodo con ellos solo aleja más.
        if self.follow_tempo and len(asyncs) >= 0.75 * len(beat_times):
            step = float(np.clip(self.beta * mean, -self.max_tempo_step * period, self.max_tempo_step * period))
            lo, hi = self.base_period * (1 - self.max_tempo_drift), self.base_period * (1 + self.max_tempo_drift)
            new_period = float(np.clip(period + step, lo, hi))
        return SyncResult(asyncs, mean, shift, new_period)
