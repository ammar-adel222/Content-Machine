# Gemini narration and measured battle timing

## What is implemented

`war_narration/` independently generates narration from a ready writer `Script`.
`war_workflow/speech.py` connects two live graph stages: `narration` and `timing`.
The graph can now research, write, review, direct, generate speech and compile a
measured action timeline. Geography, asset production and picture rendering are
still awaiting graph adapters; a fresh project stops explicitly at `terrain`.

The default is Gemini 3.8 Flash TTS with the prebuilt Charon voice. Flash-Lite TTS
is also supported through configuration. The implementation uses REST directly,
with no new dependency. There is no automatic voice/model fallback, avoiding a
narrator change partway through a video.

Google's current API separates verbatim text from turn-level delivery metadata.
The provider sends the writer's spoken phrase as text and its narrator style, tone,
pace, emphasis and relevant pronunciation hints as `speech_metadata.style`. It
requests 24kHz mono 16-bit PCM WAV, checks the completed response and validates the
returned waveform. See the [official speech API guide](https://ai.google.dev/gemini-api/docs/speech-generation).
The [current pricing page](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash-tts)
lists a standard free tier; availability and quotas depend on the configured account.
No billing tier is selected or modified by this code.

## Editing and recovery

Each phrase clip is cached by spoken text, delivery instructions, applicable
pronunciation guidance, model and voice. The cache key excludes pause length and
script metadata. Identical performance requests can share a clip, including repeated
phrases. A receipt hashes the actual WAV bytes; changed cached audio fails closed.

- Changing one phrase's text or direction regenerates that performance only.
- Changing a requested pause reassembles audio without calling TTS.
- Changing narrator voice/model or global direction affects all matching phrases.
- A narration edit can target scene IDs or individual phrase IDs, such as `s2.p1`.
  Scoped notes replace the target phrase's previous extra direction; other edits stay.
- Global voice/model/style settings require an unscoped edit. Explicit `phrase_notes`
  can also be supplied as JSON configuration.

The effective request is saved with the narration. Subsequent edits build on it,
so editing a second scene cannot discard the first scene's delivery. Graph cache
identity includes this effective request. Writer/director edit caches also now include
the previous artifact where edits depend on preserved scenes, fixing the same issue
for repeated authoring edits.

Every uncached provider request reserves `tts_requests` before submission. TTS disables
the shared transport's automatic retry; network errors cannot silently double a
reservation's API calls. A provider HTTP 429 becomes `quota_wait` in the graph.
Failed requests remain reserved. Completed clips survive both provider failure and
budget exhaustion; rerunning reuses them. A local `max_requests` additionally bounds
standalone work. Raise the appropriate limit or wait for provider quota reset, then
resume. No scheduler or provider-wide rate limiter is implemented.

Credentials are loaded at runtime and never enter cache identities or saved reports.
Cached work needs no API client. `GEMINI_TTS_MODEL` and `GEMINI_TTS_VOICE` set defaults
for a new narration; existing effective requests remain stable until explicitly edited.

## Measured clock and alignment

The assembler reads actual sample frames from each clip and concatenates them with
the writer's requested silence. Integer frame counts define starts and ends, avoiding
cumulative rounding drift. Provider-generated natural pauses remain within the clip;
the requested trailing silence is appended once. Pause edits belong to the script.

Saved outputs include:

- `Narration` JSON with exact script fingerprint, effective request, clip identities,
  hashes, sample counts, offsets, request count and reused count.
- A content-addressed full narration WAV and individual cached phrase WAVs.
- `AudioTiming` JSON compatible with the existing director's retiming API.
- A measured plan and alignment data with phrase, scene and action timing.
- Phrase-level SRT captions, ending at the clip boundary before the added silence.

The timing stage verifies the script and audio identities, then calls the existing
`retime()` checks with measured phrase durations. It preserves terrain, units, action
routes and phrase-relative anchors; only their presentation clock changes. It makes
no model call. Timing uses current full research/script/plan contracts because their
identity and terrain checks matter even if action IDs are unchanged. Stable duration,
visual and effects views allow downstream reuse.

The preferred duration remains 90–120 seconds. Narration outside that range gets a
warning. The existing 60–150-second plan validation still applies; overlong audio
stops without truncation, and an invalid retimed plan is retained for edits. The system
does not accelerate speech or invent new choreography to force a duration target.

This is **measured phrase alignment**, not word-level forced alignment. Clip boundaries
can include natural breath or silence. There is no ASR comparison proving the voice
read every word, and no automatic pronunciation or emotional-quality approval. Individual
requests may have audible phrase joins despite using one voice. Audition remains needed.

## Usage

Independent generation from an existing ready script:

```powershell
& .\.venv\Scripts\python.exe -m war_narration SCRIPT.json --config examples/narration/quiet-documentary.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

To also align a saved plan, add `--dossier DOSSIER.json --plan RENDER_PLAN.json`.
Both are validated before spending requests. Use `--output` and `--cache` to choose
storage locations. Content-hash filenames preserve old output versions. The installed
entry point is `war-narrate`.

Graph execution uses the existing command:

```powershell
& .\.venv\Scripts\python.exe -m war_workflow run PROJECT-PATH --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
& .\.venv\Scripts\python.exe -m war_workflow edit PROJECT-PATH --parent REVISION-ID --kind narration --scene s1 --notes 'Sound curious and conversational, with restrained emphasis.'
& .\.venv\Scripts\python.exe -m war_workflow edit PROJECT-PATH --parent NEW-REVISION-ID --kind narration --object s2.p1 --notes 'Give this phrase a quieter, reflective delivery.'
& .\.venv\Scripts\python.exe -m war_workflow run PROJECT-PATH --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Run and inspect each revision as needed; the last example's edits can also be combined
before running. For global changes, supply a JSON settings file through `--settings`.

## Verification

Offline tests exercise real PCM assembly, exact pauses, cache reuse, changed text/style,
voice changes, pronunciation scope, integrity failures, malformed audio/REST responses,
quota and local-limit recovery, no hidden network retries, script-version rejection,
actual action/caption retiming, duration failures, independent CLI and real LangGraph
integration. Repeated scene edits verify that earlier edits cannot silently revert.

A separate live smoke check made exactly **one** Gemini 3.8 Flash TTS request using
the existing external environment file. It returned a valid **3.24-second** WAV for
the first phrase of a saved Falklands script. No full video or historical-quality
approval is claimed from this short connectivity check.

- [Live sample WAV](../output/narration-live-smoke/sample.wav)
- [Non-secret live check metadata](../output/narration-live-smoke/result.json)

The live files are local ignored outputs. Final verification: **323 Python tests and
20 JavaScript/browser tests pass**, including 24 narration tests and the additional
authoring cache regression. `pip check` reports no broken requirements, the independent
CLI is installed, and patch whitespace validation passes.
