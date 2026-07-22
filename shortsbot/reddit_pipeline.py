import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import captions, ffmpeg_utils, header_card, reddit_client, sfx, tts_client, video_utils

BUDGET_SECONDS = 88.0  # ~1:30 target, minus a small safety margin for encoder rounding
WORDS_PER_SECOND_ESTIMATE = 2.5  # ~150 wpm, a natural conversational narration pace
MAX_TOTAL_SPEED = 1.35  # ceiling on narration speed-up -- past this it sounds
# rushed/hard to follow even with word-flash captions helping comprehension

ProgressCB = Callable[[str, float], None]


def _noop_progress(stage: str, fraction: float) -> None:
    pass


def _truncate_to_sentence(text: str, max_words: int) -> str:
    """Cut text down to at most max_words, backing up to the last full
    sentence that fits rather than cutting mid-sentence."""
    words = text.split()
    if len(words) <= max_words:
        return text
    truncated_words = words[:max_words]
    for i in range(len(truncated_words) - 1, -1, -1):
        if truncated_words[i].rstrip().endswith((".", "!", "?")):
            return " ".join(truncated_words[: i + 1])
    return " ".join(truncated_words)  # no sentence boundary in range -- hard cut


def _prepare_body_for_budget(body_text: str, remaining_budget: float) -> tuple:
    """Decide the narration speed for body_text, capped at MAX_TOTAL_SPEED. If
    it still wouldn't fit remaining_budget even at that speed, truncate the
    body (at a sentence boundary) instead of speaking faster than the cap.
    Returns (speed, text_to_narrate)."""
    word_count = max(1, len(body_text.split()))
    estimated_duration = word_count / WORDS_PER_SECOND_ESTIMATE

    if remaining_budget <= 0 or estimated_duration <= remaining_budget:
        return 1.0, body_text

    needed_factor = estimated_duration / remaining_budget
    if needed_factor <= MAX_TOTAL_SPEED:
        return needed_factor, body_text

    max_words = int(remaining_budget * MAX_TOTAL_SPEED * WORDS_PER_SECOND_ESTIMATE)
    return MAX_TOTAL_SPEED, _truncate_to_sentence(body_text, max_words)


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
    settings.require_apify()

    voice_id = voice_id or settings.elevenlabs_default_voice_id
    icon_cache_dir = Path("cache") / "subreddit_icons"

    progress_cb("Fetching Reddit post", 0.0)
    post = reddit_client.fetch_post(url, settings.apify_api_token, icon_cache_dir)

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
    body_text = post.body.strip()
    has_body = bool(body_text)

    remaining_budget = BUDGET_SECONDS - title_duration
    if has_body:
        target_speed, body_text = _prepare_body_for_budget(body_text, remaining_budget)
    else:
        target_speed = 1.0
    api_speed = min(target_speed, tts_client.MAX_API_SPEED)

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

    # --- Remainder speed-up if the estimate undershot (capped at MAX_TOTAL_SPEED
    # combined with api_speed -- if that's not enough, the video runs slightly
    # over budget rather than sounding faster than the cap) ---
    if total_duration > BUDGET_SECONDS and has_body:
        progress_cb("Adjusting narration speed to fit the time budget", 0.45)
        ideal_remainder = total_duration / BUDGET_SECONDS
        max_allowed_remainder = MAX_TOTAL_SPEED / api_speed
        remainder_factor = min(ideal_remainder, max_allowed_remainder)
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

    # --- Header card (pop-in animation + hold + fade to transparent) ---
    progress_cb("Rendering header card", 0.78)
    header_canvas = header_card.render_header_card(
        post.subreddit, post.author, post.title, post.icon_path, settings.impact_font_path
    )
    header_overlay_path = header_card.build_header_overlay(
        header_canvas, title_duration, total_duration, work_dir
    )

    # --- Whoosh sound effect, timed to the header's pop-in ---
    whoosh_path = sfx.ensure_whoosh_sound()

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

    # Both overlays now span the full clip timeline with built-in transparency
    # for their "off" periods, so compositing them is just two plain overlays.
    filter_complex = (
        f"[0:v]{crop_filter}[bg];"
        f"[bg][1:v]overlay=0:0[bgh];"
        f"[bgh][2:v]overlay=0:0[vout];"
        f"[4:a]volume=0.55[woosh];"
        f"[3:a][woosh]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.95[aout]"
    )

    args = (
        bg_input_args
        + ["-i", str(header_overlay_path)]
        + ["-i", str(caption_overlay_path)]
        + ["-i", str(narration_path)]
        + ["-i", str(whoosh_path)]
        + [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
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
