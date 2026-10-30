# Quality reviewer — build report

## Role

The new `war_reviewer` package is independently callable and also used by the director.
It compares a script or storyboard against supplied research and returns actionable
quality findings. It uses Gemini's free API through the existing adapter. There are no
new dependencies and no publishing or source-editing side effects.

Its current review scope is **script and storyboard quality**. It does not conduct new
web research, independently verify every historical source, listen to generated audio,
or inspect rendered video. Those require additional tools/artifacts at later stages.

## Quality contract

The model scores five dimensions from 0 to 5: accuracy, clarity, visual logic, voice
direction and phone readability. A score below **4** requires revision. Findings distinguish
blocking problems from advisory suggestions, with scene IDs where relevant.

The returned `QualityReview` records the reviewed artifact fingerprint, findings, local
issues and model identities. Final pass/revise status is calculated in code. The model
cannot override a known local problem or pass a low score by omitting issue text.

The prompt asks for substantive factual and visual problems: invented maneuvers, wrong
chronology, unexplained arrivals, rigid whole-army motion, ignored terrain, lost narration
emphasis, and clutter. Faithful paraphrases and an explicitly schematic layout are allowed;
the reviewer should not demand exact survey coordinates or every optional historical detail.

This is a separate role and interface, but the default reviewer uses the same configured
Gemini model family as generation. It is not an independent factual authority. A live trial
gave high scores to a plan with an incorrect target and retreat depiction; manual review
identified the errors and prompted stronger deterministic checks in the director.

## Integration and loop behavior

The director first checks provenance, script validity, timing, geometry and continuity.
Only locally valid drafts go to semantic review. A blocking review triggers one bounded
repair, with generation and review sharing a default four-model-attempt budget. The final
plan retains its review report. Failed/unavailable review leaves the plan unready.

Standalone review can inspect a draft script or incomplete plan and preserve its known
local issues instead of hiding them. Input version mismatches and broken evidence are
rejected. Reviewing a measured plan requires the corresponding audio timing file.

The writer's existing inline review remains in place for compatibility. The new reviewer
can be run explicitly against a saved writer result. LangGraph integration will coordinate
cross-agent review and routing; it has not been built in this change.

## Run it

```powershell
# Review a saved script.
python -m war_reviewer 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Review a director storyboard.
python -m war_reviewer 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' --plan 'output/directing/PLAN/storyboard.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Use `--audio-timing FILE` for a plan compiled from measured audio. `--model` overrides
Gemini Flash-Lite; `GEMINI_MODEL` is also respected. API credentials stay in the supplied
environment file and are never included in reports.

Each run creates a new folder under `output/reviews/` containing `review.json` and
`review.md`. Exit codes: 0 pass, 2 revise, 1 input/provider failure. Scores and pass status
are quality signals, not human approval to publish.

## Verification

Offline tests cover passing reviews, score thresholds, blocking/advisory behavior, local
issues the model cannot override, invalid/stale inputs, CLI operation, and measured-plan
requirements. Director tests also cover review failure, shared budgets and repair loops.

A live standalone Gemini review of the saved Falklands script returned pass:
[local review report](../output/reviews/87f40fb07f6a48a19bc7546b80efef5a/review.md).
This generated example is ignored by Git and exists only in the local workspace.

Final combined result: **184 offline tests passed**. Reviewer agent and models have
**100% measured line coverage**; its CLI has **98%** (the executable entry-point line is
exercised by a live command run). Line coverage measures exercised code, not review
accuracy, exhaustive branches, or the quality of the eventual video.
