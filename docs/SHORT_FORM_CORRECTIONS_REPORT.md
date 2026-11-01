# Short-form pacing, unit icons and audio corrections

## Result and scope

This work changes the agents and renderer, then uses a live Austerlitz project as a
verification case. It is not simply another unchanged full-pipeline run.

The corrected narration is **76.36 seconds**, versus the original 114.04-second audio
plan. The video is vertical 1080 x 1920 at 30 fps. The previous video and immutable
project artifacts remain available. The equipment-icon export is complete and verified. Its exact results are below.

## Opening and delivery

The new opening is:

> The Allies attacked Napoleon's right. He struck their weakened center.

The battle name and year follow the tactical problem. The revised script has 234
words, brisk phrase directions and 120 ms planned pauses: 1.2 seconds of explicit
assembly pauses across ten phrases. Actual duration implies approximately 184 words
per minute including those pauses. No global video speed-up or pitch shift is used.

The writer's previous date guard only recognized dates immediately following 'On'
or 'In', so 'On a cold Monday morning' escaped it. Validation now rejects that form,
opening sentences longer than 16 words, and pauses above 500 ms. The prompt requests
a 6-12 word opening and forward-moving delivery; the independent reviewer checks the
opening rather than trusting its role='hook' label.

The generated rewrite still reintroduced a northern subplot and stronger intent and
treaty wording. The delivered script received an explicit source-grounded editorial
correction and then passed the real independent review. This is a supervised result,
not proof that an autonomous writer always produces the desired story.

## Army identity and attention cues

France stays blue and the Allies stay red. The earlier colors did not actually swap;
missing identification and attention rings made their roles unclear. Faction identity
now comes from a stable roster rather than force-array position, and a persistent
France/Allies legend appears in the video. Focus uses a small gold chevron rather
than a circle that could look like encirclement. Neither highlighting nor winning
changes a unit's faction color.

## Equipment icon policy

The user rejected the intermediate human figure, which resembled a person lying down.
The accepted direction is now:

- Older-era infantry: an upright sword icon.
- Modern infantry: an upright helmet icon, with a generic gun icon as an option.
- Tanks, artillery, cavalry and new specialist units keep their descriptive identity
  rather than becoming the same generic infantry symbol.

Austerlitz uses the sword **as an era convention**, not a claim that its infantry were
all equipped with swords. Native editable presets are saved under
`examples/units/infantry.json`, `modern_infantry.json` and `modern_rifle.json`.
Each contains a brief, an exact bounded vector design, and its presentation mode.
The sword received an actual rendered-image model review. The helmet and gun are
editable available presets, not live-tested depictions of particular modern armies.

`Binding.presentation` is independently stored as 'upright' or 'heading'. Portable
bundles carry per-force `unit_presentations`; upright icons do not rotate or roll
when their formations move. Vehicle silhouettes can retain heading-based rotation.
Movement positions, subgroup timing and faction colors are separate from icon
orientation. Existing bindings default to heading for compatibility. Unit planning
now receives researched date claims and is instructed to use the era icon vocabulary.

`ContentAgent.review_design()` accepts an exact edited vector, reviews its real render
and only then publishes it to the shared library. It preserves the previous library
entry if review fails. Model-designed unfamiliar assets still use the original
bounded design/render/review path; this revision does not pretend that the final
hand-refined preset was generated autonomously by a model.

## Fixed captions

The jumping white banner is removed. Short outlined word groups appear in one fixed
band at 72% of the frame height, with room left for bottom platform UI and the right
interaction rail. Caption position no longer follows individual moving units or
changes between scenes. This is a practical safe-zone target, not a guarantee for
every platform UI or screen crop.

Map framing, rather than caption position, is adjusted when a unit falls under that
band. The third shot was reframed after the sword-version review caught a collision.
Actual browser tests verify fixed caption placement and upright icons during motion.
Word-group timing remains approximate within measured phrase intervals, not forced
word alignment.

## Music and sound design

The earlier music was mixed to roughly **-56.55 dBFS RMS**. The revised original
96 BPM percussion-and-harmony bed measures **-41.26 dBFS RMS**, about 15.3 dB higher,
with narration ducking and a 16 dB voice-margin target. Its 150 ms fade-in brings the
bed in promptly. Final mix peak is approximately **-1.10 dBFS**.

