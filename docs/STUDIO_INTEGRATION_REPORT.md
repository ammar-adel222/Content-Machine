# Studio backend, workflow jobs and platform integrations

The subsequent [publishing corrections report](PUBLISHING_CORRECTIONS_REPORT.md)
supersedes the initial upload-mode assumptions below: the current Instagram Login
uses the edition-one temporary HTTPS staging flow, TikTok defaults to mobile inbox
delivery, and automatic AI-label flags are omitted. The project now uses the
user-requested local, Git-ignored `.env` copy.

## Purpose

The Studio now uses real saved projects, LangGraph jobs and platform API adapters.
Demo mode remains isolated and optional. The main workspace no longer substitutes
demo analytics or simulated progress for backend data.

## Architecture

- `war_studio/api.py`: loopback FastAPI routes, static UI, project/video access,
  metadata storage, job submission, account verification and publishing review.
- `service.py`: translates UI requests into the existing `ProjectStore`, immutable
  revisions and targeted edit contracts. Large media are hash-checked before
  serving or publishing, not on every progress poll.
- `database.py`: separate SQLite storage for jobs, post drafts, upload receipts,
  account checks, backend token caches and analytics snapshots. Agent contracts
  remain in the existing project databases.
- `worker.py`: a detached subprocess drains the persistent queue. One OS file lock
  prevents competing Studio workers. The existing per-project lock also protects
  the graph. Worker heartbeats support recovery after process loss. Completed
  stage receipts are reused when generation is resumed.
- `platforms.py`: injectable HTTP transport for official YouTube, Instagram and
  TikTok authentication, uploading, post status and analytics calls.
- `web/backend.mjs`: same-origin transport and serialized metadata writes. The UI
  polls saved status roughly every 2.5 seconds and debounces post-draft saves.

The backend adds FastAPI, Uvicorn and HTTPX through the optional `studio` extra.
No frontend build framework or platform SDK is required.

## Generation and editing

Generate video creates a real project and queues its workflow. A blank topic uses
the existing research discovery mode; battle/war scope, format and target length
are saved in the contracts. Progress reflects actual stage receipts and worker
activity. Refreshing or closing the browser does not cancel the detached worker.
Stopping generation is cooperative: it stops at the next adapter boundary.

The library reads existing projects, including the completed Austerlitz revision.
The player streams the current revision through a hash-checked media endpoint with
byte-range support. Changed render artifact IDs invalidate the player URL.

Edits carry the exact parent revision and a request ID. Stale edits are rejected.
The user chooses the edit target rather than having arbitrary prose silently routed
to an unrelated agent. Research, writing, narration and direction accept their
existing note contracts. Deterministic audio/camera/caption stages require explicit
settings: common music/narration/effect levels have numeric controls, with advanced
JSON for other saved-contract settings. The description is retained in Activity
without passing unsupported prose to those adapters. Unaffected artifacts are reused.

**Terrain limitation:** a new tactical battlefield still requires a checked source
bundle and geographic binding for its actual director blueprint. The default battle
mode stops with that requirement rather than claiming schematic terrain is measured.
The user can explicitly choose illustrative schematic mode. This integration does
not establish unattended reproduction of Austerlitz's editorial/terrain quality.

## Publishing

Post titles, captions/descriptions, hashtags and platform selections are saved on
the backend, independently for YouTube, Instagram and TikTok. Visibility and TikTok
interaction controls are shown explicitly. No upload happens when verifying an
account, editing metadata or opening the publishing review.

Preparing a post checks the finished revision, current accounts, supported metadata
lengths, TikTok privacy/duration/interaction limits and the exact video hash. A
10-minute review ticket binds these inputs. The final **Approve & publish** action
queues publishing; the worker rechecks those bindings and approves the exact saved
video through the existing LangGraph human-review gate before sending it.

