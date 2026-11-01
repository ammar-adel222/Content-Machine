# Content Machine Studio: first UI

The subsequent [backend integration report](STUDIO_INTEGRATION_REPORT.md) describes
the connected workspace. The original UI-only mode documented below is now launched
with `--demo`; live project mode is the default.

## Purpose and scope

Studio is the user-facing workspace for creating videos, reviewing them, requesting
edits, preparing posts and exploring performance. This component implements the UI
first. Generation, publishing, account authorization and analytics ingestion are
deliberately not connected to live services yet.

The interface includes:

- An overview with optional topic entry, battle/war selection and portrait/landscape
  format selection. Blank topics represent researcher-selected stories.
- A searchable video library with ready, in-progress, published and draft filters.
- A video workspace with a portrait-first player, pipeline progress and separate
  Edit video, Publish and Activity panels.
- General, script/voice, map/units and sound/music edit instructions. Applying an
  edit saves the instruction and prior revision metadata, then simulates a new run.
- Independent YouTube, Instagram and TikTok titles, descriptions/captions and
  hashtags, with platform selection and a final publishing-details dialog.
- Analytics filters for platform, individual video and 7/30/90-day periods; views,
  likes, shares, engagement rate, illustrative trends, channel breakdowns and a
  per-video performance table.
- A publishing queue and platform-connection placeholders.

## Architecture

The frontend lives in `war_studio/web/`. It uses plain HTML, CSS and JavaScript
modules, with no frontend build tool, framework, remote font or added dependency.

`state.mjs` holds the UI data, demo analytics, validation, project creation, edit
history and elapsed-time progress functions. `studio.mjs` renders the screens and
handles interactions. The CSS provides responsive desktop, tablet and phone
layouts. Portrait preview is prioritized; landscape selection is supported.

The current launch command uses a small standard-library HTTP server solely for
static UI files and two optional mounted media files. It is **not the production
backend**. The planned FastAPI service will connect this interface to LangGraph,
the saved project store, publishing adapters and analytics APIs in the next phase.
Agent code and existing saved contracts have not been changed.

The server binds to loopback only. It exposes an explicit file allowlist rather
than the workspace directory. MP4 byte ranges support video seeking. Missing
media shows a friendly fallback. The server does not read `.env`, load API keys,
start a model request or expose project files.

## State, inputs and outputs

The browser stores demo projects, per-platform metadata, selected publishing
targets, draft edit text and revision metadata in `localStorage` under
`content-machine-studio-v1`. Valid saved state survives refreshes. Corrupt or
structurally invalid state falls back to the seeded demo workspace. Storage
failures show a notice rather than claiming that changes were saved.

A demo run takes approximately 15.4 seconds and advances through Research,
Writing, Script review, Battle direction, Visuals & audio, Rendering and Final
review. Its start timestamp is saved, so reopening the page updates simulated
progress by elapsed time. This is a UI simulation, **not a durable worker**.

Demo edits store instructions and history; they do not render changed media.
Revision history is metadata only, not an implementation of media version storage.
The existing Austerlitz sample can be played and downloaded locally when present.
Other sample projects illustrate empty/player states.

Publishing metadata is kept separately for all three platforms. The Publish video
button opens a review dialog; its final submission button is unavailable until
integrations exist. It never changes a project to published or posts externally.
The seeded published project and all analytics values are clearly marked as demo
data. Analytics filters operate on these fixtures, not the user's accounts; the
trend curve is illustrative rather than an observed time series.

## Usage

From the project directory:

```powershell
.\.venv\Scripts\python.exe -m war_studio --demo --open
```

Open `http://127.0.0.1:8765`. Optional media and port overrides:

```powershell
.\.venv\Scripts\python.exe -m war_studio --port 8765 `
  --video "E:\path\to\final.mp4" --poster "E:\path\to\frame.png"
```

By default the launcher uses `output/austerlitz-presentation/final.mp4` and
`final-50.png` when available. Without them, the rest of the UI still works.
`war-studio` is also declared as a console entry point for subsequent installs.
Static assets are included in package data.

## Verification

**392 offline Python tests and 38 renderer/browser tests passed.**

New Python tests cover static/media serving, GET/HEAD, video byte ranges, invalid
ranges, missing media, traversal and unrelated-file rejection, invalid command
options and server cleanup. New JavaScript tests cover state recovery, input
validation, optional topics, both formats, elapsed-time progress, revision
preservation, overlapping-run rejection, library filters and analytics totals.

Browser tests exercise generation and completion, refresh persistence, scoped
edits, platform-specific metadata, publishing review, selecting no platforms,
analytics filtering, search empty states, corrupt/unavailable storage, missing media, cancelling
a demo run and phone layouts. No external requests or browser exceptions occurred
in the main end-to-end flow. User-entered markup remains literal text.

Desktop overview, workspace, publishing and analytics screens, plus the phone
layout, were captured and visually inspected. The existing local Austerlitz MP4
loaded in the preview. No live APIs were used for testing.

## Next integration boundary and limitations

Replace demo state with the FastAPI project/job API, and replace simulated progress
with durable LangGraph job status. Keep the saved-contract project store as the
source of truth. Edits should become targeted revisions rather than frontend-only
history. Publishing needs authenticated accounts, platform-specific validation,
per-platform receipts and retries that avoid duplicate posts. Analytics needs
platform adapters and metric definitions before presenting cross-platform totals
as real performance.

There is no authentication, scheduling, multi-user synchronization, live pipeline
execution or platform connectivity in this component. Clearing browser storage
removes UI demo drafts. Production credentials must remain on the future backend.
