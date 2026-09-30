"""Fraseo: la banda cambia de papel por frases, no por compases.

Jev opina en cada compás, pero un músico no cambia de patrón a cada compás: toca una
frase entera (4 compases por defecto) y cambia al empezar la siguiente si la música lo
pide. El planificador:

- acumula los votos de Jev (sus probabilidades) durante la frase, con más peso a los
  compases recientes, y al empezar la frase nueva elige por mayoría; el papel actual se
  mantiene salvo que otro le gane por más de `margin` (0,2: con 0,1 la banda alternaba
  frase sí, frase no en una jam real, porque Jev oscila mucho compás a compás);
- cambia a todos los músicos a la vez, en el pulso 1 de la frase;
- excepción: si Jev está muy seguro de que empieza una sección nueva, cambia en el
  compás siguiente y ahí empieza una frase nueva;
- el redoble (fill) no es un papel sino un adorno: se toca en el último compás de la
  frase cuando viene un cambio o cuando Jev lo pide con fuerza;
- la energía (volumen) sigue a Jev compás a compás, pero sin saltos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ORNAMENTS = {"drums": "fill"}  # opciones que no son papeles de frase sino adornos de un compás


@dataclass
class Plan:
    bar: int
    parts: dict[str, str]  # lo que toca cada músico en este compás
    energy: float  # energía suavizada que se usa para tocar
    phrase_pos: int  # 0 = primer compás de la frase
    phrase_bars: int
    changed: bool  # este compás empieza con papeles nuevos
    reason: str  # "start" | "phrase" | "section" | ""
    fill: bool  # la batería redobla en este compás
    changed_agents: list[str] = field(default_factory=list)


class PhrasePlanner:
    def __init__(self, phrase_bars: int = 4, margin: float = 0.2, section_threshold: float = 0.85,
                 min_bars_for_section: int = 2, energy_step: float = 0.5, fill_threshold: float = 0.3):
        self.phrase_bars = phrase_bars
        self.margin = margin
        self.section_threshold = section_threshold
        self.min_bars_for_section = min_bars_for_section
        self.energy_step = energy_step
        self.fill_threshold = fill_threshold
        self.parts: dict[str, str] | None = None
        self.phrase_start = 0
        self.last_change = 0
        self.energy: float | None = None
        self._target_energy = 0.0
        self._votes: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------------ API
    def position(self, bar: int) -> int:
        """Posición de `bar` en su frase si no hay cambios de sección antes (para el estado de Jev)."""
        return (bar - self.phrase_start) % self.phrase_bars

    def plan(self, bar: int, probabilities: dict[str, dict[str, float]] | None, energy: float | None,
             section_change: float = 0.0) -> Plan:
        """Papeles y energía del compás `bar`.

        `probabilities` es la respuesta nueva de Jev para este compás (agente → opción → prob.),
        o None si no llegó a tiempo (se sigue con lo que hay).
        """
        pos = bar - self.phrase_start
        fresh = probabilities is not None
        if fresh:
            self._vote(probabilities, weight=1.0 + 0.5 * min(pos, self.phrase_bars))
        if energy is not None:
            self._target_energy = energy

        reason = ""
        if self.parts is None:
            if not fresh:
                return self._plan(bar, {}, 0, False, "", False, [])
            reason = "start"
        elif pos >= self.phrase_bars:
            reason = "phrase"
        elif (fresh and section_change >= self.section_threshold
              and bar - self.last_change >= self.min_bars_for_section):
            reason = "section"

        changed_agents: list[str] = []
        if reason:
            # En un cambio de sección los votos de la frase describen la sección que acaba:
            # manda la opinión actual de Jev. En los demás casos, la mayoría de la frase.
            new = self._choose(probabilities if reason == "section" else None)
            changed_agents = [a for a in new if self.parts is None or self.parts.get(a) != new[a]]
            if changed_agents:
                self.last_change = bar
            self.parts = new
            self.phrase_start = bar
            pos = 0
            self._votes = {}
            if fresh:  # lo que Jev opina de este compás ya cuenta para la frase nueva
                self._vote(probabilities, weight=1.0)
            if reason == "start":
                self.energy = self._target_energy

        # Redoble en el último compás de la frase si viene un cambio o si Jev lo pide con fuerza.
        fill = False
        if pos == self.phrase_bars - 1 and self.parts.get("drums", "tacet") != "tacet":
            upcoming = self._choose()
            fill = upcoming != self.parts or self._share("drums", "fill") >= self.fill_threshold

        # Energía: sigue a Jev, como mucho `energy_step` por compás.
        if self.energy is None:
            self.energy = self._target_energy
        delta = max(-self.energy_step, min(self.energy_step, self._target_energy - self.energy))
        self.energy += delta

        parts = dict(self.parts)
        if fill:
            parts["drums"] = "fill"
        return self._plan(bar, parts, pos, bool(changed_agents), reason if changed_agents else "", fill,
                          changed_agents)

    # ------------------------------------------------------------ internos
    def _plan(self, bar, parts, pos, changed, reason, fill, agents) -> Plan:
        return Plan(bar=bar, parts=parts, energy=round(self.energy or 0.0, 2), phrase_pos=pos,
                    phrase_bars=self.phrase_bars, changed=changed, reason=reason, fill=fill,
                    changed_agents=agents)

    def _vote(self, probabilities: dict[str, dict[str, float]], weight: float) -> None:
        for agent, probs in probabilities.items():
            votes = self._votes.setdefault(agent, {})
            for option, p in probs.items():
                votes[option] = votes.get(option, 0.0) + weight * float(p)

    def _share(self, agent: str, option: str) -> float:
        votes = self._votes.get(agent, {})
        total = sum(votes.values())
        return votes.get(option, 0.0) / total if total else 0.0

    def _choose(self, only: dict[str, dict[str, float]] | None = None) -> dict[str, str]:
        """Papel por mayoría ponderada de la frase; el actual se queda salvo derrota clara.

        Con `only` se decide solo con esas probabilidades y sin histéresis (cambio de sección).
        """
        out = {}
        source = only if only is not None else self._votes
        agents = set(source) | set(self.parts or {})
        for agent in agents:
            votes = {o: v for o, v in source.get(agent, {}).items() if o != ORNAMENTS.get(agent)}
            total = sum(votes.values())
            current = (self.parts or {}).get(agent)
            if not total:
                out[agent] = current or "tacet"
                continue
            shares = {o: v / total for o, v in votes.items()}
            best = max(shares, key=shares.get)
            keep = (only is None and current is not None and current in shares
                    and shares[current] >= shares[best] - self.margin)
            out[agent] = current if keep else best
        return out
