# brag-plan — JEVjam

**What:** An AI band (drums, bass, keys) that listens to your guitar and jams along live over MIDI. Jev judges and deterministic code plays the notes.
**For:** Musicians who practise alone and want a band that follows them.
**Sets it apart:** It listens and follows you instead of generating a song. Jev decides the *next* bar, so the network never touches the audio.
**Funniest true claim:** in reactive mode, bass and keys come in on beat 2, "like a musician who doesn't know the changes". Also: "Use headphones. If the mic hears the band, the band ends up listening to itself."
**Visual hook:** a line of text types itself with a typo ("jma"), fixes it, then falls off the screen.
**Real UI:** the app's big red button, the "OIGO → LA BANDA TOCA" stage (rebuilt with the app's real CSS tokens) and the real app in `index.html?preview`.
**Tone:** freeform "cool but clumsy". This maps to `default` pacing, with a hand-drawn marker (Caveat), slightly crooked stickers and things that land a bit wrong and then fix themselves.
**Share caption:** "Nobody wanted to jam with me, so I built a band that has to."

## Soundtrack
The soundtrack is JEVjam playing itself. A synthetic guitar (`sources.render_human`) strums Am–G–F–E at 100 BPM, and the band comes from `band.py` + `synth.py`, the real generators and the real FM synth. One bar is 2.4 s.
The band enters clumsily on beat 2 of bar 2, the reactive-mode joke. It plays light for bars 3–4 with a fill, grooves in bars 5–8 with a fill, and ends on a crash with a pad on bar 9. The effects (button click, typing ticks) are soft and in A.

## Storyboard (22.4 s)
| # | Time | Music | On screen |
|---|---|---|---|
| 1 Hook | 0.0–2.8 | guitar alone, Am | "Nobody wants to jma" ⌫ "jam with you." + a small handwritten "(again)". Crooked, then it drops off the screen. |
| 2 Button | 2.8–5.6 | the band stumbles in on beat 2 (3.0 s) | The app's red button bounces in and the cursor clicks it. "So we built a band that has to." Marker note: "comes in on beat 2. on purpose. mostly." |
| 3 Reveal | 5.6–9.6 | light band, fill | The JEVjam logo, where "jam" lands late and bounces. "An AI band that listens to what you play — and jams along." |
| 4 Judges | 9.6–14.4 | groove starts | Left: live stage card (OIGO → LA BANDA TOCA, the plan, a VU meter). Right: "Jev doesn't write notes. It judges." Question chips land on the beat: more energy? / a fill? / leave space? One chip lands crooked and gets nudged. |
| 5 The band | 14.4–19.2 | groove, fill | The real app slides up. "Drums, bass, keys. They change roles together." A marker circle wobbles around the musician cards. |
| 6 Outro | 19.2–22.4 | crash + ring | "JEVjam" / "Jam with an AI band." / github.com/sanlega/JEVjam, plus a sticker: "use headphones, or the band jams with itself". |
