import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class FFmpegError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: Path) -> dict:
    """Return {"width", "height", "duration"} for the first video stream, plus
    top-level "duration" from the format section as a fallback."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}:\n{result.stderr}")

    data = json.loads(result.stdout)
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if video_stream is None:
        raise FFmpegError(f"No video stream found in {path}")

    duration = video_stream.get("duration") or data.get("format", {}).get("duration")
    if duration is None:
        raise FFmpegError(f"Could not determine duration of {path}")

    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "duration": float(duration),
    }


def probe_audio_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {path}:\n{result.stderr}")
    data = json.loads(result.stdout)
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise FFmpegError(f"Could not determine duration of {path}")
    return float(duration)


def run_ffmpeg(args: list, overwrite: bool = True) -> None:
    """Run an ffmpeg command. `args` should not include the leading 'ffmpeg' or
    the '-y'/'-n' overwrite flag."""
    cmd = ["ffmpeg", "-y" if overwrite else "-n", "-hide_banner", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(
            f"ffmpeg command failed (exit {result.returncode}):\n"
            f"{' '.join(cmd)}\n\nstderr:\n{result.stderr}"
        )
