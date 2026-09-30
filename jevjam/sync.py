"""Sincronía con el humano: corrección de fase y de periodo, como entre músicos.

Modelo de la psicología del ritmo (Vorberg; Wing, Endo, Bradbury y Vorberg 2014, "Optimal
feedback correction in string quartet synchronization"): cada músico mide la asincronía
entre su ataque y el del otro y corrige una fracción α de ella en el siguiente (fase) y,
más despacio, una fracción β en su tempo (periodo). B-Keeper (Robertson y Plumbley) usa
la misma idea para que un secuenciador siga a un batería, con el tempo limitado a ±5 %.

Aquí la banda corrige una vez por compás (programa un compás por adelantado) con la
asincronía media de sus pulsos.

Un desfase **constante** no es un error de fase sino latencia (micro inalámbrico, altavoces
Bluetooth, búferes): el humano ya toca "a tiempo" con lo que oye. Si se corrigiera, la banda
se retrasaría cada compás, el humano la seguiría y el tempo caería (jam real 2026-09-30
17:22: +55 ms constantes, +19 ms de corrección por compás, 100 → 99,2 BPM). Por eso se
estima ese desfase lento (`bias`) y solo se corrigen las desviaciones respecto a él.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SyncResult:
    asyncs_s: list[float] = field(default_factory=list)  # por pulso: ataque del humano − pulso de la banda
    mean_s: float = 0.0
    phase_shift_s: float = 0.0  # se suma al inicio del próximo compás
    period_s: float = 0.5  # periodo de pulso para el próximo compás
    bias_s: float = 0.0  # desfase constante estimado (latencia), que no se corrige


class BeatSync:
    def __init__(self, alpha: float = 0.4, beta: float = 0.1, window: float = 0.25, max_shift_s: float = 0.05,
                 max_tempo_step: float = 0.02, max_tempo_drift: float = 0.15, follow_tempo: bool = True,
                 bias_rate: float = 0.15, max_bias_s: float = 0.15):
        self.alpha, self.beta = alpha, beta
        self.window = window  # fracción del pulso en la que un ataque cuenta como "de ese pulso"
        self.max_shift_s = max_shift_s
        self.max_tempo_step = max_tempo_step  # cambio máx. de tempo por compás (fracción)
        self.max_tempo_drift = max_tempo_drift  # respecto al tempo inicial (evita derivas sin fin)
        self.follow_tempo = follow_tempo
        self.base_period: float | None = None
        self.bias_rate, self.max_bias_s = bias_rate, max_bias_s
        self.bias = 0.0
        self._recent: deque[float] = deque(maxlen=3)  # asincronías medias de los últimos compases
        self._bias_updates = 0
        self._slopes: deque[float] = deque(maxlen=3)
        self._periods: deque[float] = deque(maxlen=3)

    def asynchronies(self, beat_times: list[float], onsets: list[float], period: float) -> list[float]:
        """Para cada pulso, el ataque del humano más cercano dentro de la ventana (o nada)."""
        return [a for _, a in self._indexed(beat_times, onsets, period)]

    def _indexed(self, beat_times, onsets, period) -> list[tuple[int, float]]:
        out = []
        on = np.asarray(sorted(onsets))
        for k, t in enumerate(beat_times):
            if not len(on):
                break
            i = int(np.argmin(np.abs(on - t)))
            a = float(on[i] - t)
            if abs(a) <= self.window * period:
                out.append((k, a))
        return out

    def update(self, beat_times: list[float], onsets: list[float], period: float) -> SyncResult:
        if self.base_period is None:
            self.base_period = period
        indexed = self._indexed(beat_times, onsets, period)
        asyncs = [a for _, a in indexed]
        if len(asyncs) < 2:  # poca evidencia (silencio, pocos ataques): no tocamos nada
            return SyncResult(asyncs, 0.0, 0.0, period, self.bias)
        # Mediana: un ataque suelto (adorno, rasgueo a contratiempo) no arrastra la corrección.
        mean = float(np.median(asyncs))
        # La latencia se aprende despacio y solo cuando el desfase es estable varios compases (la
        # firma de una latencia); si va cambiando es tempo o fase y hay que corregirlo.
        # Pendiente del desfase dentro del compás: plana = latencia; creciente = otro tempo.
        if len(indexed) >= 3:
            ks, vals = zip(*indexed)
            slope = float(np.polyfit(ks, vals, 1)[0])  # s por pulso
            self._slopes.append(slope)
        self._periods.append(period)
        steady_tempo = (len(self._slopes) > 0 and abs(float(np.median(self._slopes))) < 0.005
                        and len(self._periods) == self._periods.maxlen
                        and np.ptp(self._periods) < 0.003 * period)  # el tempo no se está reajustando
        self._recent.append(mean)
        if (steady_tempo and len(self._recent) == self._recent.maxlen and np.ptp(self._recent) < 0.015):
            # Al principio, media simple (converge en pocos compases); después, ritmo lento.
            self._bias_updates += 1
            rate = max(self.bias_rate, 0.5 / self._bias_updates) if self.bias_rate else 0.0
            self.bias = float(np.clip(self.bias + rate * (mean - self.bias), -self.max_bias_s, self.max_bias_s))
        error = mean - self.bias
        shift = float(np.clip(self.alpha * error, -self.max_shift_s, self.max_shift_s))
        new_period = period
        # El tempo solo se corrige si la rejilla es creíble: casi todos los pulsos tienen un ataque
        # del humano cerca. Con una rejilla equivocada (tempo mal detectado) los pocos ataques que
        # caen cerca son casuales y corregir el periodo con ellos solo aleja más.
        if self.follow_tempo and len(asyncs) >= 0.75 * len(beat_times):
            step = float(np.clip(self.beta * error, -self.max_tempo_step * period, self.max_tempo_step * period))
            lo, hi = self.base_period * (1 - self.max_tempo_drift), self.base_period * (1 + self.max_tempo_drift)
            new_period = float(np.clip(period + step, lo, hi))
        return SyncResult(asyncs, mean, shift, new_period, self.bias)
