# Experimental text-to-sound recipes

Opt-in experiment. The production sound pipeline never imports this package.
All output goes under `output/sound-design/`, not the production asset library.

```powershell
python -m experiments.sound_design experiments/sound_design/briefs/wooden_siege_tower.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
python -m experiments.sound_design BRIEF.json --recipe EDITED-RECIPE.json
python -m experiments.sound_design BRIEF.json --reuse
python -m experiments.sound_design.compare RUN-ONE RUN-TWO --output output/sound-design/NEW-LISTENING-FOLDER
python -m experiments.sound_design.serve --root output/sound-design/NEW-LISTENING-FOLDER --port 64922
python -m unittest discover -s experiments/sound_design/tests -v
```

`--provider groq|gemini` and `--model` select the existing provider adapters. The
default is the configured project's Qwen model through Groq, with two model attempts.
There is no automatic provider fallback. `--recipe` is offline; `--reuse` reads a
separate unapproved candidate cache. A technical pass never grants listening approval.

Each run saves the brief, model/call metadata, validated recipe, candidate WAV,
technical metrics and report. The DSP interpreter supports filtered noise/tones,
frequency sweeps for tones, envelopes, repeated hits, jitter, tremolo and stereo pan.
The schema caps duration, layers and synthesis workload. It accepts no executable code.

The comparison page matches RMS while retaining peak headroom and transient shape.
It is not perceptual loudness normalization. A/B source labels are revealed on demand.
Listen for recognizability, unwanted tones/hiss, repeated patterns, harshness and
phone-speaker usability. No candidates are automatically attached to videos.

See [the detailed report](../../docs/EXPERIMENTAL_SOUND_DESIGN_REPORT.md).
