import random
import re
from pathlib import Path
from typing import List, Optional, Tuple

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_AR = TARGET_WIDTH / TARGET_HEIGHT  # 9/16 = 0.5625
AR_TOLERANCE = 0.01

MAX_CLIP_SECONDS = 60.0

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _round_to_even(value: float) -> int:
    n = int(round(value))
    return n - 1 if n % 2 else n


def build_crop_filter(src_w: int, src_h: int) -> str:
    """Return an ffmpeg -vf filter string that conforms src_w x src_h to the
    1080x1920 shorts frame: skip cropping if already ~9:16, otherwise center-crop
    the long axis down to a 9:16 window before scaling."""
    src_ar = src_w / src_h

    if abs(src_ar - TARGET_AR) < AR_TOLERANCE:
        return f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos,setsar=1"

    if src_ar > TARGET_AR:
        # wider than 9:16 -> crop width, keep full height
        new_w = _round_to_even(src_h * TARGET_AR)
        x = (src_w - new_w) // 2
        crop = f"crop={new_w}:{src_h}:{x}:0"
    else:
        # narrower/taller than 9:16 -> crop height, keep full width
        new_h = _round_to_even(src_w / TARGET_AR)
        y = (src_h - new_h) // 2
        crop = f"crop={src_w}:{new_h}:0:{y}"

    return f"{crop},scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=lanczos,setsar=1"


def parse_timestamp(value: str) -> float:
    """Parse a timestamp given as raw seconds ("12.5") or "MM:SS"/"HH:MM:SS"."""
    if ":" not in value:
        return float(value)
    parts = [float(p) for p in value.split(":")]
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_timestamp(seconds: float) -> str:
    """Reverse of parse_timestamp: seconds -> "MM:SS", or "H:MM:SS" past 1 hour."""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Windows-safe filename stem: strip reserved chars, collapse whitespace to
    hyphens, cap length. Preserves the original casing."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = re.sub(r"\s+", "-", cleaned.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
    if not cleaned:
        cleaned = "video"
    return cleaned[:max_length].rstrip("-")


class IntervalError(ValueError):
    pass


def select_interval(
    duration: float,
    mode: str = "random",
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> tuple:
    """Return (start, length) in seconds, always length <= MAX_CLIP_SECONDS."""
    if mode == "random":
        if duration <= MAX_CLIP_SECONDS:
            return 0.0, duration
        max_start = duration - MAX_CLIP_SECONDS
        chosen_start = random.uniform(0, max_start)
        return chosen_start, MAX_CLIP_SECONDS

    if mode == "manual":
        if start is None:
            raise IntervalError("--start is required in manual mode")
        if start < 0 or start >= duration:
            raise IntervalError(
                f"--start ({start}) is outside the video's duration ({duration:.2f}s)"
            )
        chosen_end = end if end is not None else start + MAX_CLIP_SECONDS
        chosen_end = min(chosen_end, start + MAX_CLIP_SECONDS, duration)
        if chosen_end <= start:
            raise IntervalError(
                f"--end ({end}) must be greater than --start ({start})"
            )
        return start, chosen_end - start

    raise IntervalError(f"Unknown interval mode: {mode}")


def pick_background_clip(folder: Path) -> Path:
    clips = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    if not clips:
        raise FileNotFoundError(
            f"No background video clips found in {folder}. Add at least one "
            f"video file (e.g. .mp4) to that folder."
        )
    return random.choice(clips)


def pick_background_offset(clip_duration: float, needed_duration: float) -> Optional[float]:
    """Return a random start offset within the clip if it's long enough to cover
    needed_duration without looping, or None if the clip must be looped instead."""
    if clip_duration <= needed_duration:
        return None
    max_start = clip_duration - needed_duration
    return random.uniform(0, max_start)


def compute_giga_sample_intervals(
    start: float, end: float, count: int, clip_length: float
) -> List[Tuple[float, float]]:
    """Split [start, end) into `count` equal buckets and return one (clip_start,
    clip_end) per bucket. If a bucket is big enough, the clip is placed at a
    random offset inside it (non-overlapping, spread across the range). If
    not, the clip is anchored at the bucket's start (overlap allowed), clamped
    so it never runs past `end` -- either way, clips still spread evenly
    across the whole range."""
    if count < 1:
        raise ValueError("count must be >= 1")
    duration = end - start
    if duration <= 0:
        raise ValueError(f"end ({end}) must be greater than start ({start})")
    if clip_length > duration:
        raise ValueError(
            f"clip_length ({clip_length}) cannot exceed the sampled range ({duration})"
        )

    bucket_size = duration / count
    intervals = []
    for i in range(count):
        bucket_start = start + i * bucket_size
        if bucket_size >= clip_length:
            clip_start = bucket_start + random.uniform(0, bucket_size - clip_length)
        else:
            clip_start = bucket_start
        clip_start = max(start, min(clip_start, end - clip_length))
        intervals.append((clip_start, clip_start + clip_length))
    return intervals
