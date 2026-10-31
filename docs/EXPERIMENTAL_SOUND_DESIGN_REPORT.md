# Experimental sound designer

## Baseline and isolation

The approved unit designs, formation animation and sound-effects stage were committed
and pushed first as `b7b125cc57e5c2e06895031d6c8ceea71d886573`:
[GitHub baseline](https://github.com/ammar-adel222/Content-Machine/commit/b7b125cc57e5c2e06895031d6c8ceea71d886573).

The new experiment lives entirely in `experiments/sound_design/`. Production Python,
renderer, configuration and tests are unchanged from that pushed baseline. It imports
the existing provider adapters, WAV utilities and baseline synthesizer read-only.
The production pipeline does not import the experiment. Its candidates/cache/gallery
are separate under `output/sound-design/`; no asset is automatically promoted or
attached to a video. Music remains outside this experiment.

## What it does

A text model authors an original layered DSP recipe from a sound brief. It is not
restricted to the production catalog of named effects: the rowing-galley and wooden
siege-tower briefs demonstrate new compositions without new effect-specific Python.

The recipe is bounded data, not generated executable code. The interpreter offers:

- Filtered noise, sine and triangle sources.
- Tonal frequency sweeps; noise frequency bands use highpass/lowpass controls.
- Attack/release envelopes and exponential decay.
- Repeated hits, bounded timing jitter, tremolo and restrained stereo positioning.

Recipes have at most 12 layers, last 0.25–12 seconds, and are limited to 80 aggregate
voice-seconds of work. The renderer outputs deterministic 48kHz stereo PCM, with
high-pass DC suppression, 5ms boundary fades and sample-peak headroom. Briefs, seeds
and recipe edits control repeatable variants. Filters are simple one-pole sections;
this is a small sound-design language, not a physical acoustic simulator.

## Agent and repair flow

1. Read and validate a saved `Brief`.
2. Ask the selected model for a `Recipe` JSON instance.
3. Validate bounds, envelope/filter relationships and synthesis workload.
4. Render locally and measure finite samples, energy, peak headroom, DC and edges.
5. Feed structured/technical failures back for one repair, within the attempt budget.
6. Save the candidate and report as `technical_pass_listening_pending` or `needs_revision`.

The default budget is two model attempts. The existing HTTP transport may make its
own single bounded retry. Missing keys or provider failures do not fabricate audio.
No second model is claimed to have listened: the provider interface used here authors
JSON, not an acoustic quality assessment. A technical pass is not proof of identity,
realism, historical authenticity or superiority over existing sound effects.

Successful candidates may be cached separately as explicitly **unapproved** recipes.
Cache identity and recipe hashes are checked. Edited recipes render offline. Cached
recipes are rerendered through the current interpreter, not treated as approved media.

## Live tests

Four model-authored recipes were generated and rendered:

| Brief | Successful author | Duration | Layers | Attempts in successful run |
|---|---|---:|---:|---:|
| Armored tracks over rough ground | Qwen through Groq | 6s | 4 | 2 |
| Wooden siege tower | Qwen through Groq | 6s | 4 | 1 |
| Rowing galley | Qwen through Groq | 6s | 3 | 1 |
| Single illustrative matchlock shot | Gemini 3.5 Flash-Lite | 2s | 4 | 1 |

The musket test first encountered Groq HTTP 429 and Gemini 3.8 Flash HTTP 503, each
within a two-attempt run. A single explicit Lite fallback attempt succeeded. All
failure reports remain in the local run folders. These different briefs/providers
are not a controlled model ranking.

The successful recipes were rerendered locally after the final DSP checks, retaining
their actual author/call metadata. Final WAV/renderer hashes and metrics were saved.
Their measured raw sample peaks range from approximately -25dBFS to -4dBFS; none
needed master attenuation. Their raw RMS levels vary substantially, so raw loudness
must not be mistaken for quality. The galley is particularly quiet before audition
gain; the siege-tower recipe emphasizes bass. Phone listening is still needed.

Recipe inspection shows the intended components represented as layers: timber
friction/knocks, oar entry/pull/creaks, mechanical/gravel textures, and a single
click/report/body/tail sequence. This is evidence of structured composition, not
proof that the rendered sound will be recognizable to listeners.

## Listening comparison

The local gallery contains seven clips across four cases:

- Generated tracks versus the existing tracks effect.
- Generated siege tower versus the existing generic wheels effect.
- Generated galley alone; there is no corresponding production baseline.
- Generated matchlock versus the existing generic musket effect.

A/B sources are hidden until revealed, and ordering is alternated. Comparisons are
matched in full-clip RMS with peak headroom preserved; this is not perceptual loudness
normalization or a statistically controlled blind study. The three sustained cases
target -24dBFS RMS; the shot pair is lower to preserve its sharper transient.

Listen for identity, texture, distracting tones/hiss, excessive repetition, harshness,
loop boundaries and phone-speaker usability. The gallery does not declare a winner
or record approval automatically. No candidate has been listening-approved.

Local files, ignored by Git:

- [Listening gallery](../output/sound-design/listening/index.html)
- [Comparison results](../output/sound-design/listening/comparison.json)
- [Tracks recipe](../output/sound-design/runs/985f16ffc16a49fe9d678e443d1c7b80/recipe.json)
- [Siege tower recipe](../output/sound-design/runs/9f99301eb71b486fa0499add09d5e5c9/recipe.json)
- [Galley recipe](../output/sound-design/runs/95e5a00857f44515b1f6e66009ce7ec7/recipe.json)
- [Matchlock recipe](../output/sound-design/runs/cd2ff95f981e4a18a11b73bdcdaf023a/recipe.json)

## Usage and verification

```powershell
python -m experiments.sound_design experiments/sound_design/briefs/wooden_siege_tower.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
python -m experiments.sound_design BRIEF.json --recipe EDITED-RECIPE.json
python -m experiments.sound_design.compare RUN-ONE RUN-TWO --output output/sound-design/NEW-GALLERY
python -m experiments.sound_design.serve --root output/sound-design/NEW-GALLERY --port 64922
python -m unittest discover -s experiments/sound_design/tests -v
```

The experiment has **14 offline tests** covering schema/work limits, all sources,
repetition/pan, silence, determinism, peak limits, repair/budgets, failures, candidate
cache integrity, offline CLI rendering, matched comparisons and HTTP range behavior.
The production **243 Python tests and 20 renderer/browser tests** also pass.
The actual gallery was checked in a real browser: four cases, seven decodable clips,
play/pause, seeking and byte-range responses work. Production-file diff against the
pushed baseline is empty.

## Limits and next decision

There is no audio-conditioned reviewer, neural waveform generator, sample retrieval,
convolution reverb, physical material simulation or automatic historical validation.
Loop edges use short fades, so continuous loops can still have a perceptible dip.
The language cannot reproduce every natural sound convincingly. Broader listening
tests and more varied briefs are needed before adopting it in production.

After listening, useful recipes can be refined or compared with recordings. Existing
production categories can already accept approved WAV replacements through their
sample configuration. New categories such as oars would need an explicit integration
decision; this experiment has made no such production change.
