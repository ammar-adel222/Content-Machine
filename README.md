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

Default text model: `gemini-3.5-flash-lite`. Use `--provider groq` to select Groq,
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

The writer defaults to Gemini's free API using `gemini-3.5-flash-lite` and the existing
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
Other providers are not being compared. Inputs must use matching research/script versions.

## Tests

No API keys, paid requests, or test packages are needed:

```powershell
& $researchPython -m unittest discover -v
& $researchPython tools/check_tests.py
```

The second command also writes standard-library line-coverage reports under
`output/coverage/`. Tests use synthetic evidence and injected fake services.