Movement Foley uses stronger editable force profiles. Its dry effects stem measures
-15.51 dBFS peak and -40.46 dBFS RMS, before the editable +4 dB effects gain and
speech ducking. The opening also includes sparse, irregular illustrative close-fighting
texture linked to the existing Telnitz combat claim. It uses the original clash
synthesis; it is not a historical recording, and it does not invent precise musket
or cannon firing events. Explicit weapon spots still require engagement cues.

Audio controls remain separate: source arrangement, music/effects gains, fades,
ducking and force profiles can be edited without rerendering the map. Music cache
identity distinguishes the original ambient bed from the new pulse arrangement.

## Efficient editing and quota recovery

The primary Gemini TTS endpoint exhausted its daily free allowance. The existing
Gemini Lite TTS option completed the ten clips across short rate-limit waits, reusing
finished clips each time. Groq/Qwen and stronger Gemini also returned visual quota
errors; this live correction used a per-run Gemini Flash Lite visual fallback.
Repository default provider choices were not silently changed.

Two queued-edit bugs were corrected and regression-tested:

1. A later narration edit could discard an earlier pending delivery change. The
   narration adapter now compares current settings with the last applied settings
   snapshot, preserving accumulated scoped delivery notes.
2. A queued narration edit could make a valid pending script edit regenerate its
   geographic plan. Valid choreography can now be rebound unless a route edit or
   review repair explicitly requires direction work.

Optional TTS edge-silence trimming was implemented and tested. The 76.36-second
completed narration was synthesized before the queued-settings correction and has
trim_silence=false; its faster pace comes from the rewritten script and delivery,
not from a claim that trimming was applied to this output.

The final sword change is a unit-only revision. It rebuilds unit binding/review,
picture and final mux; it reuses research, script, narration, timing, terrain,
effects, music and mixing. No TTS calls are allowed in that revision.

## Verification and limits

Offline tests cover writer error paths, exact-vector review/rejection, source-linked
sound bounds, deterministic music, cache separation, queued edits, portable icon
presentation and browser rendering. Final counts and MP4 checks are appended below.

The project remains awaiting exact-version human review. Nothing is approved or
published automatically. Sampled image reviews and technical audio metrics are useful
checks, but they do not establish audience retention, historical truth or subjective
sound quality. The live fallback behavior and manual corrections above remain part
of the result rather than being hidden behind passing stage labels.


## Final verified artifacts

- [Corrected full video](../output/austerlitz-shortform/final.mp4)
- [Opening 15 seconds](../output/austerlitz-shortform/opening-15s.mp4)
- [Sword inspection sheet](../output/austerlitz-shortform/sword-design.png)
- [Helmet inspection sheet](../output/austerlitz-shortform/helmet-design.png)
- [Optional gun inspection sheet](../output/austerlitz-shortform/gun-design.png)
- [Verification audit](../output/austerlitz-shortform/verification.json)

The final video is **76.366667 seconds**, H.264 **1080 x 1920 at 30 fps**, with
48 kHz stereo AAC. File size is 7,671,856 bytes. A complete FFmpeg decode passed
without reported errors. Final-video frames at 1, 3, 20, 35, 45, 60 and 72 seconds
were extracted; opening, third-shot framing and central assault frames were inspected.

**379 offline Python tests and 24 renderer/browser tests passed.** The browser checks
include actual WebGL motion with icon and body rotation held at zero for upright
presentation. Unit tests also verify that presentation survives bundle saving and
that contradictory upright briefs fail validation.

The final unit-only revision retained the exact artifact IDs for research, writing,
direction, narration, timing, terrain, effects, music source and mixing. Its camera
follow-up reused four passing scene-image reviews and reviewed the changed third
shot. It made zero TTS or search requests. The final picture render took 494.5 seconds
on the local software renderer while tests were also running; final mux took 4.3 seconds.

The entire correction/debugging sequence used 48 logical model attempts, zero new
search requests and 16 TTS attempts, including failed and rate-limited attempts.
Transport retries can add HTTP requests. These totals include rejected figure
experiments and fallback checks; they are not the cost of a normal unit-only edit.

Saved revision: `87c2fd5118944c6d9b0aa105735000ac`. All 17 stages have artifacts;
there are no dirty stages or blocking issues. Status is **awaiting_review**, with
no human approval and no publishing. The earlier full-pipeline report remains a
record of the original video, not the current corrected preview.
