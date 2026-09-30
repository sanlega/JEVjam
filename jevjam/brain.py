"""Cerebro de la banda: Jev decide el papel de cada músico para el próximo compás.

Jev no genera notas: elige entre opciones musicales acotadas (Choice), valora la energía
(Score) y comprueba condiciones (Noul). Todas las preguntas van en UNA petición (fan-out)
porque comparten el mismo estado y son independientes.

Si la respuesta no llega antes del plazo, el conductor mantiene la última decisión de Jev.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, Score

# Opciones por músico. Las claves son las que entiende `band.py`; las descripciones son
# lo que lee Jev, así que dicen qué hace musicalmente cada opción.
AGENT_OPTIONS: dict[str, dict[str, str]] = {
    "drums": {
        "tacet": "Drums stay silent.",
        "light_time": "Soft time-keeping: closed hi-hat on eighth notes, kick on beat 1, rim or soft snare on 3.",
        "groove": "Standard backbeat groove: kick on 1 and 3, snare on 2 and 4, hi-hat eighths.",
        "driving": "Energetic rock beat: kick on every beat, loud snare on 2 and 4, open hi-hat, crash on beat 1.",
        "half_time": "Half-time feel: kick on 1, snare only on 3, spacious and heavy.",
        "fill": "A drum fill across the bar that leads into the next bar, ending with a crash.",
    },
    "bass": {
        "tacet": "Bass stays silent.",
        "roots_whole": "One long root note per chord, held for the whole bar.",
        "roots_pulse": "Root note repeated on every beat, steady and supportive.",
        "octaves": "Root alternating with its octave on eighth notes, energetic.",
        "walking": "Walking line: a different chord or scale tone on each beat, moving toward the next chord.",
        "syncopated": "Funky syncopated line with rests and anticipations around the root and fifth.",
    },
    "keys": {
        "tacet": "Keyboard stays silent to leave space.",
        "pads": "Sustained chord held for the whole bar, soft background.",
        "comping": "Short rhythmic chord stabs on off-beats, like a comping pianist.",
        "arpeggio": "Chord tones played one at a time in a flowing eighth-note arpeggio.",
        "answer_phrase": "A short melodic phrase answering the human, played in the gaps of their playing.",
    },
}

ENERGY_LEVELS = [
    "Silent: the band should not play at all.",
    "Very soft and minimal: barely there, lots of space.",
    "Soft: gentle support, low volume.",
    "Medium: a normal comfortable accompaniment volume.",
    "Strong: full band, confident and loud.",
    "Maximum: climax, as loud and intense as possible.",
]


def build_questions() -> dict:
    q: dict = {
        "energy": Score(
            instructions="How much energy should the backing band play with in the next bar, "
                         "to match and support `human_player`?",
            criteria=ENERGY_LEVELS,
        ),
        "section_change": Noul(
            instructions="Has `human_player` just started a new section of the song, with a clear change "
                         "in loudness, note density, or chords compared with before?",
            criteria={"true": "A clear new section has started.",
                      "false": "The music continues the same section."},
        ),
        "leave_space": Noul(
            instructions="Is `human_player` playing a dense or loud lead part, so the band should play "
                         "less and leave space for it?",
        ),
        "human_stopped": Noul(
            instructions="Has `human_player` stopped playing?",
        ),
    }
    for agent, options in AGENT_OPTIONS.items():
        # Sin "mantén lo anterior": Jev lo lee literalmente y se ancla. La continuidad la
        # pone el código (histéresis en conductor._stabilize).
        q[f"{agent}_part"] = Choice(
            instructions=f"You are the {agent} player in a live jam backing `human_player`. What should you "
                         f"play in the next bar to match how `human_player` is playing now, especially how loud and busy "
                         f"they are compared to the rest of this jam, and their loudness trend, "
                         f"given `band.position_in_phrase`?",
            criteria=options,
        )
    return q


@dataclass
class Decision:
    """Decisión de Jev para un compás."""

    bar: int
    parts: dict[str, str]
    confidence: dict[str, float]
    energy: float  # 0..5
    section_change: float
    leave_space: float
    human_stopped: float
    latency_ms: float
    model: str = ""
    reused: bool = False  # True si es la decisión anterior mantenida por llegar tarde
    raw: dict = field(default_factory=dict)


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga KEY=VALUE de un .env sin sobrescribir el entorno (sin dependencias)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class JevBrain:
    """Cliente asíncrono de Jev con presupuesto de tiempo por compás."""

    def __init__(self, model: str | None = None, timeout_s: float = 1.5):
        load_dotenv()
        if not os.environ.get("TYPESAFE_API_KEY"):
            raise RuntimeError("Falta TYPESAFE_API_KEY (en el entorno o en .env).")
        self.model = model or os.environ.get("JEV_MODEL", "jev-1.13.0")
        self.timeout_s = timeout_s
        self.questions = build_questions()
        # Sin reintentos largos: un reintento que llega tarde no sirve para la música.
        self.client = AsyncTypeSafeClient(
            model=self.model, timeout=timeout_s,
            retry=RetryPolicy(max_retries=1, backoff_initial=0.05, backoff_max=0.1, timeout=timeout_s),
        )

    async def decide(self, bar: int, state: dict) -> Decision:
        t0 = time.perf_counter()
        r = await self.client.system_one(state, self.questions)
        latency = (time.perf_counter() - t0) * 1000
        parts = {a: r.choices[f"{a}_part"].choice for a in AGENT_OPTIONS}
        conf = {a: float(r.choices[f"{a}_part"].confidence) for a in AGENT_OPTIONS}
        return Decision(
            bar=bar, parts=parts, confidence=conf,
            energy=float(r.scores["energy"].score),
            section_change=float(r.nouls["section_change"].noul),
            leave_space=float(r.nouls["leave_space"].noul),
            human_stopped=float(r.nouls["human_stopped"].noul),
            latency_ms=latency, model=r.model,
            raw={a: dict(r.choices[f"{a}_part"].probabilities) for a in AGENT_OPTIONS},
        )

    async def aclose(self) -> None:
        await self.client.aclose() if hasattr(self.client, "aclose") else None


class DecisionWorker:
    """Ejecuta Jev en su propio hilo con un bucle asyncio; el conductor nunca espera."""

    def __init__(self, brain: JevBrain):
        import threading

        self.brain = brain
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True, name="jev")
        self.thread.start()

    def request(self, bar: int, state: dict):
        """Lanza la decisión del compás `bar`; devuelve un concurrent.futures.Future."""
        return asyncio.run_coroutine_threadsafe(self.brain.decide(bar, state), self.loop)

    def close(self) -> None:
        fut = asyncio.run_coroutine_threadsafe(self.brain.aclose(), self.loop)
        try:
            fut.result(timeout=1)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
