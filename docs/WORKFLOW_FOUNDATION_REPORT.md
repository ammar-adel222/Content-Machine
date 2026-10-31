# Workflow foundation: saved projects and targeted edits

Follow-up: [authoring integration](WORKFLOW_AUTHORING_REPORT.md) now connects research,
writing, script review, direction and plan review. The scope/test counts below record
the original foundation milestone; the follow-up report describes the current additions.

## What is implemented

The first orchestration layer is implemented in `war_workflow/` using real LangGraph,
durable SQLite checkpoints and a separate project database. It keeps the existing
agents independently callable. This step implements project/revision state, edit
routing, content reuse, budget accounting, resumability and final approval.

There are 17 named production-stage slots plus routing and human-review nodes.
Four live adapters are connected: the existing audio/music mixer, audio checks,
video/audio muxing and final technical media checks. Full authoring adapters for
research, writing, directing, TTS, geography, assets and picture rendering are not
connected yet. Missing adapters stop explicitly; they do not fabricate content or
claim an end-to-end historical video was produced.

New-project defaults remain portrait and a 105-second target. Existing short studies
can be imported for audio-only editing. Experimental sound generation stays separate.

## Saved state and artifact identity

Each project has:

- `project.sqlite`: current head, versioned revisions, idempotent edit requests and
  per-revision budget counters.
- `checkpoints.sqlite`: actual LangGraph state and persisted human-review interrupts.
- `artifacts/STAGE/HASH.json`: immutable typed output manifests and media hashes.
- `receipts/STAGE/INPUT-KEY.json`: complete computation receipts for cache/resume.
- `work/REVISION/STAGE/`: adapter output files and media bundles.

An edit creates a new revision and retains the parent's configuration and artifact
references. An expected parent revision prevents concurrent/stale edits from silently
overwriting a newer request. Replaying an identical request ID returns its original
revision; reusing the same ID for different instructions is rejected.

Exact artifact identity is separate from computation identity. Cache keys cover stage,
adapter version, parameters, scoped instructions and selected input hashes. Named
semantic views can isolate speech, duration, waveform or visual dependencies. Missing
views fall back to the complete content hash, favoring correctness over a false hit.

An adapter can rebind a cached computation to current provenance without repeating
generation. This hook must validate its current domain contracts; the coordinator
does not silently rewrite a saved script/dossier fingerprint. Each rebound output
gets its own exact artifact ID while retaining the reusable computation key.

Manifests and referenced files are checked before reuse. Failed review outputs remain
available as drafts, but are not put in the passing computation cache. Receipts are
published before progress updates, allowing a result saved immediately before a
progress/checkpoint crash to be reused on the next run.

## Edit routing and review gates

Content dependencies determine dirty stages; review gates determine whether execution
may proceed. Keeping those separate prevents an audio check from forcing a picture
rerender. A music-mix edit invalidates only `mix`, `audio_review`, `mux`, `final_review`
and approval. A unit-design edit affects assets and relevant visual work without
automatically regenerating narration or effects. A route edit affects direction and
dependent spatial/timing/effects work, while retaining unchanged narration.

Scene/object scopes are saved and passed to adapters. The foundation does not yet
implement per-scene TTS or scene-chunk rendering; those live adapters still need to
honor the scopes and continuity rules in the graph plan.

Unknown/missing prerequisites, failed reviews, altered media or unavailable adapters
produce actionable `needs_input` states. A new edit arriving during execution causes
the older run to stop at its next stage boundary as `superseded`. The in-flight stage
is not forcibly killed, and its completed receipt remains reusable by the new revision.

## Budgets and recovery

Model, search and TTS attempt reservations are atomic SQLite updates. They are shared
across a revision and are not reset by resuming that revision. Budget exhaustion
produces `quota_wait`. Budget ceilings can be adjusted through the store API.

These counters are local logical-attempt budgets, not provider token/rate meters.
Live agent adapters must connect their consume callbacks and account for their
existing retries. No provider-wide admission controller or timed 429 retry scheduler
is claimed in this step.

One worker runs a project at a time, enforced with an OS-released file lock. SQLite
handles close explicitly, including on Windows. Different revisions retain distinct
LangGraph thread IDs. Independent-node parallel execution is a later integration
step; the first executor runs ready dirty stages serially to establish safe reuse.

