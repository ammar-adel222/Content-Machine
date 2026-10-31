# War Content Machine — edition two

The independent research agent discovers or accepts a war/battle, retrieves evidence,
and saves structured research. The writing agent turns a ready dossier into narration,
performance directions, and a TTS handoff. Default video target: **105 seconds**
(90–120 seconds normally, 60–150 seconds allowed).

See [the research agent build report](docs/RESEARCH_AGENT_REPORT.md) for the design,
contracts, tests, limitations, and live verification results.
Also see [the writer build report](docs/WRITING_AGENT_REPORT.md) and
[the model comparison](docs/MODEL_COMPARISON.md).
The [director](docs/DIRECTOR_AGENT_REPORT.md) and [reviewer](docs/REVIEWER_AGENT_REPORT.md)
are now independently runnable. [LangGraph is the planned coordinator](docs/PIPELINE_ARCHITECTURE.md).

## Requirements

Python 3.11+ and Pydantic 2.8+. The only runtime package dependency is Pydantic:

```powershell
python -m pip install -e .
```

In this workspace the bundled Python already has Pydantic installed, so the commands
below can run without installing anything:

```powershell
$researchPython = 'C:\Users\dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
```

Use `python` instead of `& $researchPython` if your own Python is on PATH.

## Run research

Run commands from this project's root. Keep using your existing credentials file;
there is no need to copy it. Only Tavily and the selected model providers are used.

```powershell
# Specific battle (the topic is preserved).
& $researchPython -m war_research --topic 'Battle of Austerlitz' --scope battle --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# A complete war is also a valid video subject.
& $researchPython -m war_research --topic 'Falklands War' --scope war --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Discover a topic within a theme; or omit --direction for automatic discovery.
& $researchPython -m war_research --direction 'Ancient battles where terrain changed the outcome' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Save topic selection without starting detailed research.
& $researchPython -m war_research --direction 'Modern naval campaigns' --discover-only --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Resume a saved discovery; substitute the actual path printed by the previous run.
& $researchPython -m war_research --selection-file 'output/research/THE-RUN/discovery.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Default research model: `gemini-3.8-flash`, automatically falling back to
`gemini-3.5-flash-lite` within the same attempt budget. Use `--provider groq` to select Groq,
`--model MODEL_ID` to override a model, or `--fallback groq` to opt into fallback.
`GEMINI_MODEL` and `GROQ_MODEL` can also set defaults. Existing process environment
variables take precedence over the file. Credentials are never saved in dossiers.

Optional controls: `--target-seconds 120`, `--scope war`, `--as-of 2026-10-30`,
`--exclude 'Previously covered topic'`, `--max-searches 10`, `--max-extract-urls 5`,
`--max-model-calls 5`, `--no-cache`. Resume uses the saved request; explicit budget
flags override its budgets. Start a new discovery to change scope, cutoff, or duration.

Each run gets a new folder. Discovery produces `discovery.json`; completed research
produces `dossier.json` and `report.md`. An incomplete report is still saved and
explicitly lists evidence gaps. Exit codes: **0** ready/discovery saved, **2** incomplete,
**1** configuration/provider/research failure.

## Write or revise a script

The writer defaults to Gemini's free API using `gemini-3.8-flash` with automatic
`gemini-3.5-flash-lite` fallback and the existing
`GEMINI_API_KEY`. Configure the text model with `GEMINI_MODEL` or `--model`. OpenRouter
and Groq remain optional adapters for later comparisons; their use is explicit via
`--provider`. OpenRouter requests are capped at zero-priced routes. No Tavily key is
needed to write from saved research.

```powershell
& $researchPython -m war_writer 'output/research/THE-RUN/dossier.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

& $researchPython -m war_writer 'output/research/THE-RUN/dossier.json' --previous 'output/writing/THE-VERSION/script.json' --scene s2 --notes 'Calmer delivery, with a pause before the reversal.' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Substitute real saved paths. Each version contains `script.json`, `script.md` and
`tts_plan.json`. A targeted edit preserves other scenes and global metadata. Actual
speech generation is a future component; pause timings are targets, not measured audio.
Writer exits: **0** ready, **2** needs revision, **1** input/provider failure.

The research CLI also accepts `--provider openrouter`. Its default remains Gemini.

## Direct and review the battlefield plan

```powershell
& $researchPython -m war_director 'output/research/THE-RUN/dossier.json' 'output/writing/THE-VERSION/script.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

& $researchPython -m war_reviewer 'output/research/THE-RUN/dossier.json' 'output/writing/THE-VERSION/script.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

The director produces `storyboard.json`, `storyboard.md`, `render_plan.json` and a quality
review when available. A targeted `--previous PLAN --scene s3 --notes '...'` edit preserves
the world and other scenes, but rechecks downstream continuity. `--retime --previous PLAN
--audio-timing FILE` recompiles timing without model calls. Reviewers can also inspect a
storyboard using `--plan PLAN`.

These are plan artifacts, not rendered videos. Default model remains Gemini Flash-Lite.
Director/reviewer commands retain their Gemini Flash-Lite defaults. Inputs must use
matching research/script versions.

## Create visuals and play the map

**To view an existing map, double-click `preview.cmd` in the project root**, or run
`python -m war_content.play`. It opens the latest ready generated map automatically;
keep its console open while viewing. Do not open `war_content/web/index.html` directly:
that is the player template and has no generated scene attached.

The content engine defaults to **Qwen 3.8 27B through Groq** for unit/terrain design
and image review. It reuses reviewed assets, creates missing vector designs, renders
them for visual inspection, and compiles a local PixiJS playback bundle.
Read the [engine report](docs/CONTENT_ENGINE_REPORT.md) and
[model comparison](docs/VISUAL_MODEL_BENCHMARK.md), including GPT-OSS results.

Maps fill the video canvas. Use the **9:16 / 16:9** preview selector to compare portrait
and landscape. Captions/labels overlay the map; large title/footer bands are removed.
See [the full-frame composition report](docs/FULL_FRAME_VIDEO_REPORT.md).

```powershell
pnpm --dir renderer install --frozen-lockfile
node renderer/node_modules/playwright/cli.js install chromium

