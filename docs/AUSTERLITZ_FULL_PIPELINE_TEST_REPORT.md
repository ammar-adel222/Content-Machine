# Austerlitz full-pipeline live test

Follow-up: [short-form corrections and equipment icons](SHORT_FORM_CORRECTIONS_REPORT.md)
address the user review of this original test output.

## Purpose and current result

This test runs a real short battlefield video through research, writing, review,
direction, Gemini speech, measured timing, terrain/unit design, PixiJS picture,
movement effects, quiet music, mixing and final container checks. It exercises real
free-tier services separately from the offline unit suite. The final approval gate
is retained: testing never approves or publishes the video on the user's behalf.

**Completed:** all 17 stages produced accepted artifacts; the project is
`awaiting_review`, with no dirty stages, no blocking issues and no human approval.
The live test required the manual interventions described below.

- Final preview: [final.mp4](../output/austerlitz-full-pipeline/final.mp4)
- Duration: **114.066667 seconds** (measured audio plan: 114.04 seconds).
- Picture: **1080 x 1920**, H.264, **30 fps**.
- Audio: **48 kHz stereo AAC**; final file size **10,091,985 bytes**.
- Complete FFmpeg decode: passed with no reported errors.
- Actual final-video frames at 10, 43, 80 and 110 seconds were inspected.
- Local software picture rendering took **544.3 seconds**, about nine minutes;
  mixing took 34.3 seconds and final muxing took 4.4 seconds. This is a supervised
  debugging run, not a benchmark of uninterrupted whole-pipeline throughput.
- Aggregate saved usage: **65 logical model attempts**, **8 search requests**,
  **12 TTS attempts** (ten successful clips and two rate-limit failures).
  Transport-level retries can add HTTP requests beyond these logical counters.

The native final review gate was reached without calling approval or publishing.
The project and exact artifact IDs are retained in the audit below.

## Inputs and provider choices

- Topic: Battle of Austerlitz; target 90-120 seconds; vertical 1080 x 1920 priority.
- Research used the configured Gemini 3.8 Flash and 3.5 Flash Lite fallback.
- Repeated primary-model timeouts required a per-run Gemini 3.5 Flash override for
  writing, script review and direction. Repository model defaults were preserved.
- Visual planning/design/review used Qwen through Groq, including actual rendered
  asset and scene images. No substitute fake model outputs were accepted.
- Gemini Flash TTS generated ten phrase clips. Their assembled measured duration,
  including requested pauses, is 114.04 seconds.
- Existing source-tracked Austerlitz terrain supplied measured relief, village
  anchors and the modern Goldbach course. This was not a new autonomous GIS lookup.
- Music uses the original ambient source, mixed quietly beneath narration with
  ducking. Effects use the existing movement Foley implementation.

## Manual guidance required

This is a supervised end-to-end test, not evidence that topic-to-video production
is reliable without intervention. Generated drafts needed duration guidance and
removal of unsupported mental-state wording, an out-of-bounds northern subplot,
invented river crossings and overly broad treaty wording. The director retained
valid choreography after a narrow closing-script edit, subject to a fresh review.

