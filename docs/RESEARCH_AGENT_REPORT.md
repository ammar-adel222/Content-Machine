# Research agent — implementation report

## What this component does

This is the first implemented part of Content Machine edition two. It is a standalone
Python research package, independent of the first edition, the future writer, and the
PixiJS renderer. It does not generate narration, animation, or publish anything.

It accepts a specific war or battle, discovers a subject within a direction, or chooses
an automatic topic. Both ancient and modern conflicts are supported. Whole wars remain
valid video subjects: their research focuses on fronts, campaigns, strategic changes,
and outcomes, while battle research focuses on deployments, terrain, and maneuvers.

The default video target is **105 seconds**, within the agreed normal range of 90–120
seconds. Requests can specify any target from 60 through 150 seconds. This is a research
planning target; actual narration timing belongs to the future writing/audio stages.

## Design and workflow

There are six small package files: models, providers, the agent workflow, storage, a CLI,
and public package exports. Pydantic is the only external runtime dependency. HTTP, JSON,
environment loading, caching, reports, and unit testing use the Python standard library.
There is no LangGraph, database, rendering library, or UI dependency in this component.

The workflow is:

1. **Discover:** search for source-supported candidates. Score story potential, visual
   explainability, evidence, duration fit, and novelty from 0–5 each. Sort the scores in
   code and remove duplicate/excluded names. Specific topics are preserved rather than
   silently replaced. Scores are model judgments, not measured audience performance.
2. **Save selection:** write `discovery.json`, including the request, candidates,
   discovery evidence, usage, and model identity. Research can resume from this file.
3. **Collect:** retrieve Wikipedia orientation text and make separate web searches for
   facts/forces, terrain/geography, and battle or campaign progression. A separate search
   finds Wikimedia Commons map references. Extract selected pages for more context.
4. **Synthesize:** supply a bounded set of relevant passages to the model. Produce
   claims, terrain descriptions and effects, a chronological event sequence, and a
   writer handoff containing essential versus optional claims.
5. **Check:** validate evidence references, claim IDs, director references, and event
   ordering. Assess essential coverage and source-domain diversity. If essential gaps
   remain, perform one focused follow-up search when the remaining budget permits.
6. **Save:** write a new dossier folder containing machine-readable JSON and a readable
   Markdown report. Automatic discovery can try another shortlisted candidate if the
   first remains incomplete and budget is available. A specific topic is never swapped.

## Evidence and uncertainty

Every claim points to a retrieved passage ID such as `S2:P1`. **The code attaches the
source and exact passage text**, ignoring any quotation text invented by the model.
For Gemini, the response schema constrains passage IDs to the actual available IDs.
Groq uses JSON mode plus the same schema in its instructions, followed by local validation.

Claims distinguish documented accounts, estimates, disputes, and inferences. Dates,
duration, location, forces, terrain, chronology, context, and outcome are separate claim
categories. Terrain features include spatial relationships and tactical consequences.
Events include actors, locations, actions, reasons, consequences, and supporting claims.
The research does not invent drawing coordinates; the future director owns visual layout.

Validation attempts one bounded repair. If citations or links remain invalid, unsupported
claims and dependent structured items are removed and the result is marked incomplete.
The uncited summary is replaced with a partial-research notice in that case.

The dossier separates **ordinary uncertainties** from **blocking gaps**. An unknown exact
clock time is retained without necessarily preventing a useful overview. Missing evidence
essential to the selected angle, missing required categories, missing director information,
or fewer than two cited non-map source domains blocks readiness. Two domains are only a
minimum diversity check; they do not prove that two accounts are independent.

For ongoing conflicts the request carries an information cutoff, which is included in
searches, model instructions, and the report. This is not a guarantee of historical
knowledge as of that date: unknown publication dates and retrospective pages still need
review. Official accounts are not automatically treated as independent confirmation.

## Inputs and outputs

The principal Python interfaces are:

```python
from war_research import ResearchAgent, ResearchRequest

discovery = agent.discover(ResearchRequest(
    mode="specific", topic="Battle of Austerlitz", scope="battle",
    target_seconds=105,
))
dossier = agent.research(discovery)
```

`agent` receives injected web/model adapters and an optional disk cache. This keeps the
workflow testable and allows providers to change without coupling it to other agents.

Saved artifacts:

| File | Purpose |
|---|---|
| `discovery.json` | Reusable topic selection, candidates, original request, and discovery evidence |
| `dossier.json` | Versioned research contract: selected topic, findings, sources, gaps, usage, and models |
| `report.md` | Readable research, director/writer handoffs, passage evidence, and source links |

Each save creates a new UUID-suffixed folder. Earlier outputs are preserved. Schema
version is `1.0`. Discovery and dossier sources have distinct ID prefixes so their
citations cannot be confused. This is stage-level resumability, not a scheduler or
automatic recovery at every individual network call.

Completed, ready dossiers in the output folder supply topic history for later discovery.
Explicit topics may be researched again. Alias-aware deduplication and importing the
first edition's publishing history are not implemented; `--exclude` supports manual history.

## Providers, credentials, and efficiency

- **Search/extraction:** Tavily REST API. Wikipedia uses the MediaWiki Action API.
- **Primary text model:** Gemini, default `gemini-3.5-flash-lite`.
- **Optional alternative/fallback:** Groq, default `qwen/qwen3.8-27b`; existing
  `GROQ_MODEL` values and CLI overrides are respected. Fallback is explicit, not mandatory.
