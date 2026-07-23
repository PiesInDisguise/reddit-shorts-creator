import argparse
import sys
import time
from pathlib import Path

from config import ConfigError, Settings

from . import autopicker, reddit_pipeline, uploaded_videos, used_posts, video_utils, youtube_pipeline
from .ffmpeg_utils import ffmpeg_available
from .upload.base import NotConfiguredError, Uploader
from .upload.instagram_upload import InstagramUploader
from .upload.tiktok_upload import TikTokUploader
from .upload.youtube_upload import YouTubeUploader


def cmd_gui(args, settings: Settings) -> int:
    from .gui import launch

    launch()
    return 0


def cmd_doctor(args, settings: Settings) -> int:
    ok = True

    if ffmpeg_available():
        print("[ok] ffmpeg/ffprobe found on PATH")
    else:
        print("[FAIL] ffmpeg/ffprobe not found on PATH")
        ok = False

    if settings.impact_font_path.exists():
        print(f"[ok] Impact font found at {settings.impact_font_path}")
    else:
        print(f"[FAIL] Impact font not found at {settings.impact_font_path}")
        ok = False

    if settings.elevenlabs_api_key:
        print("[ok] ELEVENLABS_API_KEY is set")
    else:
        print("[FAIL] ELEVENLABS_API_KEY is not set (required for reddit mode)")
        ok = False

    if settings.apify_api_token:
        print("[ok] APIFY_API_TOKEN is set")
    else:
        print(
            "[FAIL] APIFY_API_TOKEN is not set (required for reddit mode - get one from "
            "https://console.apify.com/settings/integrations)"
        )
        ok = False

    clips_dir = settings.background_clips_dir
    if clips_dir.exists():
        clips = [
            p for p in clips_dir.iterdir() if p.suffix.lower() in video_utils.VIDEO_EXTENSIONS
        ]
        if clips:
            print(f"[ok] {len(clips)} background clip(s) found in {clips_dir}")
        else:
            print(f"[FAIL] No background clips found in {clips_dir} (required for reddit mode)")
            ok = False
    else:
        print(f"[FAIL] Background clips folder does not exist: {clips_dir}")
        ok = False

    return 0 if ok else 1


def cmd_youtube(args, settings: Settings) -> int:
    start = video_utils.parse_timestamp(args.start) if args.start else None
    end = video_utils.parse_timestamp(args.end) if args.end else None

    # youtube mode exists to prepare background filler footage, so that's
    # where clips land by default (with a descriptive filename); pass --out
    # to save somewhere else with an exact name instead.
    out_path = Path(args.out) if args.out else None
    out_dir = None if args.out else settings.background_clips_dir

    out = youtube_pipeline.run(
        args.url,
        mode=args.mode,
        start=start,
        end=end,
        out_path=out_path,
        out_dir=out_dir,
        keep_work=args.keep_work,
    )
    print(f"Wrote {out}")
    return 0


def cmd_giga_sample(args, settings: Settings) -> int:
    start = video_utils.parse_timestamp(args.start) if args.start else None
    end = video_utils.parse_timestamp(args.end) if args.end else None
    out_dir = Path(args.out_dir) if args.out_dir else settings.background_clips_dir

    outs = youtube_pipeline.run_giga_sample(
        args.url,
        count=args.count,
        start=start,
        end=end,
        clip_length=args.clip_length,
        out_dir=out_dir,
        keep_work=args.keep_work,
    )
    for out in outs:
        print(f"Wrote {out}")
    return 0


def cmd_reddit(args, settings: Settings) -> int:
    out_path = Path(args.out) if args.out else None
    out = reddit_pipeline.run(
        args.url,
        settings,
        voice_id=args.voice_id,
        out_path=out_path,
        keep_work=args.keep_work,
    )
    print(f"Wrote {out}")
    return 0


def cmd_auto_loop(args, settings: Settings) -> int:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")
    settings.require_elevenlabs()
    settings.require_apify()
    settings.require_upload_enabled()

    uploader = UPLOADERS["youtube"](settings)
    icon_cache_dir = Path("cache") / "subreddit_icons"

    print(f"Starting auto-loop on r/{args.subreddit} every {args.interval_seconds}s. Ctrl+C to stop.")
    while True:
        cycle_start = time.time()
        try:
            post = autopicker.pick_post(args.subreddit, settings.apify_api_token, icon_cache_dir)
            if post is None:
                print("No usable post found this cycle (all candidates used or too long), skipping.")
            else:
                print(f"Picked post {post.post_id!r}: {post.title!r}")
                out_path = reddit_pipeline.render_post(post, settings)
                print(f"Rendered {out_path}")
                result = uploader.upload(
                    out_path,
                    title=post.title,
                    description=reddit_pipeline.build_hashtags(post.subreddit),
                    privacy="public",
                )
                print(f"Uploaded to {result.platform}: {result.url}")
                uploaded_videos.record_upload(
                    out_path.name, result.platform, result.video_id, result.url
                )
                used_posts.mark_used(post.post_id)
        except Exception as exc:
            print(f"Error during auto-loop cycle: {exc}", file=sys.stderr)

        elapsed = time.time() - cycle_start
        remaining = args.interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)


