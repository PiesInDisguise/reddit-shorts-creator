import uuid
from pathlib import Path
from typing import Callable, List, Optional

import yt_dlp

from . import ffmpeg_utils, video_utils

ProgressCB = Callable[[str, float], None]


def _noop_progress(stage: str, fraction: float) -> None:
    pass


def download_video(url: str, work_dir: Path, progress_cb: ProgressCB) -> tuple:
    work_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(work_dir / "source.%(ext)s")

    seen_max = 0.0

    def hook(d):
        nonlocal seen_max
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes")
        if not total or not downloaded:
            return
        fraction = min(1.0, downloaded / total)
        seen_max = max(seen_max, fraction)
        progress_cb("Downloading video", seen_max * 0.7)

    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    source_path = work_dir / "source.mp4"
    if not source_path.exists():
        # yt-dlp may not have merged to mp4 if only one stream was available
        candidates = list(work_dir.glob("source.*"))
        if not candidates:
            raise FileNotFoundError(f"yt-dlp did not produce an output file in {work_dir}")
        source_path = candidates[0]

    return source_path, info.get("id", "video"), info.get("title") or "video"


def fetch_info(url: str) -> dict:
    """Metadata-only lookup (no download) -- used to populate the Giga Sample
    range slider with the source video's real title/duration."""
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title") or "video",
        "duration": float(info.get("duration") or 0.0),
    }


def _encode_clip(
    source_path: Path,
    vf: str,
    clip_start: float,
    clip_length: float,
    title_tag: str,
    out_path: Path,
) -> None:
    ffmpeg_utils.run_ffmpeg(
        [
            "-ss",
            str(clip_start),
            "-i",
            str(source_path),
            "-t",
            str(clip_length),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-metadata",
            f"title={title_tag}",
            str(out_path),
        ]
    )


def _descriptive_filename(title: str, start_ts: str, end_ts: str) -> str:
    stem = video_utils.sanitize_filename(title)
    ts_part = f"{start_ts}-{end_ts}".replace(":", "-")
    return f"{stem}_{ts_part}.mp4"


def run(
    url: str,
    mode: str = "random",
    start: Optional[float] = None,
    end: Optional[float] = None,
    out_path: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    keep_work: bool = False,
    progress_cb: Optional[ProgressCB] = None,
) -> Path:
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id

    progress_cb("Downloading video", 0.0)
    source_path, video_id, title = download_video(url, work_dir, progress_cb)

    progress_cb("Probing source video", 0.72)
    info = ffmpeg_utils.probe(source_path)

    chosen_start, clip_len = video_utils.select_interval(
        info["duration"], mode=mode, start=start, end=end
    )
    clip_end = chosen_start + clip_len
    vf = video_utils.build_crop_filter(info["width"], info["height"])

    start_ts = video_utils.format_timestamp(chosen_start)
    end_ts = video_utils.format_timestamp(clip_end)
    title_tag = f"{title} - {start_ts}-{end_ts}"

    if out_path is None:
        out_dir = out_dir or Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / _descriptive_filename(title, start_ts, end_ts)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    progress_cb("Encoding shorts clip", 0.75)
    _encode_clip(source_path, vf, chosen_start, clip_len, title_tag, out_path)

    if not keep_work:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)

    progress_cb("Done", 1.0)
    return out_path


def run_giga_sample(
    url: str,
    count: int,
    start: Optional[float] = None,
    end: Optional[float] = None,
    clip_length: float = 180.0,
    out_dir: Optional[Path] = None,
    keep_work: bool = False,
    progress_cb: Optional[ProgressCB] = None,
) -> List[Path]:
    """Download one YouTube video once and cut `count` separate clips of
    `clip_length` seconds each, spread across [start, end] (defaults to the
    whole video) -- see video_utils.compute_giga_sample_intervals for the
    spacing algorithm."""
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id

    progress_cb("Downloading video", 0.0)
    source_path, video_id, title = download_video(url, work_dir, progress_cb)

    progress_cb("Probing source video", 0.15)
    info = ffmpeg_utils.probe(source_path)
    duration = info["duration"]

    range_start = 0.0 if start is None else start
    range_end = duration if end is None else min(end, duration)
    if range_start < 0 or range_end > duration or range_end <= range_start:
        raise ValueError(f"Invalid range {range_start}-{range_end} for a {duration:.2f}s video")

    intervals = video_utils.compute_giga_sample_intervals(
        range_start, range_end, count, clip_length
    )
    vf = video_utils.build_crop_filter(info["width"], info["height"])

    out_dir = out_dir or Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    n = len(intervals)
    for i, (clip_start, clip_end) in enumerate(intervals):
        progress_cb(f"Encoding clip {i + 1}/{n}", 0.2 + 0.75 * (i / n))
        start_ts = video_utils.format_timestamp(clip_start)
        end_ts = video_utils.format_timestamp(clip_end)
        clip_out_path = out_dir / _descriptive_filename(title, start_ts, end_ts)
        title_tag = f"{title} - {start_ts}-{end_ts}"
        _encode_clip(source_path, vf, clip_start, clip_end - clip_start, title_tag, clip_out_path)
        results.append(clip_out_path)

    if not keep_work:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)

    progress_cb("Done", 1.0)
    return results