YouTube uses resumable binary upload. Instagram creates a resumable Reels container,
uploads directly to Meta, checks processing and submits that container. TikTok uses
direct-post file upload and post-status polling. No temporary third-party file hosts
are used. Returned upload destinations are restricted to the relevant official hosts.
See the official [YouTube insert API](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert),
[Meta sample](https://github.com/fbsamples/reels_publishing_apis/blob/main/insta_reels_publishing_api_sample/README.md)
and [TikTok Direct Post API](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post).

Each revision/platform has its own receipt. A successful or processing receipt is
not uploaded again when another platform fails. Confirmation double-clicks return
the same queued job. Ambiguous network/remote errors are marked `uncertain`; they
are not blindly retried. Refresh post status & analytics reconciles processing
containers. Unknown results need remote inspection rather than a duplicate post.

TikTok defaults to sandbox/private-only controls (`SELF_ONLY`). Set the backend
`TIKTOK_APP_MODE=production` only after the app's actual approval/configuration allows
it. Runtime choices still come from the creator-info API. YouTube visibility defaults
to private and can be explicitly changed in the UI. Synthetic-media labels are set
for YouTube and TikTok.

## Analytics

Refresh analytics reads bounded sets of the account's recent posts: up to 50 YouTube,
25 Instagram and 20 TikTok posts per sync. Posts created before this system appear
as external videos with their own IDs. New publishing receipts link future posts to
the local video project. Per-platform and per-video filters operate on real snapshots.

This release presents **latest lifetime snapshots**, not fabricated 7/30/90-day
reports. Date-range selectors and the demo trend curve are removed in live mode.
Views have platform-specific definitions. Missing metrics remain `null`/`—`; totals
sum available counters and engagement is withheld when required counters are missing.
YouTube Analytics reports are attempted when permissions allow, otherwise its Data
API counters remain available. Instagram insights may also be permission-dependent.

TikTok verified the posting account, but its video-list call returned HTTP 401
`scope_not_authorized`. The user confirmed the app is still a sandbox and registration
is in progress. TikTok analytics stays visibly unavailable pending app/permission
approval; no demo values replace it. Public Terms/Privacy pages and URL ownership
verification are separate app-review requirements, not something localhost provides.
See [TikTok app registration](https://developers.tiktok.com/docs/en/getting-started-create-an-app)
and [review guidelines](https://developers.tiktok.com/docs/en/app-review-guidelines).

## Credentials and local access

The supplied external `.env` is loaded at runtime and is not modified or committed.
OAuth access/rotated refresh tokens are cached in the ignored local Studio SQLite
database so refreshes survive restarts. That database contains private backend data;
it is not a browser-accessible asset or a repository artifact.

The HTTP server binds to loopback, checks local host/origin, requires a per-server
request nonce for mutations and exposes only explicit static/media routes. The
frontend receives account identities and sanitized errors, never provider credentials,
OAuth responses, signed upload sessions or arbitrary filesystem paths. This is a
single-user local application, not an authenticated public deployment.

## Usage

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[studio,workflow,geography]"
.\.venv\Scripts\python.exe -m war_studio --port 8765 `
  --env-file "E:\AI matirial\content machine\war-tactics-agent\.env"
```

Open `http://127.0.0.1:8765`. Optional `--projects` and `--data` select isolated
project/Studio stores. Use `--demo` for the original offline UI demonstration.
Node/Playwright and FFmpeg remain the existing rendering prerequisites.

## Verification and practical limits

**411 offline Python tests and 40 renderer/browser tests passed.** New tests cover
local API protection, saved project/video access, byte ranges, queued generation,
cancel/resume boundaries, metadata persistence, revision conflicts, structured audio
edits, token rotation, upload-host restrictions, direct upload protocols, sandbox
visibility, stale/expired confirmation tickets, duplicate confirmation, partial
publication failure, uncertain outcomes and worker recovery/redaction. Browser tests
cover both connected and isolated demo modes, saved post details, explicit consent,
numeric audio controls, unavailable metrics and backend outages without demo fallback.

Read-only live checks verified **The War Grid** on YouTube and TikTok and **thewargrid**
on Instagram. YouTube and Instagram analytics returned 16 total post snapshots in
this check. TikTok's analytics permission failure was recorded separately. No live
upload or publication was attempted.

A real API-to-worker smoke test used an isolated saved-contract copy of Austerlitz.
It lowered music gain by 1 dB and completed `mix`, `audio_review`, `mux` and
`final_review`; all 13 other stage artifacts, including picture and narration, were
unchanged. Model/search/TTS budgets were all set to zero and all usage stayed zero.
The output reached `awaiting_review`, with no approval. Its 76.366667-second,
1080 × 1920 video streamed successfully with HTTP 206 byte ranges. The original
project remained at revision `8c86b67e30924b33ac5848c3a74d09ba`, unchanged and unpublished.
The local proof is [saved here](../output/studio-connected-smoke.json).

The connected UI was inspected in a real browser, loaded the saved full-resolution
video and showed no JavaScript exceptions. Desktop and phone layout checks passed.

Live publishing is implemented but deliberately not externally tested by posting to
the user's accounts. Platform review, quotas and token permissions can still reject
an upload. TikTok file uploads are currently limited to 64 MB. Reconciliation is
user-triggered rather than a perpetual polling service. Account OAuth onboarding,
full historical pagination/date reports, public hosting/legal pages and production
multi-user access remain separate work.
