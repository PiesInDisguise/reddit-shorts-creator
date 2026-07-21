# shorts-creator

A personal CLI tool that turns two kinds of source material into vertical (1080x1920) shorts:

- **`youtube`** — download a YouTube video and crop/trim it to shorts spec.
- **`reddit`** — turn a Reddit thread into a narrated "Reddit story" short: AI voiceover (title,
  then body), a subreddit header card, word-flash captions synced to the narration, and
  background gameplay-style filler footage.

## Setup

1. Python 3.12+ and [ffmpeg](https://ffmpeg.org/) (with `ffprobe`) on `PATH`. Verified against
   ffmpeg 8.1 (`qtrle`/`prores_ks`/`ffv1` alpha-capable encoders required — most full builds have
   these).
2. `python -m venv .venv` then `.venv\Scripts\pip install -r requirements.txt`.
3. `copy .env.example .env` and fill in:
   - `ELEVENLABS_API_KEY` — required for `reddit` mode.
   - `REDDIT_USER_AGENT` — required for `reddit` mode. Reddit's public JSON endpoints throttle
     (or outright block) requests without a descriptive User-Agent, e.g.
     `shortsbot/0.1 by u/yourname`. **Note:** Reddit has also been known to block requests from
     datacenter/cloud IP ranges outright (an HTML login-wall instead of JSON) regardless of
     User-Agent — this only affects hosted/cloud environments, not a normal home connection.
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
- Output files land in `output/`.

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

Covers crop-filter math, interval selection, caption word/chunk timing, and Reddit JSON parsing
(mocked network). The YouTube pipeline and caption-rendering pipeline have both been manually
smoke-tested end-to-end; the live Reddit-fetch path should be smoke-tested from your own machine
since Reddit may block requests from cloud/datacenter networks (see the User-Agent note above).
