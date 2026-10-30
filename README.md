# War Content Machine — edition two

An independent research agent for ancient and modern wars and battles. It discovers
or accepts a topic, retrieves evidence, and saves versioned JSON/Markdown dossiers.
Default video target: **105 seconds** (normally 90–120, allowed 60–150).

See [the research agent build report](docs/RESEARCH_AGENT_REPORT.md) for architecture,
inputs/outputs, tests, live checks, and limitations.

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

## Tests

No API keys, paid requests, or test packages are needed:

```powershell
& $researchPython -m unittest discover -v
& $researchPython tools/check_tests.py
```

The second command also writes standard-library line-coverage reports under
`output/coverage/`. Tests use synthetic evidence and injected fake services.
