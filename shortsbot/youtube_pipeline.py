import time
import uuid
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from . import ffmpeg_utils, video_utils

ProgressCB = Callable[[str, float], None]


def _noop_progress(stage: str, fraction: float) -> None:
    pass


def download_video(url: str, work_dir: Path, progress_cb: ProgressCB) -> Path:
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

    return source_path, info.get("id", "video")


def run(
    url: str,
    mode: str = "random",
    start: Optional[float] = None,
    end: Optional[float] = None,
    out_path: Optional[Path] = None,
    keep_work: bool = False,
    progress_cb: Optional[ProgressCB] = None,
) -> Path:
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id

    progress_cb("Downloading video", 0.0)
    source_path, video_id = download_video(url, work_dir, progress_cb)

    progress_cb("Probing source video", 0.72)
    info = ffmpeg_utils.probe(source_path)

    chosen_start, clip_len = video_utils.select_interval(
        info["duration"], mode=mode, start=start, end=end
    )
    vf = video_utils.build_crop_filter(info["width"], info["height"])

    if out_path is None:
        Path("output").mkdir(parents=True, exist_ok=True)
        out_path = Path("output") / f"youtube_{video_id}_{int(time.time())}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    progress_cb("Encoding shorts clip", 0.75)
    ffmpeg_utils.run_ffmpeg(
        [
            "-ss",
            str(chosen_start),
            "-i",
            str(source_path),
            "-t",
            str(clip_len),
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
            str(out_path),
        ]
    )

    if not keep_work:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)

    progress_cb("Done", 1.0)
    return out_path