- **Credentials:** read the supplied external `.env` at runtime. Existing process variables
  take precedence. No credentials are copied to this project or stored in research outputs.
- **Default budgets:** 10 search operations, 5 extraction URLs, and 5 model attempts.
  Budgets are shared across candidate retries. Provider fallback consumes model attempts.
- **Cache:** successful public web results are cached for up to 24 hours, with the request
  cutoff date in the cache key. Model synthesis is not cached. `--no-cache` disables it.
- **Context:** at most eight non-map sources are passed to synthesis, using bounded relevant
  excerpts. Newly found gap sources are included even when earlier sources fill the limit.
  Saved source text retains up to 12,000 characters per source.
- **Failures:** temporary HTTP/network failures have one retry. Long rate-limit waits
  surface as provider failures rather than sleeping indefinitely. Errors omit raw provider
  bodies and credentials. The HTTP timeout is 60 seconds.

Usage fields count logical search operations and extraction URLs attempted, including cache
hits. They are **not an invoice or token counter**. HTTP retries can make up to two network
attempts for an operation. Provider dashboards remain the authority on credits and quotas.

## Running it

See the root [README](../README.md) for complete PowerShell commands. For a Python on PATH:

```powershell
python -m war_research --topic 'Battle of Austerlitz' --scope battle --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
python -m war_research --direction 'Ancient ambushes' --discover-only --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
python -m war_research --selection-file 'output/research/THE-RUN/discovery.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Resume uses the saved request. Explicit budget flags can change its remaining configured
limits; start a new discovery to change the topic scope, cutoff date, or duration.
Exit status is 0 for a ready dossier or successful discovery, 2 for a saved incomplete
dossier, and 1 for configuration, provider, or unrecoverable research errors.

## Verification

The offline suite covers models and validation, ranking and exclusions, ancient/modern
war/battle workflows, preservation of specific topics, date cutoffs, grounding and repair,
partial results, essential versus optional gaps, budgets, fallback, HTTP retries, environment
loading, extraction failures, cache behavior, persistence, CLI modes, and resume behavior.
Tests use synthetic evidence and fake services, not credentials or real historical claims.

```powershell
python -m unittest discover -v
python tools/check_tests.py
```

The second command writes standard-library line-coverage reports in `output/coverage/`.
Line coverage does not measure historical accuracy, source independence, or narration quality.

Final offline result: **91 tests passed**. Standard-library line coverage was **100%**
for the workflow, data models, provider adapters, and storage; the CLI module was **98%**
(its executable entry-point line is exercised by live CLI checks rather than import-based
unit tests). This is line coverage, not a claim of exhaustive branch or historical coverage.

Live verification on October 30, 2026 used the existing external credentials file:

| Check | Result |
|---|---|
| Gemini / Austerlitz individual battle | Ready: 13 cited claims, 1 terrain feature, 3 events; 5 logical searches, 3 extraction URLs, 2 model attempts |
| Gemini / Falklands whole modern war | Ready: 9 cited claims, 1 terrain feature, 3 campaign events; 6 logical searches, 3 extraction URLs, 3 model attempts |
| Groq / Cannae topic discovery | Successful source-backed selection using the configured Groq model |
| Credential scan | Passed across 56 generated/code/document files; no local `.env` copy |

Both final dossiers retain ordinary uncertainties. The Austerlitz report notes limited
detail about every individual corps deployment. The Falklands report notes that every
intermediate skirmish/naval engagement is not covered. Neither was treated as essential
to its selected short overview. “Ready” means the implemented provenance and coverage
gates passed, not that an independent historian has verified the narrative.

Final live examples:

These example links refer to generated local artifacts under ignored `output/`; they
are not included in the GitHub repository. Run the CLI to generate your own examples.

- [Austerlitz research report](../output/research/battle-of-austerlitz-0f2d52a6316d4922870a3180802eb4d1/report.md)
- [Falklands War research report](../output/research/falklands-war-9183d866e9e6405aaa3dc0bd54ad8330/report.md)

Initial live trials exposed schema-enforcement, request-size, and model-written quotation
problems. These led to bounded context, native Gemini JSON-schema constraints, and
code-owned passage citations. Incomplete development drafts remain under the ignored
output folder; the links above identify the final verified runs. Search caches were
reused during debugging to reduce repeated API usage.

## Current limits and next integration

- The code proves that an evidence passage exists; it cannot prove that every generated
  interpretation follows from that passage. Human review and a future semantic critic are
  still important, especially for causal claims and disputed casualty figures.
- Map lookup currently returns text references. There is no image-reading, OCR, elevation
  data pipeline, geographic reconstruction, Wikimedia license-metadata ingestion, or direct
  historical-archive connector. A map title cannot establish its contents.
- Source quality is guided through search and synthesis instructions, with citation checks;
  there is no comprehensive publisher reputation or source-copy detection system yet.
- Text excerpts and source limits deliberately trade exhaustive research for predictable
  free-tier usage. Difficult subjects can legitimately remain incomplete.
- Topic exclusion currently compares normalized names, not historical aliases. Topic
  selection quality still needs evaluation across a larger representative set of subjects.
- The agent is a CLI/library component. Writing, battle direction, voice generation,
  animation, editing UI, scheduling, and publishing have not been built in this workspace.

The next component can consume `dossier.json` directly. It should preserve claim IDs and
uncertainty, and refuse automatic production when `readiness` is `incomplete`.

## API references

- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
- [MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page)
- [Gemini generateContent](https://ai.google.dev/api/generate-content)
- [Groq structured output guidance](https://console.groq.com/docs/structured-outputs)
