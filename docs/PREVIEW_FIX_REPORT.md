# Map preview fix

## Problem

The screenshot showed `war_content/web/index.html` opened with a `file:` URL. This is
the source player template, which has neither the generated scene nor a local PixiJS
runtime beside it. Browser restrictions also block ES module loading from this location.
The previous module-only startup could not display its own error, leaving a blank screen
with controls that appeared usable.

## Change

- Added `preview.cmd` at the project root. Double-click it to start the preview and
  open the latest ready generated map. Keep its console open; Ctrl+C stops the server.
- Added `python -m war_content.play [BUILD_DIRECTORY]` and the installed `war-preview`
  command. Without a directory, the launcher finds the most recently modified ready
  build under `output/content`, skipping failed/incomplete builds.
- The server binds only to `127.0.0.1` and chooses an available port automatically.
  It serves the selected scene/runtime and the current player files through an explicit
  allowlist. It does not expose the whole repository or build metadata directory.
- Added classic-script startup that also runs when the HTML is opened from disk.
  Direct-file visits now explain how to launch the preview. Missing runtime, player
  module or scene also produces a visible error. Play/seeking stay disabled until
  the renderer successfully loads.
- New generated bundles include the startup script. Existing bundles work through
  the launcher because it serves the current player with the saved scene.

No API calls, new visuals or model changes are required to preview an existing map.
The selected example is the earlier ready Falklands engine demonstration; the launcher
does not relabel an incomplete Qwen build as ready.

## Usage

```powershell
# Easiest: double-click preview.cmd, or run it from the project root.
.\preview.cmd

python -m war_content.play
python -m war_content.play output/content/THE-BUILD
python -m war_content.play --port 8000 --no-browser
```

`--root DIRECTORY` changes the automatic selection directory. The preview prints its
URL and selected build path. Direct-file visits show instructions because playback
requires the local server and a generated scene.

## Verification

**209 Python tests and 7 JavaScript/browser tests pass.** New tests cover ready-build
selection, incomplete/broken inputs, HTTP file allowlisting, browser launch options,
server errors, direct-file error guidance, missing resources and disabled controls.
Existing real PixiJS rendering, motion and backward-seeking checks also pass.

A running preview was verified in headless Chromium: ready=true, topic=Falklands War,
three forces and three terrain features. A frame at 45 seconds was captured in
`output/map-preview-working.png` (local, ignored by Git).
