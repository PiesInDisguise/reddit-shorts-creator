import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import captions, ffmpeg_utils, header_card, reddit_client, tts_client, video_utils

BUDGET_SECONDS = 58.0
WORDS_PER_SECOND_ESTIMATE = 2.5

ProgressCB = Callable[[str, float], None]


def _noop_progress(stage: str, fraction: float) -> None:
    pass


def _estimate_speed_needed(text: str, remaining_budget: float) -> float:
    word_count = max(1, len(text.split()))
    estimated_duration = word_count / WORDS_PER_SECOND_ESTIMATE
    if remaining_budget <= 0 or estimated_duration <= remaining_budget:
        return 1.0
    return estimated_duration / remaining_budget


def _concat_audio(paths: list, out_path: Path) -> None:
    args = []
    for p in paths:
        args += ["-i", str(p)]
    n = len(paths)
    filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    args += ["-filter_complex", filter_str, "-map", "[aout]", str(out_path)]
    ffmpeg_utils.run_ffmpeg(args)


def run(
    url: str,
    settings,
    voice_id: Optional[str] = None,
    out_path: Optional[Path] = None,
    keep_work: bool = False,
    progress_cb: Optional[ProgressCB] = None,
) -> Path:
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    settings.require_elevenlabs()
    settings.require_reddit_user_agent()
    settings.require_reddit_oauth()

    voice_id = voice_id or settings.elevenlabs_default_voice_id
    icon_cache_dir = Path("cache") / "subreddit_icons"

    progress_cb("Fetching Reddit post", 0.0)
    post = reddit_client.fetch_post(
        url,
        settings.reddit_user_agent,
        icon_cache_dir,
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
    )

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- Title narration (always normal pace) ---
    progress_cb("Synthesizing title narration", 0.05)
    title_path = work_dir / "title.mp3"
    title_alignment = tts_client.synthesize(
        post.title, voice_id, settings.elevenlabs_api_key, title_path, speed=1.0
    )
    title_duration = ffmpeg_utils.probe_audio_duration(title_path)

    # --- Body narration ---
    body_text = post.body.strip() or post.title  # title-only posts: nothing else to read
    has_body = bool(post.body.strip())

    remaining_budget = BUDGET_SECONDS - title_duration
    initial_speed = (
        _estimate_speed_needed(body_text, remaining_budget) if has_body else 1.0
    )
    api_speed, _ = tts_client.clamp_speed_for_budget(initial_speed)

    progress_cb("Synthesizing body narration", 0.15)
    body_path = work_dir / "body.mp3"
    if has_body:
        body_alignment = tts_client.synthesize(
            body_text, voice_id, settings.elevenlabs_api_key, body_path, speed=api_speed
        )
        body_duration = ffmpeg_utils.probe_audio_duration(body_path)
    else:
        body_alignment = tts_client.Alignment(characters=[], start_times=[], end_times=[])
        body_duration = 0.0

    total_duration = title_duration + body_duration

    # --- Remainder speed-up if the estimate undershot ---
    if total_duration > BUDGET_SECONDS and has_body:
        progress_cb("Adjusting narration speed to fit 60s", 0.45)
        remainder_factor = total_duration / BUDGET_SECONDS
        sped_body_path = work_dir / "body_sped.mp3"
        ffmpeg_utils.run_ffmpeg(
            [
                "-i",
                str(body_path),
                "-filter:a",
                f"atempo={remainder_factor:.6f}",
                str(sped_body_path),
            ]
        )
        body_path = sped_body_path
        body_duration = ffmpeg_utils.probe_audio_duration(body_path)

        rescaled_starts = [t / remainder_factor for t in body_alignment.start_times]
        rescaled_ends = [t / remainder_factor for t in body_alignment.end_times]
        body_alignment = tts_client.Alignment(
            characters=body_alignment.characters,
            start_times=rescaled_starts,
            end_times=rescaled_ends,
        )
        total_duration = title_duration + body_duration

    # --- Concatenate narration audio ---
    progress_cb("Concatenating narration audio", 0.5)
    narration_path = work_dir / "narration.mp3"
    if has_body:
        _concat_audio([title_path, body_path], narration_path)
    else:
        narration_path = title_path

    # --- Captions (body only; title is shown as full text in the header card) ---
    progress_cb("Building word-flash captions", 0.6)
    body_words = (
        captions.words_from_alignment(body_alignment, time_offset=title_duration)
        if has_body
        else []
    )
    chunks = captions.chunk_words(body_words, chunk_size=2, final_end=total_duration)
    caption_overlay_path = captions.build_caption_overlay(
        chunks, title_duration, work_dir, settings.impact_font_path
    )

    # --- Header card ---
    progress_cb("Rendering header card", 0.78)
    header_path = work_dir / "header.png"
    header_card.save_header_card_png(
        post.subreddit, post.author, post.title, post.icon_path, settings.impact_font_path, header_path
    )

    # --- Background footage ---
    progress_cb("Preparing background footage", 0.82)
    clip_path = video_utils.pick_background_clip(settings.background_clips_dir)
    clip_info = ffmpeg_utils.probe(clip_path)
    offset = video_utils.pick_background_offset(clip_info["duration"], total_duration)
    crop_filter = video_utils.build_crop_filter(clip_info["width"], clip_info["height"])

    if offset is not None:
        bg_input_args = ["-ss", str(offset), "-i", str(clip_path)]
    else:
        bg_input_args = ["-stream_loop", "-1", "-i", str(clip_path)]

    # --- Final composite ---
    if out_path is None:
        Path("output").mkdir(parents=True, exist_ok=True)
        out_path = Path("output") / f"reddit_{post.post_id}_{int(time.time())}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"[0:v]{crop_filter}[bg];"
        f"[bg][1:v]overlay=0:0:enable='between(t,0,{title_duration:.3f})'[bgh];"
        f"[bgh][2:v]overlay=0:0[vout]"
    )

    args = (
        bg_input_args
        + ["-loop", "1", "-framerate", "30", "-i", str(header_path)]
        + ["-i", str(caption_overlay_path)]
        + ["-i", str(narration_path)]
        + [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "3:a",
            "-t",
            f"{total_duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
    )
    progress_cb("Compositing final video", 0.85)
    ffmpeg_utils.run_ffmpeg(args)

    if not keep_work:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)

    progress_cb("Done", 1.0)
    return out_path
