# Camera drift, spoken-word captions and movement trails

## Purpose

This component keeps tactical videos visually active during narration, makes captions
readable over pale terrain, and shows where marching formations came from. Portrait
1080 × 1920 remains the primary output; landscape uses the same presentation controls.

## Architecture

The PixiJS renderer computes presentation directly from playback time. It does not
accumulate animation state, so seeking backwards produces the same frame.

- Each director sector starts at its authored framing and gradually pushes in by
  eight percent. Subsequent sectors blend from the previous sector's finished
  framing. Captions and HUD stay in screen coordinates. Sector lookup also retains
  the preceding sector during small gaps between narration phrases, avoiding a
  momentary jump to the last sector.
- Captions retain the exact saved script tokens, in groups of up to five words.
  A pooled set of Pixi text objects wraps and centers these words in the fixed safe
  band at 72% of screen height. White text uses a 10 px centered dark stroke
  (approximately 5 px outside the letters); the active word uses `#f5c542`.
  Highlights end during longer pauses. Text textures only change when text or color
  changes rather than on every frame.
- Each moving formation gets one subtle dashed faction-colored centerline, drawn
  behind its icons. The line follows only the already-traveled route, including
  corners and contiguous split orders. It never draws an unreached destination or
  connects discontinuous routes. Trails fade in and disappear two seconds after a
  halt. Dash lengths and line thickness stay stable on screen during camera zoom.

`war_narration/words.py` is a separate offline contract/validation module. It imports
recognized word timestamps and aligns them to the saved script without rewriting
the narration. Small timestamp reversals up to 150 ms are smoothed in transcript
order; substantial disorder or less than 85% transcript agreement is rejected.
Unrecognized script words are interpolated between recognized anchors. Words remain
inside the measured phrase intervals. A local waveform/syllable estimate is also
available when no timestamp import is supplied; that fallback is approximate.

No additional dependency or automatic external transcription service was added.

## Inputs and outputs

The existing scene contract supplies director sectors, force identity, timed movement
routes and phrase captions. Optional caption-word imports contain:

- Exact narration waveform SHA-256, script SHA-256 and duration.
- Timing basis (`asr_word` or `local_estimate`) and transcript match fraction.
- Each phrase ID mapped to its original words with absolute start/end seconds.

Production validates the import against the current narration, copies it into the
immutable reviewed bundle as `caption-words.json`, and adds the cues to `scene.json`.
Review/export cache contexts include the timing-file content hash and narration
waveform hash. Replacing a timing file at the same path therefore invalidates the
review; stale cues from a different voice or script are rejected.

## Editing and usage

The existing workflow `caption` edit can patch **both** `visual_review` and `picture`
with these presentation settings:

```json
{
  "camera_push_in": 0.08,
  "movement_trails": true,
  "caption_stroke_px": 10,
  "caption_word_timing": "E:/path/to/word-timing.json"
}
```

Set `camera_push_in` to zero or `movement_trails` to false to disable either effect.
Omit `caption_word_timing` to use local estimates. Existing camera overrides still
control sector focus and base framing. A presentation-only edit reruns visual
review, picture export, mux and final review while reusing authored content and
audio. Picture export checks that its settings match those actually reviewed.

## Austerlitz verification

The user explicitly approved uploading generated narration audio to Groq for word
timestamps. The bounded live experiment used `whisper-large-v3`; the imported 234
script words achieved **97.01% transcript agreement**. A 100 ms timestamp reversal
was smoothed locally. The saved response is reused for local alignment rather than
uploading again. Groq received generated narration audio, not credentials, video,
or the project directory. Offline tests make no API requests.
The live check made two successful transcription requests and one HTTP 403 attempt;
the first successful response exposed the timestamp-order issue before raw-response
caching was added to the one-off experiment.

Five rendered sector samples passed the bounded visual review, using five model
attempts, zero search requests and zero TTS requests. Actual WebGL checks verify
gold word fill, stronger stroke, a fixed caption position, visible traveled trails,
post-halt fading and increasing camera scale during a stationary phase. Pure tests
cover sector gaps/transitions, disable controls, corners, discontinuous paths,
pause highlighting, line wrapping and deterministic seeking. Python tests cover
exact transcript preservation, timestamp jitter, invalid imports, stale bindings
and presentation-edit reuse.

**389 offline Python tests and 31 renderer/browser tests passed.** The full export
is **76.366667 seconds**, **1080 × 1920 H.264 at 30 fps**, with 48 kHz stereo AAC.
Complete FFmpeg decoding passed without reported errors. Picture export took
412.3 seconds and muxing took 3.1 seconds on the local renderer.

- [Full video](../output/austerlitz-presentation/final.mp4)
- [14-second movement/caption preview, seconds 47–61](../output/austerlitz-presentation/motion-preview.mp4)
- [Final encoded frame at 50 seconds](../output/austerlitz-presentation/final-50.png)
- [Media verification and artifact reuse audit](../output/austerlitz-presentation/verification.json)

Only visual review, picture, mux and final review changed. All 13 other stage
artifacts were reused, including narration, timing, unit designs, effects and the
music mix. Revision `8c86b67e30924b33ac5848c3a74d09ba` has no dirty stages or blocking
issues and is **awaiting_review**, with no human approval or publication.

## Limitations

ASR word timing is an estimate of spoken boundaries, not guaranteed forced
alignment. Words that differ from recognition use interpolated intervals. Caption
placement is fixed for predictable phone viewing, so it can overlap terrain
annotations. Trails describe authored schematic routes rather than independently
verified historical tracks. Still-image review does not replace motion, audio or
human editorial review. This revision remains subject to the existing human review
gate before publishing.