Checkpoints/receipts reduce repeated work, but do not guarantee exactly-once remote
API billing if a process loses a response before saving it. Agents' local retries
are not surrounded with another automatic graph retry loop here.

## Human review and publication

When work is complete, LangGraph pauses with an actual `interrupt()` naming the exact
video hash and path. The project remains `awaiting_review`. Approval resumes that
saved interrupt, checks the current revision, media hashes and matching final review,
then records approval. Repeated approval is idempotent. Edits clear approval, and an
older revision cannot approve over the current head.

No publishing adapter is connected. A local technical pass or approval does not
convert an imported terrain/animation study into publishing-ready historical content.

## First live adapter demonstration

An existing approved movement/music preview was imported as an audio-edit project.
Its actual stems, prepared music and picture were registered by hash. No research,
script, director or TTS history was invented during import. The imported picture
approval applies only to that unchanged picture; the new final audio/video still
requires its own human review.

Changing music gain from -22dB to -28dB executed exactly:

1. `mix`
2. `audio_review`
3. `mux`
4. `final_review`

The real run completed in about 8.6 seconds. It reused the picture artifact and
reserved **zero model, search and TTS calls**. It stopped at the persisted final
review interrupt; the demonstration has not been approved automatically.

Local artifacts, ignored by Git:

- [Project metadata/result](../output/projects/music-edit-demo-result.json)
- [Graph-produced final video](../output/projects/music-edit-demo/work/48771dbd60a24c43b00f34064bdb1db8/mux/final.mp4)

Imported media references currently use absolute paths, including references outside
the project folder. Keep those version folders intact. A self-contained project
archive/rebase operation is a future feature; source music bundles themselves retain
their existing portable stems and originals.

## Installation and usage

Pinned optional packages are LangGraph 1.2.19 and its SQLite checkpointer 3.1.3.
They were installed and tested in the workspace `.venv`, leaving the shared runtime
unchanged. To set up another checkout:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[geography,workflow]"
& .\.venv\Scripts\python.exe -m war_workflow init --topic 'Battle of Austerlitz'
& .\.venv\Scripts\python.exe -m war_workflow status PROJECT-PATH
```

The installed `war-project` command is equivalent. A fresh authoring project currently
stops at the first missing live adapter. For an existing approved picture/music bundle:

```powershell
& .\.venv\Scripts\python.exe -m war_workflow import-media MUSIC-BUNDLE --video APPROVED-PICTURE.mp4 --picture-approved
& .\.venv\Scripts\python.exe -m war_workflow edit PROJECT-PATH --parent REVISION-ID --kind music_mix --settings examples/workflow/music-quieter.json
& .\.venv\Scripts\python.exe -m war_workflow plan PROJECT-PATH
& .\.venv\Scripts\python.exe -m war_workflow run PROJECT-PATH
# After reviewing the exact final video:
& .\.venv\Scripts\python.exe -m war_workflow approve PROJECT-PATH --revision REVISION-ID
```

Use `--picture-approved` only for a picture already reviewed. Edit requests can carry
`--scene`, `--object` and `--notes`. Configuration edits should enter through this
API instead of modifying immutable artifact files. `ProjectStore.set_limit()` is the
current budget-adjustment API. Graph invocation never publishes remotely.

## Verification

**278 Python tests and 20 JavaScript/browser tests pass** in the workflow-enabled
environment. The 22 workflow tests cover targeted invalidation, persistent revisions,
stale edit rejection, idempotent requests, concurrent budget reservation, artifact
integrity, worker locks, real LangGraph execution, process reopen, budget resume,
failed/missing adapters, saved-result crash recovery, semantic view reuse, provenance
rebinding, durable approval, stale review rejection, retained drafts, superseded runs
and real-stem media adapters. Provider and encoder calls are mocked in unit tests.

The actual music-edit demonstration separately exercised real mixing, FFmpeg muxing,
container checks and SQLite-backed human interruption. `pip check` reports no broken
requirements. Production renderer regressions remain passing.

## Next integration work

Connect research/writer/director through domain-aware provenance/review adapters,
then implement Gemini TTS/timing and grounded spatial-plan integration. Add provider
admission control and bounded owner-directed repair loops before parallel authoring.
Scene-chunk rendering, archival/export and publishing remain later steps.

Official references used for the implementation:
[LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence), and
[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
