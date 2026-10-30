# Writing agent — implementation report

## Purpose

The writer turns an existing ready research dossier into an English short-form war or
battle explanation. It owns the narration, scene structure, and vocal performance
directions. It does not research new facts, generate speech audio, animate the map,
or publish content. It runs independently through its library API or CLI.

The normal target remains **90–120 seconds**, defaulting to the dossier's target
(usually 105). The supported range is 60–150 seconds. Estimated timing includes planned
pauses and different speaking rates; final timing must come from the generated audio.

## What the writer produces

Each script has a title, caption, overall narrator style, pronunciation guide, and 4–10
scenes. A scene contains:

- A stable ID such as `s2` and its role: hook, context, maneuver, turning point, or outcome.
- Research claim IDs supporting the scene.
- A short visual intent explaining what the viewer should understand; the future battle
  director still owns map choreography, coordinates, camera movement, and exact timing.
- Tone and delivery instructions separate from the spoken words.
- One or more spoken phrases, each with its pace, exact words to emphasize, and a desired
  pause afterward in milliseconds.

Splitting spoken text into phrases allows a pause **inside a sentence** without putting
`[pause]` markers or SSML into the words that a TTS service should read. Example:

```json
{
  "text": "The crossing looked open.",
  "pace": "normal",
  "emphasis": ["open"],
  "pause_after_ms": 550
}
```

The next phrase can change pace or emphasis. Not every sentence needs a dramatic pause;
the prompt asks for conversational phrasing, a restrained documentary voice, and space
for key ideas. Pronunciation spellings are advisory and require an audition; they are not
presented as verified linguistic research.

## Workflow and checks

1. Load and validate the saved research dossier. Refuse incomplete research, blocking
   gaps, or broken source evidence before making model calls.
2. Compute a deterministic SHA-256 fingerprint of the research contract. This records
   exactly which research version the script used.
3. Generate a draft using a compact packet of claims, terrain, events, angle and gaps.
   The writer cannot call search tools or silently replace the research.
4. Run local checks: unique scene IDs, hook/outcome structure, known claim IDs, essential
   claim coverage, explicit uncertainty wording, supported numeric figures, clean
   spoken text, valid emphasis/glossary terms, and an estimated duration within 15% of
   target and within the absolute 60–150-second range.
5. If local checks pass, request a model review against the same research. This checks
   interpretation, chronology, title/caption, causal clarity and spoken delivery. It is
   a second call, not a claim of independent verification by another model or historian.
6. Allow one repair, then check and review again within the model-call budget. Default
   budget is four provider attempts, including explicit fallback attempts.
7. Save the script as `ready` only if local checks and model review pass. Save usable
   partial work as `needs_revision` when issues or review/budget failures remain.

The writer does not silently stretch audio or rewrite the dossier to pass these checks.
`ready` is a writing-stage result, not human publication approval.

## Independent edits and outputs

A whole-script revision can take a previous `script.json` and new notes. A targeted edit
also specifies a scene ID. For that case the model returns only a replacement scene;
code copies the previous draft and replaces that scene. Global metadata and all other
scenes remain intact. The entire result is still checked for timing, coverage and factual
consistency. A wrong scene ID is rejected rather than applied elsewhere.

Every save creates a new folder, preserving previous versions:

| File | Purpose |
|---|---|
| `script.json` | Structured script, supporting claim snapshot, research hash, parent-script hash, changed scenes, review issues and model usage |
| `script.md` | Readable narration, scene-by-scene voice direction, pronunciation guide and provenance |
| `tts_plan.json` | Provider-neutral spoken chunks, delivery instructions, pause targets and IDs for later timing alignment |

The TTS plan preserves the script status. A future audio adapter must refuse automatic
production of a `needs_revision` plan. It must measure real speech and apply required
silence during assembly rather than assume Gemini honors millisecond pauses exactly.
The plan can support synthesis at phrase or scene level; blindly making a separate
request for every short phrase can harm vocal continuity and increase quota use.

Revisions require the same dossier fingerprint. If research changes, create a new draft
instead of applying an old scene patch against changed facts.

## Providers and model choice

The writer defaults to Gemini's free API with `gemini-3.5-flash-lite`, following the
user's final decision to defer other comparisons. `--model` or `GEMINI_MODEL` overrides
the text model. Stronger Gemini models can be selected explicitly when quota permits;
there is no automatic upgrade to a scarce model. Gemini TTS remains the intended audio
provider, independently of this text-model choice.

Gemini receives a simplified native JSON grammar because its API rejected the writer's
full nested constraint schema. The full schema is still included in instructions and
Pydantic applies every constraint locally. Text limits, pause bounds, scene-ID patterns,
and structural checks remain enforced. Research uses the same shared adapter and its
existing tests remain passing.

The shared adapter now supports OpenRouter for research as well. Existing research
defaults remain unchanged. OpenRouter requests have a zero-price provider cap, so model
experiments remain within the requested free-API scope. This build does not authorize
paid MiniMax usage. See [the model comparison](MODEL_COMPARISON.md) for current MiniMax
options, limitations of benchmark comparisons, and pricing sources.

