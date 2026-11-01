# Restore the working Instagram and TikTok upload flows

## Purpose

Correct the first connected Studio's publishing assumptions, preserve the user's
existing API workflow, and remove automatically added AI disclosure flags.

The user clarified that edition one publishes directly to YouTube and Instagram,
then sends TikTok uploads to the mobile inbox for review and manual posting.
The first Studio adapter incorrectly treated both Instagram login types as binary
upload clients and used TikTok Direct Post instead of the working inbox path.

## What changed

### No automatic AI labels

YouTube uploads omit `status.containsSyntheticMedia`, and TikTok Direct Post
payloads omit `is_aigc`. The UI no longer says labels are enabled. The normal TikTok
inbox request contains only `source_info`; it does not submit post metadata or
label flags. This changes future requests from this application; it does not
modify an existing YouTube post or control labels independently applied by a platform.

### Instagram Login uses the edition-one HTTPS staging path

A bounded validation request confirmed the failing Instagram call returned
**HTTP 400, code 100: `The parameter video_url is required`**. No container was
created by that validation, and no video was uploaded or published.

The adapter now distinguishes login types:

- Current Instagram Login tokens use `graph.instagram.com`. After explicit publishing
  confirmation, the MP4 is staged on **uguu.se**, the same primary temporary host as
  edition one. The resulting HTTPS `video_url` is supplied to Instagram. The
  publishing review explicitly discloses this staging transfer.
- Facebook Login tokens continue to use the direct resumable binary upload path.
  No new Facebook credentials or login migration are needed for the existing setup.

The staging request carries the video only, never the Instagram access token.
Returned URLs must be HTTPS on the Uguu domain; there are no silent host fallbacks.
Uguu currently documents a **128 MiB** file limit and **three-hour** expiration.
These are provider limits, not a promise of permanent storage.
See the [Uguu API](https://uguu.se/api), [hosting limits](https://uguu.se/), and
[Meta's official publishing collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api).

Instagram Login publishes the finished container through `me/media_publish`.
Processing is checked for up to about 60 seconds in the worker; pending results
keep their receipt for later status refresh instead of starting another upload.

### TikTok goes directly to the mobile inbox

The default is now `TIKTOK_PUBLISH_MODE=inbox`. Upload initialization uses
`/v2/post/publish/inbox/video/init/` with `FILE_UPLOAD`, then sends the MP4 bytes.
There is no preliminary Direct Post attempt and no requirement to select
`SELF_ONLY` for inbox delivery. The user's account privacy settings are unchanged.

`SEND_TO_USER_INBOX` becomes **Awaiting mobile review**, not Published. The user
opens TikTok's inbox notification, edits/reviews and posts in the mobile app.
Caption/title/hashtag drafts stay in Studio, with a copy button: the inbox API does
not submit them as post metadata. Later status refresh can reconcile completion.
See the [official TikTok upload API](https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video).

Direct Post remains opt-in through `TIKTOK_PUBLISH_MODE=direct`. Its audit/private
account restrictions are separate from inbox upload. The earlier 403 was produced
by this wrong publishing mode even though its payload already used `SELF_ONLY`.

### Receipts, retries and confirmation

The already-published YouTube receipt is retained and skipped on retries of the
failed Instagram/TikTok destinations. Inbox receipts also prevent repeat uploads.
A failed status read after upload preserves Processing rather than claiming a
fresh upload is safe. Interrupted temporary staging can be retried, while ambiguous
social upload/final-submit results remain protected as Uncertain.

Review tickets now include a publishing-policy version. Tickets made before these
flow changes must be reviewed again, so a stale confirmation cannot silently start
a newly introduced third-party staging transfer.

## Configuration and usage

At the user's explicit request, the external `.env` was copied into the project as
`.env`. Its contents were not displayed, and Git confirms the file is ignored.
The original file is preserved. No Facebook credentials were fabricated or required.
The restarted Studio uses this local file:

```powershell
.\.venv\Scripts\python.exe -m war_studio --port 8765 --env-file .env
```

Reload `http://127.0.0.1:8765`, open the video's Publish tab and review publishing
again to retry the failed platforms. The review should show Instagram temporary
hosting, TikTok inbox delivery, and YouTube in the skipped destinations.
Old failed receipts remain visible as previous attempts; their history is not erased.

## Verification

Regression tests cover absent AI-label flags, Instagram Login staging and URL
creation, staging failure before Meta requests, token isolation, TikTok inbox
payload/status handling, stale policy rejection, duplicate prevention and preserving
pending uploads after status-read failures. Browser checks cover inbox explanations,
caption copying and clipboard failures, with the former AI-label notice absent.

The live **non-publishing preflight passed** for the existing Austerlitz revision:
YouTube was skipped, Instagram selected temporary HTTPS hosting for `thewargrid`,
and TikTok selected inbox delivery for `The War Grid`. Preflight does not upload
to Uguu, upload media to TikTok, or publish a post. No failed destination was retried
externally during this correction.

**417 offline Python tests and 40 renderer/browser tests passed.** The local `.env`
was confirmed ignored by Git, and the uploader source contains neither automatic
AI-label field. The only occurrences of those field names in the new tests assert
that they are absent from outgoing payloads.

## Limits

The restored transport paths are covered offline and match the edition-one code;
actual media delivery still needs the user's next explicit publishing confirmation.
Temporary hosting can fail or expire. TikTok analytics permissions are independent
of successful inbox delivery. This correction does not alter the already-published
YouTube video, remove a platform-applied label, or change account privacy.