Troop anchors and paths were manually checked against the existing measured terrain
and historical references, including the [West Point atlas](https://dhc.westpoint.edu/atlases/)
and [Napoleon.org Austerlitz discussion](https://www.napoleon.org/en/history-of-the-two-empires/articles/the-battle-of-austerlitz-and-the-principles-of-war/).
They depict approximate operational sectors; they are not surveyed formations or
exact historical tracks. Camera overrides were supplied after real screenshots
showed troops outside the focal frame. No final human approval was supplied.

## Defects found and corrected

1. **Spoken time validation.** The writer treated spoken "four thirty p m" as a
   year-like number. Clock normalization now matches supported clock expressions
   without treating them as troop counts. Two regression tests cover this.
2. **Windows path length.** Narration assembly appended a long temporary suffix to
   a content-addressed filename and exceeded Windows MAX_PATH. Atomic writes now
   use a short UUID temporary basename in the destination directory.
3. **Provider image compatibility.** Groq rejected a multi-image scene review.
   Reviews now send one actual scene image per request. Completed passing frame
   reviews survive subsequent failures and are reused.
4. **Free-tier recovery.** TTS and visual work encountered HTTP 429 responses.
   Completed phrase clips, audited manifests and reviewed assets were retained.
   Visual requests honor bounded short rate-limit resets; no paid provider switch
   was used. Repeated real review rounds required explicit bounded test-budget
   increases, recorded in the run manifest.
5. **Independent camera editing.** Structured per-scene camera overrides now update
   framing without changing historical action geometry or regenerating speech.
   Unknown scene IDs fail and the final picture must match its reviewed framing.
6. **Tactical layout.** Full-phrase captions covered units. Short timed word groups
   now find gaps between visible unit rows, preferring screen edges. Off-screen
   contextual units no longer displace them into the action. Word-level timing is
   approximate within measured phrase intervals, not forced alignment.
7. **First-export camera inheritance.** Multiple camera edits before any picture
   existed left the picture stage without older overrides. Picture settings now
   inherit the current reviewed framing; a regression covers an absent prior picture.
8. **Map labels and credits.** Stream segments no longer repeat the same label;
   tactical labels use collision avoidance and leader lines. Compact credits retain
   full source metadata in the saved contract. The baked-in silent-preview footer
   was replaced with the approximate-deployment disclosure for production replays.

## Editing and saved artifacts

The SQLite project stores immutable artifact receipts, dependency hashes, revision
history, bounded provider counters and native LangGraph checkpoints. Narrow script,
camera and mix edits retain unaffected work. A camera edit demonstrated reuse of
research, script, narration, direction, terrain, assets and prepared audio.

The local run manifest is `output/austerlitz-live-run.json`. The audit snapshot is
`output/austerlitz-full-pipeline-result.json`; it includes exact artifact paths and
aggregate provider usage across revisions. Generated media and audits remain under
ignored `output/`; API credentials are neither copied nor written into reports.

## Verification

- Complete offline Python suite: **369 tests passed**.
- Production adapter follow-up: **25 tests passed** after review and first-export changes.
- Renderer/browser suite: **24 tests passed**, including real WebGL loading,
  deterministic backward seeking, both frame formats, label handling, short
  captions, dense unit rows and off-screen collision inputs.
- The initial browser command used the wrong working directory and failed fixture
  lookups; running the documented command from the repository root passed.

## Limits and next improvements

Sampled frame review does not verify every animation frame or establish historical
truth. Automatic model reviewers both caught real defects and produced some
questionable layout findings, so review remains advisory evidence behind a gate.
Spatial authoring and camera composition required human corrections. Speech still
needs listening approval, and approximate caption word timing can drift within a
phrase. Original ambient music is an available baseline, not a historical score.
A single successful supervised Austerlitz run does not validate other battles,
modern equipment, campaign-scale geography, or unattended publishing.


## Measured audio mix

The actual mix uses music gain -28 dB, with -10 dB narration ducking and a
22 dB minimum voice margin. Measured music RMS is approximately -56.55 dBFS;
final peak is -1.02 dBFS. Fades are two seconds in and three seconds out.
These measurements confirm quiet levels and technical headroom; they do not replace
listening for delivery, pronunciation or subjective balance.


## Remaining visual findings from the finished video

Frame sampling is incomplete coverage: a top caption around 80 seconds overlaps the
north indicator, despite the scene midpoint passing model review. Captions may also
change vertical position between word groups as units move. Some contextual forces
sit at the edge of a shot. The next visual refinement should reserve HUD space and
stabilize caption positions per shot, with checks beyond a single midpoint. These
issues are disclosed rather than describing the output as visually perfect.
