# Quiet music and editable audio projects

## Purpose

Add a very quiet background music layer while keeping narration and important effects
clear. Music is independently selectable, replaceable and removable. Revisions use
saved stems and settings without generating narration, effects or visual frames again.
The existing sound recipes remain the production defaults; the experimental sound
designer is not connected to this stage.

## Mix behavior

The default hierarchy is narration, prominent effects, then music. A selected track
is prepared near -20dBFS RMS, with at least 6dB sample-peak headroom. The music gain
defaults to -22dB relative to that source: approximately -42dBFS RMS before fades
and ducking. High-crest-factor tracks may prepare quieter to preserve their peaks.

Music fades in over two seconds and out over three seconds. Detected narration
reduces music by a further 10dB; strong effects reduce it by 6dB. The stronger
reduction wins. Soft narration can trigger additional attenuation targeting a 22dB
RMS margin beneath the voice. Attack/release smoothing avoids abrupt gain changes.
This is a signal-level detector and target margin, not a semantic speech model or a
guarantee at every instant during its attack. Effects retain their existing voice ducking.

The final combined mix scales down only when necessary for 1dB sample-peak headroom.
It does not boost the final music/mix to commercial loudness. All gains, fades,
thresholds, timing and ducking settings remain editable.

## Track sources

`MusicSource` accepts a local WAV, MP3, OGG, FLAC, M4A or AAC track. FFmpeg decodes
only the needed segment at 48kHz stereo. Source offset, optional looping and loop
crossfade are configurable. Non-looping short tracks fade before their actual end.
Choose restrained instrumental music: this stage does not detect vocals or judge taste.

A fixed, original ambient demonstration bed is also available. It contains slow
harmonic changes with no lead melody, percussion or vocals. It is not a neural music
generator or a new music service. The listening example uses this original material
imported as MP3, exercising the same file workflow as a replacement track. Its title,
attribution and original file hash are retained. No external music was downloaded.

## Independent components

- `music_models.py`: portable source selection and typed, bounded mix settings.
- `music_render.py`: original demo, track fitting, normalization and quiet mixing.
- `music.py`: preparation cache, portable bundle construction, editable project,
  effects-stage preservation and CLI.

The music source is prepared separately from the mix. A cache key includes source
content hash, offset, loop settings, video duration, sample rate and renderer version.
It excludes gain/fade/ducking controls, so those edits reuse the prepared WAV.
Numeric fields are canonicalized: saving and reloading JSON does not cause a cache
miss between equivalent `0` and `0.0` values. Cache hashes are checked; files and
metadata publish atomically. Corrupted entries fail explicitly.

## Files retained for editing

Each new output bundle contains:

- `music-config.json`: source, levels, fades, timeline placement and ducking controls.
- `music-original.*`: the imported original file, when used, copied byte-for-byte.
- `music-source.wav`: fitted, normalized source before mix controls.
- `music.wav`: the quiet, faded and ducked music stem.
- `sound-effects.wav`: the unchanged dry effects stem.
- `narration.wav`: original narration, when available, preserved byte-for-byte.
- `soundtrack.wav`: final mix for browser playback and export.
- `audio-project.json`: source identity, stem hashes, mix settings and parent version.
- `music-metrics.json`, `music-report.md`, and the portable map runtime.

Music gain, source offset, start/end, looping, fade lengths, enable/mute, voice/effects
levels and ducking can be edited independently. For a volume-only revision, change
`mix.music_gain_db` and rerun the stage. Setting `mix.enabled=false` removes music
from the mix while retaining its prepared source for later reuse.

Every build uses a new directory. Parent project hashes preserve the version chain;
the source audio and visuals remain intact. The manifest also retains prior mix
settings if a config file is edited. A full graphical timeline editor is not built
in this step; the saved project is its editable foundation.

The effects compiler now preserves the music project when effects or narration are
revised. It reuses the music source and recomputes ducking against the new stems.
Incomplete/failed music builds are marked unready, so the preview selector cannot
mistake them for complete videos. Source publishing/review status is restored only
after the audio mix succeeds.

## Usage

```powershell
python -m war_content.music output/content/SOUND-BUNDLE --config examples/music/quiet.json --video output/units/unit-animation.mp4
python -m war_content.play output/content/MUSIC-BUNDLE

# Edit MUSIC-BUNDLE/music-config.json, then make a new version:
python -m war_content.music output/content/MUSIC-BUNDLE --video output/units/unit-animation.mp4

# Replace narration while reusing the effects and prepared music:
python -m war_content.music output/content/MUSIC-BUNDLE --narration narration.wav
```

After installation, `war-music` is an equivalent entry point. For an imported track,
set `source.kind` to `file` and `source.path` to a path relative to the config file,
with an appropriate title/attribution. The saved bundle rewrites it to its portable
`music-original.*` path. Music can also be added to a visual-only bundle with a
silent effects stem.

Normal MP4 export already reads the final soundtrack. `--video` can instead attach
the new mix to a supplied matching render using video stream copy. This checks
duration; the caller supplies the correct cut. No map rendering is needed for that
operation.

## Verification and example

**256 offline Python tests and 20 JavaScript/browser tests pass.** Music tests cover
source/settings validation, deterministic demo generation, normalization, repeated
and short tracks, fade/trim/disable, voice/effects ducking, soft-voice margin, headroom,
portable imports, local/global cache reuse and corruption, narration preservation,
effects rebuilds retaining music, failed-build readiness and CLI/decoder error paths.

A real MP3 import produced a 24-second 1080×1920 H.264 preview with 48kHz stereo AAC.
Its video-stream hash matches the approved silent render exactly. Live browser
play/pause and seeking work, and a separate two-second normal-export smoke test
also contains the composed AAC soundtrack.
Its music stem measures about -44.95dBFS full-program RMS versus effects around
-28.54dBFS: music is roughly 16.4dB lower overall. The final peak is about -14.32dBFS,
with no master attenuation. The example has no narration; the voice-priority behavior
is tested with offline narration fixtures and should be heard with final TTS later.

A real volume-only revision from -22dB to -28dB reused the prepared imported source,
kept the effects stem and visual blueprint unchanged, and completed in about 6.35
seconds for this 24-second example. Track decoding was explicitly blocked during
that test. The previous project remained available.

Local outputs, ignored by Git:

- [Music preview](../output/content/7c03c63465cd4d0e898d1a7d292b0dc2/preview-with-music.mp4)
- [Editable config](../output/content/7c03c63465cd4d0e898d1a7d292b0dc2/music-config.json)
- [Audio project](../output/content/7c03c63465cd4d0e898d1a7d292b0dc2/audio-project.json)
- [Quieter revision report](../output/content/ae1b10bb32e04d24a8e7249fa8c9b9e8/music-report.md)

The preview is an illustrative animation/audio study, not a publishing-ready battle
reconstruction. Music style and its final balance remain listening-review decisions.
