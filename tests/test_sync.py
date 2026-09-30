"""Sincronía de fase y periodo con un humano simulado (sin audio)."""
import numpy as np
import pytest

from jevjam.sync import BeatSync


def simulate(human_bpm, band_bpm, bars=24, offset_s=0.0, jitter_s=0.01, follow_tempo=True, seed=0):
    """El humano toca a su tempo; la banda corrige por compás. Devuelve asincronías medias por compás."""
    rng = np.random.default_rng(seed)
    sync = BeatSync(follow_tempo=follow_tempo)
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


def test_phase_offset_is_corrected():
    means, _ = simulate(100, 100, offset_s=0.06)  # el humano va 60 ms "detrás" de la banda
    assert abs(means[0]) > 0.05 and abs(np.mean(means[-6:])) < 0.012


def test_follows_a_slightly_different_tempo():
    means, bpm = simulate(103, 100)
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
