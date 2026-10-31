# Sound-effects stage

## Purpose

Add synchronized Foley to the approved unit animation while keeping sound design
independent of research, writing, visual assets, animation and future music. The
first example adds tracks/engine layers to tanks and heavy footsteps to elephants.
It uses the existing 24-second vertical animation without rerendering its picture.

## Architecture and timing

`sound_models.py` defines editable configuration and a saved cue plan.
`sound_plan.py` compiles cues from the saved animation timeline. `sound_render.py`
generates or loads effects and mixes them. `sound_effects.py` packages an independent
preview bundle, reports and WAV stems, and optionally attaches the mix to a video.
No new dependencies or API keys are required. FFmpeg/FFprobe are used for MP4 output.

Movement cues follow the same stagger formula as animation: departure delay is
capped at 1.2 seconds and every layer stops within its authored action. Up to three
subgroup layers suggest a symbolic formation. They use stable phases, controlled
combined gain, smooth start/stop envelopes and restrained equal-power stereo panning.
The mix is suitable for mono playback as well. These are illustrative group sounds,
not one sound per literal historical soldier.

Infantry and cavalry can default to footsteps and hoofbeats. Other identities need
an explicit profile: unknown moving units return `needs_profiles` with their IDs.
Choose a supported sound or explicit `none`; there is no automatic vehicle guess.
The example configuration selects tracks and heavy steps for its known generated
designs. New visual unit types can reuse these sound categories or supplied WAVs.
Static campaign area callouts and terrain-only studies omit movement sounds; the
plan/report records those omitted actions rather than sounding unanimated routes.

Gunfire is not inferred from narration nouns or movement. A weapon/impact sound
requires an explicit spot time inside an authored `engage` action. Supported spot
types are cannon, musket, rifle and clash. A shot time must also match a visual
firing event before production use; this stage validates the engagement window,
not a skeletal weapon animation. The current demonstration has no weapon sounds.

## Original sounds and replacements

Default material is original deterministic synthesis, not downloaded recordings:

- Footsteps: short thud and filtered gravel/noise layers.
- Heavy steps: lower, longer thuds with surface texture.
- Hooves: staggered clop patterns.
- Tracks: engine harmonics, rumble, mechanical chatter and clanks.
- Wheels: subdued rolling texture and periodic creak/rattle.
- Explicit weapon/impact cues: bounded transients, body and decaying tails.

These sounds establish timing and a consistent stylized treatment. They are not
verified recordings of a particular historical weapon, vehicle or surface.

`samples` in the config can replace any effect with a local 16-bit PCM WAV. Movement
replacements should be loop-ready; spot replacements should be one-shots. Mono or
stereo at 8–96kHz is accepted, converted to the mix rate and centered before panning.
Movement recordings control their own internal cadence. A source attribution string
and file hash are recorded in the report. No remote audio is fetched.

## Voice-priority mixing

An optional narration WAV is mixed at its supplied level. A 20ms RMS detector
reduces effects by up to 12dB during speech, with 20ms attack and 220ms release.
This simple detector expects an isolated narration stem. It is not a speech model
or a loudness-normalization service. The final mix scales down only when necessary
to retain at least 1dB sample-peak headroom; it does not boost quiet effects.

Narration that exceeds video duration is rejected rather than truncated. The original
narration stem is preserved byte-for-byte. Rebuilding effects on a narrated bundle
reuses that stem; a missing stem requires the narration file again. This prevents
editing sound effects from silently removing narration. TTS generation is separate.

## Inputs, outputs and usage

```powershell
python -m war_content.sound_effects output/content/ANIMATION-BUNDLE --profiles examples/sound/unit_animation.json --video output/units/unit-animation.mp4
python -m war_content.sound_effects output/content/BUILD --profiles sounds.json --narration narration.wav
python -m war_content.play output/content/SOUND-BUNDLE
node renderer/export.mjs output/content/SOUND-BUNDLE final.mp4 24 24 portrait
```

After package installation, `war-sound` is an equivalent entry point. Output is a
new bundle under `output/content/` containing:

- `sound-config.json`: editable profile/recording/spot selections.
- `sound-plan.json`: validated cues and fingerprint of the source scene.
- `sound-effects.wav`: effects-only stem.
- `soundtrack.wav`: final 48kHz stereo 16-bit PCM mix.
- `narration.wav`: original narration, when supplied.
- `sound-metrics.json` and `sound-report.md`: levels, speech activity and sources.
- A portable map preview with soundtrack metadata and hash in `scene.json`.
- `preview-with-sound.mp4` when a matching silent MP4 is supplied.

The source bundle remains intact. Only runtime and designated media are copied;
unrelated files such as `.env` are excluded. The source publishing/review status is
preserved. `--video` checks duration and stream-copies the video; the caller must
choose the matching cut. It does not independently establish visual identity.

## Playback and export

Play starts audio through a user gesture. Pause and seeking stop playback, and the
audio clock drives the visual timeline while playing. Mute/Unmute controls remain
outside the exported video. Deterministic `renderAt()` inspection is silent.

The local preview server supports byte-range audio responses for reliable seeking.
Missing audio shows a readable message while leaving the map inspectable. Silent
bundles retain their existing controls. Normal MP4 export verifies the WAV hash and
automatically encodes AAC audio, including shortened preview cuts.

## Verification

**243 Python tests and 20 JavaScript/browser tests pass.** New coverage includes
staggered cue timing, unknown profiles, explicit silence, fade bounds, stationary
routes, explicit weapon windows, invalid inputs, deterministic synthesis for all
nine effects, silent start/stop regions, WAV conversion/replacement, voice ducking,
headroom, narration-stem preservation, packaging, CLI and mux failures.

Real browser tests cover audio-clock synchronization, pause, asynchronous seeking,
mute, frame inspection and missing WAV handling. HTTP tests cover valid, suffix,
open-ended and rejected byte ranges. Existing map/animation tests remain passing.

The 24-second example is H.264 1080×1920 with 48kHz stereo AAC. The unboosted mix
has a -14.34dBFS sample peak and -28.54dBFS full-program RMS, including quiet halts.
It has no narration or music. A separate two-second normal-export smoke test also
contains AAC audio. Voice ducking is verified with offline synthetic narration;
actual narration performance still needs review when TTS audio is connected.

Local example files, ignored by Git:

- [Sound-enabled vertical video](../output/content/aedddbd18d554be1b86888a456c774c1/preview-with-sound.mp4)
- [Effects stem](../output/content/aedddbd18d554be1b86888a456c774c1/sound-effects.wav)
- [Build report](../output/content/aedddbd18d554be1b86888a456c774c1/sound-report.md)

The audible character of these synthesized effects is ready for listening review;
recorded Foley can replace it independently. Music remains a separate next step.
