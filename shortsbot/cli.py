import argparse
import sys
from pathlib import Path

from config import ConfigError, Settings

from . import reddit_pipeline, video_utils, youtube_pipeline
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

    if settings.reddit_user_agent and "<your_reddit_username>" not in settings.reddit_user_agent:
        print("[ok] REDDIT_USER_AGENT is set")
    else:
        print("[FAIL] REDDIT_USER_AGENT is not set (or still the placeholder) (required for reddit mode)")
        ok = False

    if settings.reddit_client_id and settings.reddit_client_secret:
        print("[ok] REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are set")
    else:
        print(
            "[FAIL] REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not set (required for reddit "
            "mode - create a free 'script' app at https://www.reddit.com/prefs/apps)"
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
    out_path = Path(args.out) if args.out else None

    out = youtube_pipeline.run(
        args.url,
        mode=args.mode,
        start=start,
        end=end,
        out_path=out_path,
        keep_work=args.keep_work,
    )
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


UPLOADERS = {
    "youtube": lambda s: YouTubeUploader(s.youtube_client_secrets_file, s.youtube_token_file),
    "tiktok": lambda s: TikTokUploader(),
    "instagram": lambda s: InstagramUploader(),
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
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shortsbot")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Verify environment setup")
    sub.add_parser("gui", help="Launch the desktop GUI")

    p_youtube = sub.add_parser("youtube", help="Download and crop a YouTube video to shorts spec")
    p_youtube.add_argument("url")
    p_youtube.add_argument("--mode", choices=["random", "manual"], default="random")
    p_youtube.add_argument("--start")
    p_youtube.add_argument("--end")
    p_youtube.add_argument("--out")
    p_youtube.add_argument("--keep-work", action="store_true")

    p_reddit = sub.add_parser("reddit", help="Turn a Reddit thread into a narrated short")
    p_reddit.add_argument("url")
    p_reddit.add_argument("--voice-id")
    p_reddit.add_argument("--out")
    p_reddit.add_argument("--keep-work", action="store_true")

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
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings.load()

    handlers = {
        "gui": cmd_gui,
        "doctor": cmd_doctor,
        "youtube": cmd_youtube,
        "reddit": cmd_reddit,
        "upload": cmd_upload,
    }

    try:
        return handlers[args.command](args, settings)
    except (ConfigError, NotConfiguredError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
