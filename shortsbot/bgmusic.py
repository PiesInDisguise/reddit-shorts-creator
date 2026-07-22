from pathlib import Path

import yt_dlp

MUSIC_URL = "https://www.youtube.com/watch?v=yyjUmv1gJEg"
MUSIC_ASSET_PATH = Path("assets") / "music" / "background.mp3"


def ensure_background_music(asset_path: Path = MUSIC_ASSET_PATH, url: str = MUSIC_URL) -> Path:
    """Return the cached background-music track, downloading just the audio
    via yt-dlp on first use. Drop your own file at this path to replace it."""
    if asset_path.exists():
        return asset_path

    asset_path.parent.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(asset_path.with_suffix("")) + ".%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not asset_path.exists():
        candidates = list(asset_path.parent.glob(asset_path.stem + ".*"))
        if not candidates:
            raise FileNotFoundError(f"yt-dlp did not produce an audio file at {asset_path}")
        candidates[0].rename(asset_path)

    return asset_path
