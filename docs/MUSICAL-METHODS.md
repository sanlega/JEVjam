# Musical methods for JEVjam

Research from 2026-09-30: which techniques from musical practice, rhythm psychology and
computer music (MIR, improvisation systems) could improve the band, and where they fit in
the current architecture. Ordered by expected impact on the problems seen in real jams.

Fit criterion: JEVjam is **code that listens and generates + Jev judging between bounded
options**. A method fits if it (a) improves the listening, (b) improves the deterministic
generation, or (c) gives Jev better questions or options. End-to-end audio generation
models don't fit the MIDI-first design (see §9).

---

## 1. Anticipating the next chord with functional harmony (+ Jev)

**Current problem:** until it has heard the progression twice (≈ 8 bars), the band is one
bar late ("follow the last chord heard"). It's the biggest audible flaw left.

**Method:** tonal harmony isn't random. Harmonic functions (tonic → subdominant → dominant →
tonic) and pop/rock corpus statistics give transition probabilities between scale degrees.
For example, V → I and IV → V are very common, and in minor iv → V → i.
[ReaLJam](https://arxiv.org/abs/2502.21267) (Google, CHI 2025) solves the same problem with
**anticipation**: the agent predicts and plans the chords before they sound, and shows its
plan to the musician. Its model, ReaLchords, was trained on about 30,000 annotated pop song
snippets from Hooktheory.

**In JEVjam:**
- A prior in code: a transition table between diatonic degrees (in `theory.py`, written by
  hand from common practice; it could be refined with corpora such as de Clercq & Temperley
  or McGill Billboard).
- Jev as a **Choice** between the diatonic chords: "Given `progression`, which chord is the
  human most likely to play now?". A musical common-sense judgment; Jev knows typical
  progressions described in text (e.g. "I‑V‑vi‑IV").
- Fusion in code: prior × Jev; if the confidence is above a threshold, play the prediction;
  otherwise, the current mode.
- ReaLJam bonus: **show in the app the chord the band plans to play** ("the band plays" is
  already there; add "next").

**Measure:** band chord accuracy in bars 0‑8 (today ≈ 0 %, because it waits or is late).

## 2. Tempo following with phase and period correction

**Current problem:** `_follow` corrects the phase ad hoc (30 % of the error, ±30 ms) and the
tempo with fixed smoothing.

**Method:** in rhythm psychology, synchronisation between musicians is modelled with
**linear phase correction** (and period correction): each one corrects a fraction α of the
asynchrony measured on the previous beat. [Wing, Endo, Bradbury and Vorberg
(2014)](https://royalsocietypublishing.org/doi/10.1098/rsif.2013.1125) measured it in string
quartets and derive the optimal α that minimises the variance of the asynchrony.
[B‑Keeper](https://zenodo.org/record/1177231) (Robertson and Plumbley) applies the idea to a
sequencer that follows a live drummer (Ableton), with a ±5 % tempo margin.

**In JEVjam:**
- Measure the asynchrony on **every beat**: the human's nearest onset vs. our beat. Apply
  phase correction α ≈ 0.25‑0.5 and period correction β ≈ 0.1, with limits, like B‑Keeper.
- Give more weight to low or accented onsets (kick/bass in B‑Keeper; on guitar, the beat-1
  strum).
- Log the asynchrony in `bars.jsonl` and show it in the review (ms, mean and deviation).

**Measure:** mean asynchrony and its deviation between the human's attacks and the band's.

## 3. Call and response in the human's gaps

**Current problem:** `answer_phrase` answers in the second half of the bar, whatever the
human is playing.

**Method:** in group improvisation (trading fours/eights, call and response) you answer
**in the other player's silences**, and the accompanist steps back when the soloist is dense.
Continuator (Pachet, 2003) and [Somax2](https://github.com/DYCI2/Somax2) (IRCAM) listen
continuously and respond based on what they hear.

**In JEVjam:**
- Listening: detect **gaps** (beats below the threshold after one of the human's phrases)
  and **density per beat**. Per-beat windows already exist, so it's little work.
- Context for Jev: "the human just left a gap at the end of the phrase" /
  "the human is playing a dense line".
- Generation: the answer phrase is played **in the gap** (not in a fixed place) and in a
  **different register** from the human's.

**Measure:** % of answer notes that land in the human's gaps vs. on top of them.

## 4. More robust harmony: approximate transcription + temporal smoothing

**Current problem:** some bars come out "no chord", or with spurious chords when the chord
changes within the bar.

**Methods:**
- **NNLS chroma** ([Mauch and Dixon, ISMIR 2010](https://code.soundsoftware.ac.uk/projects/nnls-chroma/)):
  an approximate transcription before the chroma (non-negative least squares with a
  dictionary of notes with harmonics). It especially improves "difficult chords"; it is the
  rigorous version of the fix we made for the guitar E.
- **Chord HMM / Viterbi** with key-dependent transitions (Chordino, Sheh and Ellis): instead
  of deciding every bar on its own, look for the most likely sequence. In real time: forward
  filtering with a fixed lag of 1‑2 beats.
- Detect **chord changes within a bar** (two chords per bar) instead of forcing one per bar.

**Measure:** % of bars with a clear chord and accuracy against an annotated ground truth of
2‑3 real jams.

## 5. Hypermeter and the arc of the arrangement

**Current problem:** 4-bar phrases already organise the changes, but the jam has no "form"
(intro, build-up, chorus, ending).

**Method:** the *Generative Theory of Tonal Music* (Lerdahl and Jackendoff, 1983) describes
**hypermetrical structure**: bars group into 2 → 4 → 8 → 16, and important changes fall on
the larger boundaries. Production practice adds **layering**: instruments come in one by one
to build intensity, layers are removed before a big moment (*break*), and there are fills or
*pickups* before the boundaries.

**In JEVjam (on top of `phrasing.py`):**
- Hierarchy: phrase (4) → section (8/16). Big changes only on section boundaries, small ones
  (one musician) on phrase boundaries.
- **Staggered entry** at the start: drums → bass → keys, phrase by phrase, like a band
  joining in.
- Jev: a Score of "where in the arc the jam is" (intro / building / peak / coming down /
  ending) from relative loudness and density and the elapsed time; code turns it into layers.
- **Ending**: if the human is winding down (downward trend + end of phrase), the band ends
  with a tonic chord on beat 1 instead of fading out.

**Measure:** listening (A/B with and without the arc) and number of "moments" per jam.

## 6. Groove: the human's accents, syncopation and swing

**Current problem:** the drums choose a pattern by energy but don't copy the human's rhythm
(accents on 2 and 4, syncopation, swing or straight eighths).

**Methods:**
- Accent profile per subdivision (which eighths or sixteenths carry strong attacks):
  syncopation index, *half‑time* detection.
- **Swing ratio**: the duration ratio between the first and second eighth note (1:1
  straight, ~2:1 swing).
- **Microtiming** per role, as in real practice: the bass slightly ahead of or on the beat,
  the hi-hat swung and the snare a little behind when *laid back*. It replaces the current
  random ±jitter.

**In JEVjam:** per-beat analysis (onsets already exist) → descriptors in words for Jev
("straight eighths", "swung", "accents on 2 and 4", "syncopated") → Jev chooses the feel and
code applies swing/microtiming in `band.py`.

**Measure:** swing and accent match between human and band (can be analysed in `mix.wav`).

## 7. Voicing practice and register allocation

**Current problem:** the keys play close triads in 55‑74 and can step on the human's
register and double the bass.

**Methods (accompaniment pedagogy):**
- **Rootless voicings** when there is a bass (the bass plays the root) and **guide tones**
  (3rd and 7th) when comping; tensions (9th) in styles that call for them.
- **Register allocation**: the keys avoid the range the human plays in (estimated from the
  chroma per octave or the lowest onset), just as a pianist makes room for the singer.
- Voice leading is already implemented (minimum movement): keep it.

**Measure:** listening, and register overlap between human and band.

## 8. Learning the player's own style

**Methods:** Continuator (Pachet, 2003; variable-order Markov models of what the musician
plays), OMax / [Somax2](https://github.com/DYCI2/Somax2) (IRCAM: Factor Oracle and corpus
memory, agents that listen and recombine in real time), ImproteK/DYCI2 (improvisation guided
by a "scenario", e.g. a chord chart, which is exactly our predicted progression).

**In JEVjam:** in the medium term, the keys' answer phrases are built from the human's own
motifs (transcribed with monophonic pitch) and transposed to the current harmony. Jev
chooses between candidates ("which of these 5 phrases best answers what they just played?"),
which is TypeSafe's "select instead of generate" pattern.

## 9. What doesn't fit (for now)

- **Real-time audio generation models** such as [Magenta RealTime](https://github.com/magenta/magenta-realtime)
  (Google DeepMind, open weights, 2 s audio chunks steered by text or audio): impressive,
  but they generate audio rather than MIDI, don't follow chord by chord, and their block
  latency clashes with the goal of another musician who responds. They could inspire a
  "texture/ambient" mode.
- **Trained accompaniment models** (ReaLchords): the quality reference for point 1, but they
  require training our own; start with a prior + Jev and measure.

---

## Status (2026-09-30): 1, 2 and 3 implemented

| # | What was done | Result on real jams |
|---|---|---|
| 1 | `theory.anticipate_chord`: a library of common progressions as scale degrees in all rotations, with wildcards for bars without a chord, harmonic rhythm, and functional harmony as a tie-breaker; `anticipated` mode and a 4-chord **plan** in the app. **Jev is not used here**: when measured, it got the next chord right 3/10 times (it tends to pick the first option or the tonic; this is sequential reasoning, outside its strengths) | F‑E‑Am‑G: 10/10 chords from the moment the band comes in (before: 4 misses in bars 4‑7); C‑G‑F‑G: 11/11 |
| 2 | `sync.BeatSync`: phase (α 0.4) and period (β 0.1) correction per bar with the median asynchrony; the tempo is only corrected if ≥ 3/4 beats match; output latency compensated; a constant offset is learned as latency | with `--bpm`: +10 ms mean and 28‑31 ms spread (the range of human musicians); A/B on an irregular jam: from −42 ms to −17 ms |
| 3 | `dialogue.GapProfile`: gaps from level drops (≥ 15 dB, or ≥ 8 dB with no attacks), a per-beat pattern over 4 bars, the human's register; the keys' answer goes into those beats and a different register; phrasing in words for Jev | Jev chose to answer at the start of a phrase and 80 % of the answers landed in the human's gaps |

Open issue found: **automatic tempo detection** confuses the beat with strumming patterns
(137 BPM in a jam at 100). Everything works with `--bpm`; possible fixes: tap tempo or a
count-in, or combining the autocorrelation with accents.

## Recommended priority

| # | Method | Fixes | Effort | Jev |
|---|---|---|---|---|
| 1 | Anticipate chords (functional harmony + Jev) | one bar of lag at the start and with new progressions | medium | Choice of the next chord |
| 2 | Phase/period correction | fine timing with the human | low‑medium | — |
| 3 | Call and response in gaps | "a musician who listens" instead of a fixed pattern | low | new context + Noul |
| 5 | Hypermeter, layers and ending | give the jam a form | medium | Score of the arc |
| 6 | Groove (accents/swing) | drums that "feel" like the human | medium | Choice of feel |
| 4 | NNLS + chord HMM | harmonic robustness | medium‑high | — |
| 7 | Voicings and register | a more professional sound | low | — |
| 8 | The player's style | answers in their own language | high | choosing between candidates |

General references: R. Rowe, *Machine Musicianship* (MIT Press, 2001), the listening/playing
design JEVjam follows; F. Lerdahl and R. Jackendoff, *A Generative Theory of Tonal Music*
(MIT Press, 1983).
