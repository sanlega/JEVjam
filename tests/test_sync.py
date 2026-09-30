"""Sincronía de fase y periodo con un humano simulado (sin audio)."""
import numpy as np
import pytest

from jevjam.sync import BeatSync


def simulate(human_bpm, band_bpm, bars=24, offset_s=0.0, jitter_s=0.01, follow_tempo=True, seed=0, **kw):
    """El humano toca a su tempo; la banda corrige por compás. Devuelve asincronías medias por compás."""
    rng = np.random.default_rng(seed)
    sync = BeatSync(follow_tempo=follow_tempo, **kw)
    human_period, period = 60 / human_bpm, 60 / band_bpm
    human_onsets = [offset_s + i * human_period + rng.normal(0, jitter_s) for i in range(bars * 4 + 8)]
    bar_start, means = 0.0, []
    for _ in range(bars):
        beats = [bar_start + i * period for i in range(4)]
        r = sync.update(beats, human_onsets, period)
        means.append(r.mean_s)
        bar_start = bar_start + 4 * period + r.phase_shift_s
        period = r.period_s
    return means, 60 / period


def test_phase_offset_is_corrected_when_not_mistaken_for_latency():
    means, _ = simulate(100, 100, offset_s=0.06, bias_rate=0.0)  # sin modelo de latencia: corrige todo
    assert abs(means[0]) > 0.05 and abs(np.mean(means[-6:])) < 0.012


def human_following_band(offset_s, bars=40, bias_rate=0.15):
    """El humano toca siguiendo lo que OYE de la banda, con una latencia fija (p. ej. micro inalámbrico)."""
    sync = BeatSync(follow_tempo=False, bias_rate=bias_rate)
    period, bar_start, starts = 0.6, 0.0, []
    for _ in range(bars):
        beats = [bar_start + i * period for i in range(4)]
        onsets = [b + offset_s for b in beats]  # el humano cae siempre `offset_s` detrás
        r = sync.update(beats, onsets, period)
        starts.append(bar_start)
        bar_start += 4 * period + r.phase_shift_s
    return np.diff(starts), r


def test_constant_latency_does_not_slow_the_band_down():
    # Regresión (jam real 17:22): +55 ms constantes hacían que la banda se retrasara cada compás.
    bar_lengths, r = human_following_band(0.055)
    assert r.bias_s == pytest.approx(0.055, abs=0.005)
    assert np.mean(bar_lengths[-20:]) == pytest.approx(2.4, abs=0.002)  # tempo estable
    naive, _ = human_following_band(0.055, bias_rate=0.0)
    assert np.mean(naive[-20:]) > 2.41  # sin el modelo de latencia, la banda se ralentiza


def test_latency_is_learned_within_a_few_bars():
    _, r = human_following_band(0.055, bars=12)
    assert r.bias_s == pytest.approx(0.055, abs=0.01)


def test_follows_a_slightly_different_tempo():
    means, bpm = simulate(103, 100, bars=40)
    # Un cambio de tempo no se confunde con latencia: el desfase crece dentro del compás.
    assert bpm == pytest.approx(103, abs=1.2) and abs(np.mean(means[-6:])) < 0.02


def test_fixed_tempo_only_corrects_phase():
    _, bpm = simulate(103, 100, follow_tempo=False)
    assert bpm == 100


def test_no_evidence_no_change():
    sync = BeatSync()
    r = sync.update([0.0, 0.6, 1.2, 1.8], [], 0.6)
    assert r.phase_shift_s == 0 and r.period_s == 0.6


def test_offbeat_strum_is_ignored():
    sync = BeatSync()
    # Ataques en los pulsos 1-4 (+10 ms) y un rasgueo a contratiempo que no debe contar.
    r = sync.update([0.0, 0.6, 1.2, 1.8], [0.01, 0.61, 0.9, 1.21, 1.81], 0.6)
    assert r.mean_s == pytest.approx(0.01, abs=1e-6)


def test_tempo_changes_are_bounded():
    sync = BeatSync()
    r = sync.update([0.0, 0.6, 1.2, 1.8], [0.14, 0.74, 1.34, 1.94], 0.6)  # humano muy detrás
    assert r.phase_shift_s <= sync.max_shift_s and r.period_s <= 0.6 * (1 + sync.max_tempo_step) + 1e-9


def test_tempo_is_not_corrected_on_an_implausible_grid():
    sync = BeatSync()
    # Solo 2 de 4 pulsos con ataque cerca: la fase se corrige, el tempo no.
    r = sync.update([0.0, 0.6, 1.2, 1.8], [0.03, 0.63], 0.6)
    assert r.phase_shift_s > 0 and r.period_s == 0.6
