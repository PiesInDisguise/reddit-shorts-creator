# shorts-creator

A personal CLI tool that turns two kinds of source material into vertical (1080x1920) shorts:

- **`youtube`** — download a YouTube video, crop/trim it to shorts spec, and save it into
  `background_clips/`. This mode exists specifically to prepare filler footage (e.g. Minecraft
  parkour) for `reddit` mode to use — not to produce a final short on its own.
- **`reddit`** — turn a Reddit thread into a narrated "Reddit story" short: AI voiceover (title,
  then body) via ElevenLabs, a subreddit header card, word-flash captions synced to the narration
  (via ElevenLabs' own word-timestamp alignment), and background gameplay-style filler footage
  (from `background_clips/`, e.g. footage prepared via `youtube` mode above) plus a quiet
  background music bed. Saves the finished short to `output/`.

## Setup

1. Python 3.12+ and [ffmpeg](https://ffmpeg.org/) (with `ffprobe`) on `PATH`. Verified against
   ffmpeg 8.1 (`qtrle`/`prores_ks`/`ffv1` alpha-capable encoders required — most full builds have
   these).
2. `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.
3. `copy .env.example .env` and fill in:
   - `ELEVENLABS_API_KEY` — required for `reddit` mode.
   - `APIFY_API_TOKEN` — required for `reddit` mode. Reddit hard-blocks anonymous scraping of its
     public `.json` endpoints from most networks (confirmed 403 even with a legitimate User-Agent
     and full browser-style headers — this is IP/TLS-fingerprint-level bot detection, not
     something fixable by tweaking request headers). This tool instead fetches posts through the
     Apify [`Reddit Scraper Lite`](https://console.apify.com/actors/oAuCIx3ItNrs2okjQ) actor
     (pay-per-result, runs through Apify's own proxy infrastructure). Get a token from
     <https://console.apify.com/settings/integrations> and put it in `.env`.
   - `BACKGROUND_CLIPS_DIR` — a folder of your own gameplay-style filler clips (e.g. Minecraft
     parkour) for `reddit` mode. At least one video file is required.
   - `IMPACT_FONT_PATH` — defaults to `C:\Windows\Fonts\impact.ttf` (already present on Windows).
4. Run `python main.py doctor` to verify everything above is in place.

## Usage

```
python main.py doctor

python main.py youtube <url> [--mode random|manual] [--start SS] [--end SS] [--out PATH]
python main.py reddit <url> [--voice-id ID] [--out PATH]
```

- `youtube --mode random` (default) picks a random 60-second window from the source video.
  `--mode manual --start 10 --end 40` uses an explicit range (clamped to 60s max).
- `youtube` saves into `background_clips/` by default; pass `--out PATH` to save elsewhere instead.
- `reddit` saves the finished short into `output/`. `--voice-id` picks an ElevenLabs voice; without
  it, the first entry in `voices.json` is used. `voices.json` is a simple saved list of voice IDs
  (seeded with two defaults on first run) — the GUI's Reddit tab has a dropdown to switch between
  saved voices and a "+ Add" button to save a new voice ID into that list for next time.

### Uploading

Uploading is off by default and separate from generation — it never runs automatically after
`youtube`/`reddit`.

```
python main.py upload <video_path> --platform youtube --title "..." [--description ...] [--tags a,b,c] [--privacy private] [--dry-run]
```

1. Set `ENABLE_UPLOAD=true` in `.env`.
2. `pip install -r requirements-upload.txt`.
3. **YouTube**: create an OAuth client (Desktop app) in Google Cloud Console, enable the
   YouTube Data API v3, download the client secret JSON to
   `.secrets/youtube_client_secret.json` (path configurable via `YOUTUBE_CLIENT_SECRETS_FILE`).
   First run opens a browser for one-time consent; the refresh token is cached at
   `.secrets/youtube_token.json`.
4. **TikTok**: create an app at <https://developers.tiktok.com> with Content Posting API access,
   set `TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET` in `.env` (register `TIKTOK_REDIRECT_URI`,
   default `http://localhost:8081/callback`, as the app's redirect URI). First run opens a browser
   for one-time consent; the token is cached at `.secrets/tiktok_token.json` and auto-refreshed
   after that. Note: unaudited apps are restricted by TikTok to `SELF_ONLY` privacy and/or posting
   to the creator's draft inbox rather than direct publish — that's a TikTok-side review
   requirement, not something this code controls.
5. **Instagram**: needs a Business/Creator IG account linked to a Facebook Page, and a long-lived
   access token with the `instagram_content_publish` permission (Meta App Review required beyond
   your own linked test account) — set `IG_ACCESS_TOKEN`/`IG_BUSINESS_ACCOUNT_ID` in `.env`.
   Instagram's Graph API needs a public URL for the video rather than a direct upload, so this
   spins up a temporary local server tunneled through [ngrok](https://ngrok.com) (`pip install`s
   `pyngrok` from `requirements-upload.txt`); set `NGROK_AUTH_TOKEN` (free account) for a
   stable tunnel. Instagram has no per-post privacy field — published Reels follow the account's
   own privacy setting regardless of `--privacy`.

Always try `--dry-run` first to check the request payload without spending API quota/credentials,
and upload as `private`/`unlisted` before ever using `public`.

## Testing

```
.venv\Scripts\python -m unittest discover -s tests
```

Covers crop-filter math, interval selection, caption word/chunk timing, ElevenLabs TTS request/
response handling, the saved-voices list, and Reddit/Apify response parsing (all with mocked
network). The YouTube pipeline, caption-rendering pipeline, Apify fetch, and a real ElevenLabs
synthesize() call have all been manually smoke-tested end-to-end.
