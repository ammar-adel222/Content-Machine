# Battle/war director — build report

## Purpose and boundaries

The director translates ready research and a ready narration script into a declarative
battlefield storyboard for the future PixiJS renderer. It plans terrain, force introductions,
routes, presentation timing, camera focus, and short labels. It does not generate video,
rewrite the script, conduct new research, or publish anything.

Individual battles use **tactical** scale with symbolic subformations. Whole-war overviews
use **campaign** scale, representing fronts, dispatches and strategic developments rather
than inventing a miniature battle for every scene. Ancient and modern force types include
infantry, cavalry, artillery, fleets, air forces and campaign army markers.

The implementation uses the existing Gemini Flash-Lite adapter, Pydantic, and the Python
standard library. No new package dependencies were added.

## Inputs and artifact contracts

Required inputs are `dossier.json` and `script.json`. Both must be ready, refer to the same
research version, and pass current evidence/writer checks. An old saved ready flag cannot
bypass updated writer validation. SHA-256 fingerprints bind the director plan to both inputs.

A plan includes:

- **Locked terrain:** sourced terrain features, passability and schematic geometry. Narrated
  and researched rocky ground, rivers, forests, roads, mountains and marshes require the
  corresponding feature. A generic land rectangle cannot stand in for all narrated terrain.
- **Forces:** identity, side, kind, start position, introduction cue and reason, research
  claim IDs, and symbolic subgroup count. Ground formations at tactical scale need at least
  three subgroups; subgroup counts are not troop-strength estimates.
- **Actions:** actor, optional target, kind, continuous route, formation, stagger, narration
  start/end anchors, supporting claims, reason and consequence. Supported kinds are move,
  withdraw, engage, highlight and fade. The renderer will implement actual follower motion,
  formation turning, visual effects and camera interpolation.
- **Scene direction:** every script scene appears in order, with one camera framing and up
  to three labels of at most 35 characters each.
- **Review and provenance:** quality findings, status, issues, input hashes, parent-plan hash,
  changed scene IDs, model identities and call counts.

All geometry is explicitly **schematic**, normalized to 0–1, with top-left origin and y
increasing downward. Both normalized axes span the full 9:16 world. A viewport width of
0.5 means half the normalized width and half the normalized height. Camera centers are
clamped to keep the requested view inside the world; this is a presentation adjustment,
not a change to historical geography.

## Timing and continuity

Actions reference existing phrase IDs such as `s3.p2` and a fraction within that phrase.
They use narration presentation time, not invented historical clock times. Without audio,
the compiler uses the writer's pace estimates plus requested pauses. Estimated timings are
clearly labeled.

An optional measured audio input has this shape:

```json
{
  "script_sha256": "THE-SCRIPT-FINGERPRINT",
  "durations": {"s1.p1": 3.2, "s1.p2": 2.8}
}
```

The file must contain **every** phrase exactly once. Values are measured spoken-audio
seconds only; requested silence is added by the compiler. Phrase boundaries can then align
to actual speech, while fractional anchors remain relative to the phrase rather than exact
word timestamps. The total must stay within 60–150 seconds.

`--retime` recompiles a previous reviewed plan using measured durations without any model
calls or changing its blueprint. It rechecks motion overlap, continuity, contact and barriers.
Actual TTS/audio integration has not been implemented; measured retiming was verified with
synthetic durations in unit tests, not a generated voice recording.

## Quality checks

Local checks reject unknown claims/forces/phrase IDs, wrong scene order, duplicate IDs,
negative or zero action durations, silent reappearance after fading, and actors/targets used
before their introduction. A later fleet cannot be targeted as though it were already present.

Movement starts from the prior position across scene boundaries. Different forces can move
concurrently; overlapping movement orders for the same force are rejected. Non-movement
actions cannot relocate a marker. Withdrawal requires explicit retreat/evacuation evidence:
surrender alone is not permission to draw a retreat arrow. Move actions also require a cited
movement event rather than only a force count or outcome.

