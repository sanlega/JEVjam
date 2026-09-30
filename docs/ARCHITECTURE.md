# JEVjam: technical architecture of the MVP

> Goal: make playing with an AI feel like **improvising with another musician**, not like
> using a generator. This page collects the research, the decisions and what has been
> measured in the proof of concept (`jevjam/`).

## 1. What Jev really is (and isn't)

Source: TypeSafe's live documentation (docs.typesafe.ai, jev‑1.13, reviewed 2026‑09‑30).

| Jev **does** | Jev **doesn't** |
|---|---|
| Take a **text/JSON** `state` and typed questions | Take audio, binary MIDI or images (text only) |
| Return a **Choice** (1 of ≤255 options + probabilities), a **Score** (2‑10 ordered levels) or a **Noul** (probability of yes) | Generate text, notes, sequences or MIDI ("use a generative model") |
| Evaluate all questions in a request in parallel over the same state (fan‑out) | Chain reasoning between questions in the same request |
| Return calibrated probabilities + `confidence` to decide when to act | Do arithmetic, count, or compare numbers precisely |
| ~100 ms according to the docs; **measured from here: median 230‑275 ms, max ~0.9 s** (includes network) | Run locally (cloud API; 40 req/s, 64k tokens per request) |

**Design consequence:** Jev can't "play". It can do what a musician does in a split second:
*judge*. Should I raise the energy? Play a fill? Leave space? Has the section changed? Which
role do I play in the next bar? Everything exact (which notes fit, when they sound, their
velocity) is done by deterministic code. This is TypeSafe's "select instead of generate"
pattern applied to music.

## 2. Architecture

```
┌──────────────────────────── LOCAL (real time) ──────────────────────────────┐
│                                                                              │
│  mic / interface ──► [capture] ──queue──► [analysis]  every ~10 ms           │
│   (sounddevice,        256 samples          onsets, tempo, beat phase,       │
│    5.3 ms/block)                            chroma→chord, key,               │
│                                             dynamics, density, silence       │
│                                                 │ Snapshot (numbers)         │
│                                                 ▼                            │
│                                     [conductor: musical clock]               │
│                                      · its own bar grid                      │
│                                      · downbeat from chord changes           │
│                                      · learns and PREDICTS the progression   │
│                                      · follows tempo/phase smoothly          │
│                     context in words │               ▲ Decision             │
│                     (context.py)     ▼               │ (or the last one)    │
│                              ┌────────── Jev thread (asyncio) ─────────┐     │
│                              │ 1 request/bar, fan‑out of 7 questions   │     │
│                              └──────────────────┬──────────────────────┘     │
│                                                 │ (cloud, 0.2‑0.9 s)         │
│  [musicians: band.py]  ◄── role + energy + predicted harmony                 │
│   drums · bass · keys  →  one bar of NoteEvents, deterministic               │
│                 │                                                            │
│                 ▼                                                            │
│  [MIDI scheduler]  monotonic clock, <1 ms precision, guaranteed note_off     │
│        │                       │                        │                    │
│        ▼                       ▼                        ▼                    │
│  built-in synth       virtual port "JEVjam"       existing port              │
│  (numpy)              (Logic, Ableton, GarageBand, VSTs)  (IAC, hardware)    │
└──────────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ POST /v1/systemone
                              Jev (TypeSafe)
```

### Two loops, two time scales