OpenRouter and Groq remain optional adapters for future comparison. Some free endpoints
do not support JSON mode. The adapter requests JSON through the
prompt, removes an outer Markdown JSON fence when present, validates with Pydantic,
and supports explicit provider fallback. It never evaluates generated code. OpenRouter
has a 180-second socket timeout to accommodate slower free inference; existing provider
timeouts remain 60 seconds. Temporary transport failures can retry once.

Credentials come from the existing external `.env` and are not copied into this project.
Only `OPENROUTER_API_KEY` is needed for the default writer; Tavily is not required to
write from a saved dossier. The writer adds no external package dependencies.

## Run it

From the project root, with Python 3.11+ and Pydantic installed:

```powershell
python -m war_writer 'output/research/THE-RUN/dossier.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

python -m war_writer 'output/research/THE-RUN/dossier.json' --previous 'output/writing/THE-VERSION/script.json' --scene s2 --notes 'Make the explanation calmer and pause before the reversal.' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

python -m war_writer 'output/research/THE-RUN/dossier.json' --provider gemini --target-seconds 120 --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Use the bundled interpreter described in the root README if `python` is not on PATH.
CLI exits: 0 = ready; 2 = saved but needs revision; 1 = input/configuration/provider error.
Model fallback is opt-in via `--fallback`. Existing process variables override `.env`.

## Tests and verification

Unit tests are offline and use synthetic evidence. They cover request/model validation,
duration estimates, pauses, citations, uncertainty, digits and English integer words, markup separation,
essential coverage, review and repair budgets, provider failure, parent fingerprints,
targeted scene preservation, versioned storage, TTS handoff and CLI behavior. The shared
OpenRouter adapter has tests for fenced JSON, malformed responses, credential handling,
and zero-price request routing. Existing research tests remain in the suite.

```powershell
python -m unittest discover -v
python tools/check_tests.py
```

Final offline result: **145 tests passed**, including all 91 original research tests.
Standard-library line coverage: **100%** for writer workflow, models, and storage, and
for shared provider adapters; **98%** for the writer CLI. The uncovered CLI entry-point
line is exercised by live command runs rather than import-based tests. Existing research
core modules also retain 100% line coverage. Coverage measures executed lines, not
historical accuracy, exhaustive branches, or audio quality.

Live Gemini checks used the existing external credentials file and the saved Falklands
War dossier. Initial drafting produced a saved reviewable script; review flagged a phrase
in its opening. A targeted revision of `s1` then passed current local checks and model
review, while preserving all other scenes and global metadata.

Final example: [Gemini Falklands script](../output/writing/falklands-war-713ba1c434e8477aaf388f7e044b2142/script.md).
This is a generated local artifact under ignored `output/`, not a file shipped on GitHub.
Its `script.json` and `tts_plan.json` are in the same folder. No speech was synthesized.
The final example has **205 spoken words**, **5 scenes**, **25 directed phrases**, and an
estimated **94.89-second** duration against a 105-second target. Its final scene-edit run
used two Gemini Flash-Lite calls and reports only `s1` as changed. This also demonstrates
that changing a scene does not rerun research or regenerate the other scenes.

Exploratory OpenRouter checks occurred before the user chose to defer comparisons:
Super VL produced valid but too-short drafts; an Ultra draft initially passed weaker
checks but manual inspection found an unsupported spelled-out distance. That led to
English number checks and a stronger semantic-review prompt. Later Ultra probes also
returned upstream errors. The direct MiniMax M3 :free route returned 404 despite its
public free-model page. The remaining free-router run was stopped when the user chose
Gemini. These trials are not a valid model-quality ranking; all exploratory OpenRouter
requests had zero-price routing caps and no paid MiniMax inference was performed.

Development trial outputs remain in the ignored output directory. Earlier `ready` flags
predate strengthened validation; use the final example above for this build. Future
production should revalidate saved scripts against the current rules, not trust an old
status alone. Model reviews can miss errors, as this live check demonstrated.

## Limits

- Claim references prove provenance, not semantic entailment. A statement can still
  misuse a real claim; model review and human review remain necessary.
- Numeric checking covers digits, common English integer words and ordinary spoken
  years. Explicit small rounding is allowed for cited quantitative facts, with a 5%
  tolerance; dates are not rounded. This is not a complete arithmetic or language parser:
  implicit ratios, complex fractions, unit mismatches and unsupported nonnumeric details
  still need semantic and human review.
- The default reviewer uses the same configured model chain. It is not an independent
  factual authority, and models can share blind spots.
- Duration is an estimate based on 130/150/170 words per minute plus explicit pauses,
  not measured audio. Punctuation, names, and delivery affect actual timing.
- The initial writer is English-only. Multilingual writing and verified pronunciation
  research have not been implemented.
- A weak but structurally ready dossier can still limit storytelling. The writer should
  surface that limitation instead of inventing the missing tactical explanation.
- No audio is generated and no Gemini TTS integration is claimed by this build.