Blocked terrain must be a valid area polygon. Segment/polygon checks detect routes entering
barriers even when both endpoints are outside. Ground forces cannot cross water, mountains
or walls; fleet routes cannot cross land polygons. Air markers are exempt from ground
barriers. A researched crossing permits passage within a schematic 0.05-world-unit tolerance.
This is **centerline validation**, not collision detection for every soldier or formation's
full footprint. Infantry/cavalry ground engagements at tactical scale must reach contact
using interpolated live positions.

A separate `ReviewerAgent` checks semantic support, causal clarity, visual logic, narration
delivery and readability. It can flag issues the local geometry rules cannot express.
The director allows one repair within a shared default four-call budget. A failed or
unavailable review cannot produce a ready plan. Unresolved plans are saved as
`needs_revision` with an empty executable timeline. Ordinary uncertainties remain visible;
only blocking gaps stop an otherwise supported overview.

## Independent edits and saved files

A targeted edit replaces one `ScenePlan`, preserving terrain, forces and other scenes.
The entire plan is rechecked: changing an endpoint can invalidate later routes, and those
dependencies are surfaced instead of silently teleporting units. Changing the input
research or script version requires a new plan.

Each save creates a new UUID-suffixed folder under `output/directing/`:

| File | Purpose |
|---|---|
| `storyboard.json` | Full versioned director artifact |
| `storyboard.md` | Human-readable terrain, introductions, actions, causes, routes and issues |
| `render_plan.json` | PixiJS handoff: blueprint, timeline, status and coordinate/motion conventions |
| `review.json` | Semantic quality review, when available |

The renderer must honor the status, schematic disclosure, introduction times, continuity,
symbolic subgroup counts and polyline paths. It must not replace a route with a straight
start-to-end slide or smooth a corner through a blocked area.

## Usage

Use Python 3.11+ with Pydantic, from the project root. The README also gives the bundled
Python path for this workspace.

```powershell
python -m war_director 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

python -m war_director 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' --previous 'output/directing/PLAN/storyboard.json' --scene s3 --notes 'Keep the fleet offshore and clarify the camera focus.' --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

python -m war_director 'output/research/RUN/dossier.json' 'output/writing/VERSION/script.json' --previous 'output/directing/PLAN/storyboard.json' --audio-timing 'audio-timing.json' --retime
```

Exit codes: 0 ready, 2 saved but needs revision, 1 invalid input/provider failure. Retiming
needs no API key. Standalone CLI review and retiming do not change upstream artifacts.

## Verification and limitations

Live Gemini trials correctly rejected a fleet sailing onto land, unsupported retreat
arrows, and camera framing outside the world. Manual inspection also caught an incorrect
engagement target that model scoring alone missed. This led to introduction and movement
evidence checks rather than relying solely on an LLM quality score.

The final targeted `s3` revision passed local checks and the reviewer while preserving the
other scenes and world. It contains **3 terrain features, 3 forces, 5 scenes and 8 timeline
events**, with an estimated **94.8923 seconds**. The revision used two model calls.

[Final local storyboard](../output/directing/falklands-war-4b97de8998534a21be6fe84b72c546da/storyboard.md).
This example is an ignored generated artifact, not a file shipped on GitHub.

Final verification: **184 offline tests passed**, including all 145 previous tests.
Director workflow, models and storage have **100% measured line coverage**; its CLI has
97% (the executable entry-point line is exercised by live command runs). The final live
storyboard was reloaded and revalidated against the current rules, with its compiled
timeline matching exactly. Tests use synthetic evidence; none make API calls. Line
coverage does not prove exhaustive branch coverage or historical accuracy.

This build does not prove historical truth or rendered-video quality. Coastlines, elevations
and routes are not surveyed GIS reconstructions. There is no pathfinding simulator, troop
physics, individual-soldier collision system, unit-footprint validation, or rendered visual
inspection yet. Physical source details and sparse research still constrain the plan.

See [the reviewer report](REVIEWER_AGENT_REPORT.md) and
[the orchestration decision](PIPELINE_ARCHITECTURE.md).
