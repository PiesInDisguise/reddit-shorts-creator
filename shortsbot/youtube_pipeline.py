import time
import uuid
from pathlib import Path
from typing import Optional

import yt_dlp

from . import ffmpeg_utils, video_utils


def download_video(url: str, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(work_dir / "source.%(ext)s")
    ydl_opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
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
) -> Path:
    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id

    source_path, video_id = download_video(url, work_dir)
    info = ffmpeg_utils.probe(source_path)

    chosen_start, clip_len = video_utils.select_interval(
        info["duration"], mode=mode, start=start, end=end
    )
    vf = video_utils.build_crop_filter(info["width"], info["height"])

    if out_path is None:
        Path("output").mkdir(parents=True, exist_ok=True)
        out_path = Path("output") / f"youtube_{video_id}_{int(time.time())}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

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

    return out_path
