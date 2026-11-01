# Compact formations and synchronized clash cues

## Purpose

The previous army symbols were too far apart for their shared movement to read as a
coherent formation. Fighting was represented mainly through highlighting and fading,
so the viewer could not clearly identify when two armies engaged.

This component changes formation layout and movement, adds an explicit visual contact
signal, and synchronizes an audible impact to the same authored engagement event.
The sword/helmet/gun icon policy, persistent faction identity and fixed subtitles are
retained. The final video remains subject to human review.

## Formation and movement changes

`war_content/web/motion.mjs` now uses compact two-rank line formations. Six subgroups
occupy two ranks of three, instead of a long single string. Marching columns use a
shorter .022 normalized trailing interval, versus the previous .084 base interval.
Line frontage is .045, with separate .022 rank depth. Dispersed and wedge formations
also have smaller footprints. Group icons are 52 screen pixels instead of 68.

Each subgroup still has its own departure delay and follows the route around bends.
An additional bounded deterministic progress variation gives subgroups different
cadence without random teleporting, backward movement or overshooting the authored
endpoint. Transitioning from a column to compact ranks remains continuous.

Formations represent symbolic cohorts, not surveyed soldier positions or a literal
count of people. Formation type, waypoints, departure stagger and phrase anchors stay
in the saved director plan. Density defaults live in the renderer; changing them
requires a picture rebuild, not new research or speech generation.

## One explicit engagement event drives picture and sound

The source of truth is the existing director `engage` action, with an actor, opposing
target, phrase-based start/end, and source claim IDs. Proximity by itself does not
invent a battle. The visual cue requires both forces to be visible and opposing;
tactical ground forces must also be inside the existing normalized contact threshold.

`engagementStates()` computes deterministic active events from the saved timeline.
`createUnits()` draws a crossed-sword marker with a short gold burst at the engagement
location, plus a CLASH label. A temporary upper-frame callout names the two factions,
so an engagement near the lower map edge remains understandable on a phone. Icons
retain their faction colors and upright orientation.

The sound compiler produces a short generic clash at that same action start. It
checks both introductions, positions and ground contact before creating the cue.
It does not infer musket or cannon fire from movement or narration nouns. Explicit
weapon/impact spots remain available; an explicit spot for the action suppresses the
automatic generic onset to avoid an unwanted double hit.

The sound and visual code use the same phrase-aligned event boundary. A still image
cannot prove sound synchronization, so the live effects stem was also inspected at
the central contact boundary.

## Editable controls

Sound settings now include:

```json
{
  "clash_enabled": true,
  "clash_gain_db": -12
}
```

The example uses -10 dB for the clash source, followed by the existing effects gain,
speech ducking and final headroom management. These are source gains, not the final
mixed dBFS level. Disabling the automatic clash affects sound; the authored engagement
can still be indicated visually. Replacement `samples.clash` WAVs use the existing
editable sample path and attribution contract.

An engagement stays in the director plan rather than being copied into independent
manual sound timestamps:

```json
{
  "kind": "engage",
  "unit_id": "soult_center",
  "target_id": "allied_center",
  "start": {"phrase_id": "s4.p2", "fraction": 0.44},
  "end": {"phrase_id": "s4.p2", "fraction": 0.79}
}
```

The full Action contract also records its ID, formation, evidence, reason and
consequence. A reviewer still checks whether the engagement is historically supported.

## Austerlitz verification case

The revised saved plan keeps the existing script and narration. The initial Allied
approach and main advance are split across the opening and second scene so the main
movement does not finish before its narration. Telnitz fighting is explicitly marked
during the village-defense explanation. Soult's original central waypoints are
retained, with a compact deployment before the Pratzen engagement; the defenders fade
after contact rather than disappearing before it.

The French defense marker is anchored to the existing source-tracked Telnitz village
coordinate. The Allied approach stays east of the blocked stream corridor, without
an invented bridge or crossing. These remain approximate operational markers, not
surveyed historical army boundaries. The spatial binding was updated and rechecked
against the source terrain. A model repair that changed that geometry was rejected
by the stale-binding guard; the checked geometry was retained for the delivered plan.

The live generic clash onsets are **28.752 s** at Telnitz and **57.6112 s** at Pratzen.
The central effects stem is silent in the short interval before the new impact;
the following 100 ms measures about **-28.98 dBFS RMS** before final effects gain and
voice ducking. This establishes that a real timed sound was generated, not just a
sound field in metadata. Subjective balance still needs listening review.

Real scene frames for the compact arrangement and both engagements were rendered
and inspected before the full export. The model scene-image review passed as well.

## Integration fixes and efficient rebuilding

- Prior unit design notes no longer force an unrelated redesign after a motion edit.
- Audio dependency views include force positions, sides, engagement target IDs and
  evidence IDs, so a meaningful contact edit invalidates its effects correctly.
- The timing adapter uses the current passing external blueprint review when
  aligning an edited plan. It rejects a review for a different blueprint. The
  independent standalone timing checks remain strict.
- Research, writing, existing speech clips and prepared music are reusable. This
  run reserves zero TTS and zero search requests. Only changed visual/audio outputs
  and their downstream checks are rebuilt.

## Verification and limits

Offline tests cover compact rank bounds, shorter columns, independent monotone
progress, continuous deployment, endpoint stops, deterministic backward seeking,
invalid/distant/friendly contact suppression, introduction errors, sound disabling,
manual spot override, contact dependency invalidation, and external-review binding.
Actual WebGL tests check that clash markers and the HUD appear only during the
engagement and reproduce identically when seeking backward.

Final suite counts, exported artifact paths and full decode results are recorded below. Human approval and publishing are never performed
by this test. Dense formations and contact markers improve readability but do not
turn approximate map symbols into a physics simulation or exact historical deployment.


## Final verified result

- [10-second formation and clash preview](../output/austerlitz-formations/clash-preview.mp4)
- [Full updated video](../output/austerlitz-formations/final.mp4)
- [Final contact frame](../output/austerlitz-formations/final-pratzen-contact.png)
- [Verification and reuse audit](../output/austerlitz-formations/verification.json)

The final video is **76.366667 seconds**, **1080 x 1920 H.264 at 30 fps**, with
48 kHz stereo AAC. File size is 7,660,686 bytes. Complete FFmpeg decoding passed
without reported errors. The short preview covers seconds 53-63 of the final video,
including the central deployment, clash and aftermath.

**383 offline Python tests and 27 renderer/browser tests passed.** Real final-video
frames for the compact opening and both clash moments were extracted. The central
contact frame was inspected again from the encoded MP4.

The exact research, writing, narration and prepared-music artifact IDs are retained,
and the reviewed unit design data is unchanged. This correction used **zero search
and zero TTS requests**. The two plan/review revisions used 11 logical model attempts,
including a rejected repair; transport retries can add HTTP requests. Final picture
export took 464.2 seconds on the local software renderer while tests were also
running. Final mux took 3.0 seconds.

The final mix peaks at approximately **-1.10 dBFS**, with music at approximately
**-41.26 dBFS RMS**. The effects stem includes the two new explicit clash onsets;
these are distinct from the continuing music and narration.

Revision `e9af0429eef44c1fbf6c9de32571f2bf` has all 17 stage artifacts, no dirty stages
and no blocking issues. It is **awaiting_review**, with no human approval and no
publishing. Earlier previews are preserved rather than overwritten inside the
immutable project history.