| Loop | Frequency | Where | What it decides | If it fails |
|---|---|---|---|---|
| **Reflex** (real time) | every block/beat | local | when each note sounds, tempo, phase, chord | — (it's code) |
| **Judgment** (musical) | once per bar | Jev | role of each musician, energy, section, space | Jev's last decision is kept |

This way Jev's latency **never** touches the audio. A human musician doesn't change role in
the middle of an eighth note either: they decide where the next bar is going while playing
the current one.

### Timeline of a bar (implemented in `conductor.py`)

```
bar N:   |beat 1 ─────|beat 2 ─────|beat 3 ─────|beat 4 ───── ▲ ─|bar N+1
              ▲ snapshot + request to Jev for N+1   deadline = start of N+1 − 120 ms:
                                                    decision (or the previous one) → notes for N+1
```

Budget for Jev: ~3 beats minus 120 ms → 1.68 s at 100 BPM, 0.88 s at 180 BPM.
Measured: 70/70 decisions on time across 4 test jams (medians 234‑275 ms, max 702 ms).
(Later the request moved to after beat 2 when the tempo allows it; see §7.)

## 3. Answers to the questions in the brief

### What runs locally
Capture, analysis, clock, harmonic prediction, note generation, MIDI scheduling and
synthesis. In other words: **everything that has a deadline**. The only remote part is Jev's
judgment, and it has a plan B (keep the previous decision), so a network outage degrades the
band's creativity, not the music.

### What Jev does
One request per bar with 7 fan‑out questions (`brain.py`):

| id | Type | Question (summary) | Used in code for |
|---|---|---|---|
| `energy` | Score 0‑5 | how much energy should the band play with? | velocity; <0.5 = silence |
| `section_change` | Noul | has the human started a new section? | section counter; can cut a phrase short |
| `leave_space` | Noul | is the human playing a dense/loud solo that needs room? | sparser comping |
| `human_stopped` | Noul | has the human stopped playing? | the band stops |
| `drums_part` | Choice ×6 | tacet / light_time / groove / driving / half_time / fill | drum pattern |
| `bass_part` | Choice ×6 | tacet / roots_whole / roots_pulse / octaves / walking / syncopated | bass pattern |
| `keys_part` | Choice ×5 | tacet / pads / comping / arpeggio / answer_phrase | keys pattern |

Every option carries a concrete musical description (which is what Jev reads). Adding a
musician = adding an entry to `AGENT_OPTIONS` and its generator in `band.py`; it is still
**one single request** (≈1,340 input tokens per bar ≈ $0.08/hour at 100 BPM).

Lessons measured with Jev:
- Asking it to "stay consistent with what you played" **anchors** it: it never changed role
  even when the energy went from 1.3 to 4.1. Without that sentence it picks
  `light_time/roots_whole/pads` when the human is soft and `driving/octaves/comping` when loud
  (confidence 0.8‑0.9). Continuity belongs in code. (At first this was confidence
  hysteresis; it is now the phrase planner, see §7 "Phrasing".)
- With the state in words it does the musically sensible thing without rules: a **fill**
  right in the transition bar and `driving → groove` once the new section settles.

### How to represent the context (`context.py`)
Jev struggles with numbers (see the "jaggedness" docs), so code translates measurements
into named categories and keeps the state small (context rot):

```json
{
  "human_player": {
    "tempo": "medium (about 100 BPM)", "key": "C major", "current_chord": "Am",
    "progression": {"recent_bars": ["Am","F","C","G"], "harmonic_rhythm": "chords change every bar or so"},
    "loudness": "loud", "loudness_trend": "getting much louder",
    "note_density": "moderate (eighth-note feel)", "playing": "playing"
  },
  "band": {"position_in_phrase": "last bar of a phrase, leading into a new phrase", "section": "section 1"}
}
```

The position in the phrase is computed in code and handed over in words, so Jev can decide
on a fill "at the end of the phrase" without counting bars. (Later additions: loudness and
density *relative to the rest of the jam*, and the player's phrasing/gaps; see §7.)

### How to detect BPM, key, chords and notes fast enough (`analysis.py`)
All numpy, 512‑sample hop (10.7 ms), 4096‑point FFT; ~110× faster than real time.

| Feature | MVP method | Test results |
|---|---|---|
| Onsets | log spectral flux + adaptive threshold | — |
| Tempo | autocorrelation of the onset envelope (8 s), log‑normal prior at 110 BPM, parabolic peak | ±0.1 BPM at 84‑150 BPM (synthetic) |
| Beat phase | circular mean of the onsets' phase | replaced by `sync.py` (§7) |
| Downbeat | dominant position of chord changes | aligns in 2‑3 bars |
| Chord | **magnitude** chroma (38 Hz‑2.1 kHz) vs. templates with the **harmonic series** modelled; sevenths penalised | 56/56 synthetic; real jam F‑E‑Am‑G 22/22 (with energy chroma the guitar E came out 0/5) |
| Key | **chord-based tracker** (`keyfinder.py`): diatonic fit + tonic presence + chroma profile, with hysteresis; or fixed with `--key` | 11/11 progressions; follows modulations in 3‑5 bars; real jam C‑G‑F‑G: C major (chroma alone: G major) |
| Dynamics / trend / density / silence | RMS in dB, 2 s vs. previous 6 s, onsets per beat | — |

The chord of the **next** bar can't be heard in time: the band **learns the progression**
(it looks for a repeating 4/2/8/3/1‑bar cycle) and anticipates it. (Originally bass and keys
waited until they had learned it; they now also recognise common progressions and, failing
that, react within the bar; see §7.)

### How Jev returns its decisions
As typed answers (`choice` + `probabilities` + `confidence`, `score`, `noul`) that code
consumes without parsing text. The probabilities are stored in the session log
(`recordings/*/bars.jsonl`) to calibrate thresholds with real jams.

### How to generate MIDI reliably (`band.py`, `midi_out.py`)
- **Deterministic generators per bar** (seed = bar): reproducible and testable.
- Minimum‑distance voice leading; notes always from the chord or the scale (tested).
- Scheduler on its own thread with a monotonic clock: measured max lateness **0.4‑1.7 ms**.
- Every `note_on` has its `note_off` scheduled; re‑attacks close the previous note;
  `panic()` (All Notes Off, CC123) on exit. Nothing hangs even if Jev or the network fails.
- GM channels: 10 drums, 1 bass, 2 keys → works with any DAW/sampler.

### How to keep Jev's latency from breaking the jam
1. Jev off the critical path: it decides the **next** bar.
2. Hard deadline per bar; if it doesn't arrive, the last decision is kept (never wait).
3. Bounded retries (1, 50‑100 ms backoff, 1.5 s timeout): a late retry is useless.
4. One single request per bar (fan‑out) instead of one per musician.
5. Stability in code so the band doesn't "wobble" between options (now: phrases, §7).

## 4. Stack

**MVP (current): Python 3.14**: fast iteration, numpy, the official TypeSafe SDK.

| Piece | MVP choice | Why |
|---|---|---|
| Audio I/O | `sounddevice` (PortAudio) | 256‑sample blocks, Core Audio/ASIO/ALSA |
| Analysis | own numpy code | predictable latency, no heavy dependencies |
| Jev | `typesafe-sdk` (async) | official client, configurable retries |
| MIDI | `mido` + `python-rtmidi` | native virtual port on macOS/Linux |
| Instrument | built-in synth (numpy) or a DAW | try it with nothing installed |

**Evolution (VST/AU, desktop, DAW):** the audio path moves to C++/Rust; the brain stays a
separate process/service:

```
Plugin (JUCE C++ or nih-plug Rust)          JEVjam service (Python or Rust)
  analysis + clock + generators   ◄──IPC/OSC──►  context + Jev + jam memory
  sample-accurate MIDI out                       (same Decision contract)
```
- **JUCE** (VST3/AU/standalone; GPLv3 or commercial licence) or **nih-plug** (Rust, VST3/CLAP).
- **Ableton Link** to share tempo with the DAW and other apps (GPL/commercial licence).
- As a plugin, the host's position/tempo replace tempo detection.

## 5. Libraries worth using (next iterations)

| Library | For | Beware |
|---|---|---|
| aubio | real-time onsets, tempo, YIN pitch (C) | GPL‑3 |
| Essentia | key, chords, beat tracking, streaming mode (C++) | AGPL‑3 or commercial licence |
| madmom | reference beat/downbeat tracking (RNN+DBN), online mode | models under a non-commercial licence |
| BeatNet | real-time beat/downbeat/meter (CRNN + particle filter) | validate latency |
| CREPE | accurate monophonic pitch (voice, solo instrument) | GPU/CPU cost |
| Basic Pitch (Spotify) | polyphonic audio→MIDI | windowed: not suited to low latency |
| librosa | offline analysis and prototyping | not real time |
| FluidSynth + GM SoundFont | quality instrument without a DAW | LGPL |

## 6. What had to be built

- Translation of measurements → context in words (the "interface" with Jev) and its evaluation.
- Catalogue of roles per musician (options + descriptions) and their MIDI generators.
- A musical clock that follows the human (tempo, phase, downbeat) and progression prediction.
- Policy: deadlines, stability, learning the progression.
- Jam recording to calibrate thresholds and improve the questions (the *autoresearch* pattern).

## 7. First tests with a real instrument (2026-09-30) and the changes they led to

Seven real jams by the user (no audio recorded yet) showed:

| Symptom | Cause | Change |
|---|---|---|
| "no clear chord" in 66 % of bars | chord decided from 0.3 s of chroma with a 0.7 threshold tuned for synthetic audio | chord per **beat and bar window** (summed chroma); threshold 0.65 (0.55 with `--key`) |
| the band stuck on F for ~20 bars | prediction discarded bars without a chord and saw a "cycle" of a single F | prediction treats "N" bars as gaps, ≥75 % agreement between cycles; regression test |
| density "moderate" in 52/53 bars; "very soft/silent" while playing | absolute descriptors depending on the mic gain | descriptors **relative to the jam itself** (`loudness_compared_to_this_jam`, `note_density_compared_to_this_jam`) and a bar-based trend |
| slow reaction | Jev only saw complete bars: it reacted 2 bars late | what has already sounded in the current bar counts, and Jev is asked after beat 2 when the tempo allows it (≤ ~125 BPM) → 1 bar |

Second real jam, now recorded (`session-20260930-150212`, `--key C`): only the drums played.
The audio review showed the problem was the capture, not the analysis: the laptop mic heard
the band through the speakers (echo at 60 ms) and the player's own input was mostly noise
and knocks (spectral flatness 0.6; a pitched instrument gives <0.3), so in 29/31 bars there
was no chord to hear and bass and keys waited forever. It turned out the wrong mic was
selected. Changes: fallback harmony modes after 4 bars (later replaced by the reactive mode,
below) and an input diagnosis (level, band bleed, flatness) in the review and at the end of
every session.

Also, every session is recorded (`recording.py`) and reviewed (`review.py`), and a jam can
be replayed from its `input.wav` to compare code versions on the same input.

### Real-time key detection: state of the art and choice

| Project | Method | Real time | Licence |
|---|---|---|---|
| libKeyFinder (Mixxx) | chroma + key profiles | designed for tracks; usable on segments | GPL‑3 |
| Queen Mary key detector (qm‑dsp, Vamp) | chroma + profiles, incremental | yes | GPL |
| Essentia `Key`/`KeyExtractor` | profiles (Krumhansl, Temperley, edma…) | streaming mode | AGPL‑3 |
| madmom | CNN | no (whole track) | non-commercial models |
| Antares Auto‑Key, Mixed In Key | proprietary | Auto‑Key yes | commercial |

They all compare chroma with profiles, and with few bars they confuse neighbouring keys
(C and G major share 6 of 7 notes). Since JEVjam already recognises chords per bar, the key
is deduced from them: which key contains the chords (an F natural rules out G major), which
one has its tonic chord present and opening phrases (C major vs. A minor), and the chroma
profile as a tie-breaker. Memory with 0.8 decay per bar; the key only changes if another
key wins 2 bars in a row.

### The E that wasn't heard (jam 2026-09-30 16:31)

"It loses the input": the audio had no dropouts (a single 10 ms gap); what got lost was the
harmony. In F‑E‑Am‑G the E came out "no chord" 5 times out of 5: with energy chroma
(magnitude²) the low E string dominated and the G# was left at 2 %. Without the E the
progression was never learned and the key jumped between F, C and A minor. With magnitude
chroma: E 5/5, 22/22 chords, stable A minor and 14/14 band chords in predicted mode. Lost
audio blocks (device overflow or saturated analysis) are now also counted and reported at
the end.

### Long jam of 2026-09-30 17:22 (75 bars, 3 min)

| Section | Problem | Change | Before → after (same input) |
|---|---|---|---|
| chords that don't repeat | "follow the last chord" was always one bar late | **reactive mode**: bass and keys listen to beat 1 and come in on beat 2 with that chord; with no clear chord they stay silent (tonic with `--key`) | 1/17 → 10/17 |
| playing softly without clear chords | the band held F blindly for 5 bars | the same: with no clear chord, nothing is made up | — |
| timing | a constant +55 ms (wireless mic + speakers) corrected as an error: the band delayed itself every bar and the tempo fell to 99.1 | `sync.py` estimates the **latency** (stable offset, stable tempo and no slope within the bar) and only corrects deviations from it | stable tempo; latency estimated at ~60 ms |
| replaying a file | the band kept playing after the audio ended | the session stops when the source ends | — |

Built-in synth rebuilt (`synth.py`): FM electric piano, additive bass, drums with band-pass
noise (difference of moving averages), stereo, vectorised Schroeder reverb and a soft
limiter; levels balanced by measuring each instrument (kick −20.7, bass −22.5, keys −23.7,
snare −24.0, hi-hat −31.9 dB); 1.7 ms per 256‑sample block.

### Phrasing (`phrasing.py`)

In real jams the band changed role every 1.2–2 bars: Jev decides bar by bar and swings a lot
(1.0 for "soft" in one bar, 0.65 for "full on" in the next). Now:

- Jev's votes (probabilities) are accumulated during the phrase and the majority decides at
  the start of the next one; the current role stays unless another beats it by > 0.2 (with
  0.1 the band alternated every other phrase in the real jam);
- all musicians change together, on beat 1 of the phrase (2/4/8/16 bars);
- exception: Jev's `section_change` ≥ 0.85 changes in the next bar (deciding with the
  current opinion, not with the votes of the section that is ending) and opens a new phrase;
- the fill is an ornament of the last bar of the phrase, not a role;
- energy follows Jev by at most ±0.5 per bar;
- bass and keys only come in at the start of a 4-bar group.

With the same real jam: from ~18 drum changes in 28 bars to 3 role changes.

## 8. Known limitations of the PoC and next steps

1. **Automatic tempo detection** confuses the beat with some strumming patterns (137 BPM in
   a jam at 100). A fixed tempo is reliable; options: tap tempo, a count-in, or combining the
   autocorrelation with accents.
2. **Downbeat without harmony** (rhythm only): use accents/low notes or a downbeat tracker.
3. **Free tempo / rubato**: gentle drift is followed (±15 %) and jumps are ignored.
4. **Hearing the band**: subtract the band's own output from the input (or use a line
   input) so it doesn't feed back when playing through speakers.
5. **More musicians and roles**: guitar, percussion, synth; answer phrases chosen by Jev
   among candidates generated in code (a Choice).
6. **Calibration**: use the recorded sessions (`bars.jsonl`, `review.csv`) to tune thresholds.
7. The rest of the musical roadmap is in [MUSICAL-METHODS.md](MUSICAL-METHODS.md).