UPLOADERS = {
    "youtube": lambda s: YouTubeUploader(s.youtube_client_secrets_file, s.youtube_token_file),
    "tiktok": lambda s: TikTokUploader(
        s.tiktok_client_key, s.tiktok_client_secret, s.tiktok_token_file, s.tiktok_redirect_uri
    ),
    "instagram": lambda s: InstagramUploader(
        s.ig_access_token, s.ig_business_account_id, s.ngrok_auth_token
    ),
}


def cmd_upload(args, settings: Settings) -> int:
    if not args.dry_run:
        settings.require_upload_enabled()

    uploader: Uploader = UPLOADERS[args.platform](settings)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    result = uploader.upload(
        Path(args.video_path),
        title=args.title,
        description=args.description or "",
        tags=tags,
        privacy=args.privacy,
        dry_run=args.dry_run,
    )

    if result.dry_run:
        print("[dry run] Would upload with payload:")
        print(result.payload)
    else:
        print(f"Uploaded to {result.platform}: {result.url}")
        uploaded_videos.record_upload(
            Path(args.video_path).name, result.platform, result.video_id, result.url
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shortsbot")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Verify environment setup")
    sub.add_parser("gui", help="Launch the desktop GUI")

    p_youtube = sub.add_parser(
        "youtube",
        help="Download and crop a YouTube video into background_clips/ (pass --out to save elsewhere)",
    )
    p_youtube.add_argument("url")
    p_youtube.add_argument("--mode", choices=["random", "manual"], default="random")
    p_youtube.add_argument("--start")
    p_youtube.add_argument("--end")
    p_youtube.add_argument("--out")
    p_youtube.add_argument("--keep-work", action="store_true")

    p_giga = sub.add_parser(
        "giga-sample",
        help="Cut N spread-out background clips from one YouTube video into background_clips/",
    )
    p_giga.add_argument("url")
    p_giga.add_argument("--count", type=int, required=True)
    p_giga.add_argument("--start")
    p_giga.add_argument("--end")
    p_giga.add_argument("--clip-length", type=float, default=180.0)
    p_giga.add_argument("--out-dir")
    p_giga.add_argument("--keep-work", action="store_true")

    p_reddit = sub.add_parser("reddit", help="Turn a Reddit thread into a narrated short")
    p_reddit.add_argument("url")
    p_reddit.add_argument("--voice-id", help="ElevenLabs voice ID (defaults to the first saved voice)")
    p_reddit.add_argument("--out")
    p_reddit.add_argument("--keep-work", action="store_true")

    p_auto = sub.add_parser(
        "auto-loop",
        help="Continuously pick, generate, and upload shorts from a subreddit forever",
    )
    p_auto.add_argument("--subreddit", default="copypasta")
    p_auto.add_argument("--interval-seconds", type=float, default=3600.0)

    p_upload = sub.add_parser("upload", help="Upload a finished short to a platform")
    p_upload.add_argument("video_path")
    p_upload.add_argument("--platform", choices=["youtube", "tiktok", "instagram"], required=True)
    p_upload.add_argument("--title", required=True)
    p_upload.add_argument("--description")
    p_upload.add_argument("--tags")
    p_upload.add_argument("--privacy", choices=["public", "private", "unlisted"], default="private")
    p_upload.add_argument("--dry-run", action="store_true")

    return parser


def main() -> int:
    # Post titles can contain characters (emoji, etc.) the Windows console's
    # active codepage can't render; without this, printing one crashes the
    # whole process (fatal for auto-loop, which needs to keep running for
    # days unattended) instead of just showing "?" for that character.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.load()

    handlers = {
        "gui": cmd_gui,
        "doctor": cmd_doctor,
        "youtube": cmd_youtube,
        "giga-sample": cmd_giga_sample,
        "reddit": cmd_reddit,
        "upload": cmd_upload,
        "auto-loop": cmd_auto_loop,
    }

    try:
        return handlers[args.command](args, settings)
    except (ConfigError, NotConfiguredError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
