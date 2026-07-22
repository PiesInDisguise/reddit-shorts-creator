# shorts-creator

A personal CLI tool that turns two kinds of source material into vertical (1080x1920) shorts:

- **`youtube`** — download a YouTube video, crop/trim it to shorts spec, and save it into
  `background_clips/`. This mode exists specifically to prepare filler footage (e.g. Minecraft
  parkour) for `reddit` mode to use — not to produce a final short on its own.
- **`reddit`** — turn a Reddit thread into a narrated "Reddit story" short: AI voiceover (title,
  then body) via [Chatterbox TTS](https://github.com/resemble-ai/chatterbox) running on a Modal
  cloud GPU, a subreddit header card, word-flash captions synced to the narration (via Whisper
  forced alignment on the generated audio), and background gameplay-style filler footage (from
  `background_clips/`, e.g. footage prepared via `youtube` mode above) plus a quiet background
  music bed. Saves the finished short to `output/`.

## Setup

1. Python 3.12+ and [ffmpeg](https://ffmpeg.org/) (with `ffprobe`) on `PATH`. Verified against
   ffmpeg 8.1 (`qtrle`/`prores_ks`/`ffv1` alpha-capable encoders required — most full builds have
   these).
2. `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.
3. A [Modal](https://modal.com) account, authenticated locally (`modal token set --token-id ...
   --token-secret ...` — get these from your Modal dashboard), then deploy the TTS app once with
   `modal deploy modal_tts_app.py`. This builds a Chatterbox TTS + faster-whisper image and deploys
   it to a Modal GPU (T4) function; `reddit` mode calls it remotely for every narration. Re-run
   `modal deploy` any time `modal_tts_app.py` changes.
4. `copy .env.example .env` and fill in:
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
5. Run `python main.py doctor` to verify everything above is in place.

## Usage

```
python main.py doctor

python main.py youtube <url> [--mode random|manual] [--start SS] [--end SS] [--out PATH]
python main.py reddit <url> [--out PATH]
```

- `youtube --mode random` (default) picks a random 60-second window from the source video.
  `--mode manual --start 10 --end 40` uses an explicit range (clamped to 60s max).
- `youtube` saves into `background_clips/` by default; pass `--out PATH` to save elsewhere instead.
- `reddit` saves the finished short into `output/`.

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
4. **TikTok / Instagram**: not implemented yet — `--platform tiktok|instagram` will raise a clear
   "pending API access" error. TikTok requires an app-review-approved Content Posting API app;
   Instagram's Graph API requires a public URL for the video file plus a Business/Creator account
   linked to a Facebook Page. Revisit once you've sorted access/hosting for either.

Always try `--dry-run` first to check the request payload without spending API quota, and upload
as `private`/`unlisted` before ever using `public`.

## Testing

```
.venv\Scripts\python -m unittest discover -s tests
```

Covers crop-filter math, interval selection, caption word/chunk timing, TTS alignment expansion,
and Reddit/Apify response parsing (mocked network). The YouTube pipeline, caption-rendering
pipeline, Apify fetch, and the Chatterbox/Whisper Modal round trip have all been manually
smoke-tested end-to-end.