& $researchPython -m war_content 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' 'output/directing/PLAN/storyboard.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

& $researchPython -m war_content.play
# Or select a particular ready build:
& $researchPython -m war_content.play output/content/THE-BUILD

# In another terminal; requires FFmpeg on PATH.
node renderer/export.mjs output/content/THE-BUILD preview.mp4 6 15
```

Custom units and terrain use validated geometry, not generated executable code.
Original director layouts are schematic; the geographic stage below adds real outlines and relief. Playback
and exports start silent; the sound-effects stage below adds Foley and optional narration. Models/quotas can leave a
build `needs_revision`; those bundles contain a report and no playable scene.

Visual overrides: `CONTENT_MODEL`, `CONTENT_REVIEW_MODEL`, `--provider`, `--model`,
`--review-provider`, `--review-model`. Research/writing retain their separate Gemini
defaults. Full cached builds with a saved manifest need no API calls.

## Design a missing unit independently

The [unit designer](docs/UNIT_DESIGN_REPORT.md) creates a unit from a brief, renders
and visually reviews it, repairs rejected designs once, and caches approved geometry.
It shares the production asset path; new types need no fixed catalog or renderer code.

```powershell
& $researchPython -m war_content.unit_cli examples/units/war_elephant.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Each run saves a result, an inspection PNG and a Markdown report under `output/units/`.
Units use recognizable silhouettes and consistent size for vertical phone screens.
Historical deployment still requires the researched director plan and manifest.

## Build a geographic map

The [geography stage](docs/GEOGRAPHY_ENGINE_REPORT.md) adds real coastlines and
elevation-derived relief. The Falklands example includes East/West Falkland and a
closer Stanley terrain view. Its schematic terrain and unlocated fleet route are
omitted rather than reused as geographic facts.

```powershell
python -m pip install -e ".[geography]"
& $researchPython -m war_content.geography output/content/ORIGINAL-READY-BUILD
& $researchPython -m war_content.play
```

For another region, supply `--geojson region.geojson --bbox WEST SOUTH EAST NORTH`.
Modern basemaps do not establish historical roads or unit deployments. Sources,
dataset hashes and limitations are saved with each geographic build.

## Battlefield terrain

War overviews and battle terrain use separate renderers. The Austerlitz battlefield
study shows a tilted elevation mesh, contours, the Goldbach stream and village markers.
It is a terrain preview, not a reconstructed battle replay. See the
[battlefield report](docs/BATTLEFIELD_TERRAIN_REPORT.md) for sources and limits.

```powershell
& $researchPython -m war_content.battlefield
& $researchPython -m war_content.play --mode battlefield
& $researchPython -m war_content.play --mode campaign
```

## Unit movement preview

The [unit animation layer](docs/UNIT_ANIMATION_REPORT.md) adds staggered departure,
individual turns, route-following columns, formation transitions and stable halts.
It uses the approved silhouettes and can render on measured battlefield terrain.

```powershell
& $researchPython -m war_content.animation_study --terrain output/content/TERRAIN-BUNDLE
& $researchPython -m war_content.play output/content/ANIMATION-BUNDLE
```

The generated study is explicitly illustrative and not publishing-ready. It runs
offline using approved library assets; source-grounded production routes remain
the director's responsibility. Playback is silent.

## Sound effects

The [sound-effects stage](docs/SOUND_EFFECTS_REPORT.md) compiles movement Foley from
the saved animation timeline, supports original synthesis or replacement recordings,
and ducks effects beneath supplied narration. Weapon sounds require explicit cues.

```powershell
& $researchPython -m war_content.sound_effects output/content/ANIMATION-BUNDLE --profiles examples/sound/unit_animation.json --video output/units/unit-animation.mp4
& $researchPython -m war_content.play output/content/SOUND-BUNDLE
```

Outputs include editable sound configuration, a cue plan, WAV stems and a Markdown
report. Sound-enabled bundles play audio with Play/Pause, seek and mute controls;
normal MP4 export includes the soundtrack automatically. Music is separate.

## Tests

No API keys, paid requests, or test packages are needed:

```powershell
& $researchPython -m unittest discover -v
& $researchPython tools/check_tests.py
node --test renderer/tests/*.test.mjs
```

The second command also writes standard-library line-coverage reports under
`output/coverage/`. Tests use synthetic evidence and injected fake services.
