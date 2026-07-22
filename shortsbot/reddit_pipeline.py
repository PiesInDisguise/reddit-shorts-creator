import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import bgmusic, captions, ffmpeg_utils, header_card, reddit_client, sfx, tts_client, video_utils, voices

BUDGET_SECONDS = 118.0  # ~2:00 target, minus a small safety margin for encoder rounding

ProgressCB = Callable[[str, float], None]


def _noop_progress(stage: str, fraction: float) -> None:
    pass


def build_hashtags(subreddit: str) -> str:
    return f"#reddit #story #stories #{subreddit}"


def _atempo_chain(factor: float) -> str:
    """Build an ffmpeg atempo filter chain for an arbitrary speed factor --
    a single atempo only supports [0.5, 2.0], so factors beyond that are
    split across multiple chained atempo stages."""
    stages = []
    remaining = factor
    while remaining > 2.0:
        stages.append(2.0)
        remaining /= 2.0
    stages.append(remaining)
    return ",".join(f"atempo={s:.6f}" for s in stages)


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
    """Fetch the post at url, then render it. See render_post() for the case
    where the caller already has a fetched RedditPost in hand (e.g. the
    autonomous picker or the GUI's "Create with Upload" button) and wants to
    avoid a redundant Apify fetch."""
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    settings.require_elevenlabs()
    settings.require_apify()

    icon_cache_dir = Path("cache") / "subreddit_icons"
    progress_cb("Fetching Reddit post", 0.0)
    post = reddit_client.fetch_post(url, settings.apify_api_token, icon_cache_dir)

    return render_post(
        post, settings, voice_id=voice_id, out_path=out_path,
        keep_work=keep_work, progress_cb=progress_cb,
    )


def render_post(
    post,
    settings,
    voice_id: Optional[str] = None,
    out_path: Optional[Path] = None,
    keep_work: bool = False,
    progress_cb: Optional[ProgressCB] = None,
) -> Path:
    """Render a short from an already-fetched RedditPost (no Apify call)."""
    progress_cb = progress_cb or _noop_progress

    if not ffmpeg_utils.ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Run `python main.py doctor`.")

    settings.require_elevenlabs()

    voice_id = voice_id or voices.load_voices()[0]

    job_id = uuid.uuid4().hex[:8]
    work_dir = Path("work") / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- Title narration (always normal pace) ---
    progress_cb("Synthesizing title narration", 0.05)
    title_path = work_dir / "title.mp3"
    title_alignment = tts_client.synthesize(post.title, voice_id, settings.elevenlabs_api_key, title_path)
    title_duration = ffmpeg_utils.probe_audio_duration(title_path)

    # --- Body narration (always generated at natural pace; any needed
    # speed-up happens below via atempo, based on the actually-measured
    # duration rather than a pre-estimate) ---
    body_text = post.body.strip()
    has_body = bool(body_text)

    progress_cb("Synthesizing body narration", 0.15)
    body_path = work_dir / "body.mp3"
    if has_body:
        body_alignment = tts_client.synthesize(body_text, voice_id, settings.elevenlabs_api_key, body_path)
        body_duration = ffmpeg_utils.probe_audio_duration(body_path)
    else:
        body_alignment = tts_client.Alignment(characters=[], start_times=[], end_times=[])
        body_duration = 0.0

    total_duration = title_duration + body_duration

    # --- Speed up to fit the budget if needed (no cap -- the full story is
    # always narrated within budget, however fast that requires) ---
    if total_duration > BUDGET_SECONDS and has_body:
        progress_cb("Adjusting narration speed to fit the time budget", 0.45)
        remainder_factor = total_duration / BUDGET_SECONDS
        sped_body_path = work_dir / "body_sped.mp3"
        ffmpeg_utils.run_ffmpeg(
            [
                "-i",
                str(body_path),
                "-filter:a",
                _atempo_chain(remainder_factor),
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

    # --- Background music bed, quiet under the narration ---
    progress_cb("Preparing background music", 0.8)
    music_path = bgmusic.ensure_background_music()
    music_duration = ffmpeg_utils.probe_audio_duration(music_path)
    music_offset = video_utils.pick_background_offset(music_duration, total_duration)
    if music_offset is not None:
        music_input_args = ["-ss", str(music_offset), "-i", str(music_path)]
    else:
        music_input_args = ["-stream_loop", "-1", "-i", str(music_path)]

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
        title_slug = video_utils.sanitize_filename(post.title)
        out_path = Path("output") / f"{title_slug}_{int(time.time())}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Both overlays now span the full clip timeline with built-in transparency
    # for their "off" periods, so compositing them is just two plain overlays.
    filter_complex = (
        f"[0:v]{crop_filter}[bg];"
        f"[bg][1:v]overlay=0:0[bgh];"
        f"[bgh][2:v]overlay=0:0[vout];"
        f"[4:a]volume=0.55[woosh];"
        f"[5:a]volume=0.18[music];"
        f"[3:a][woosh][music]amix=inputs=3:duration=first:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.95[aout]"
    )

    args = (
        bg_input_args
        + ["-i", str(header_overlay_path)]
        + ["-i", str(caption_overlay_path)]
        + ["-i", str(narration_path)]
        + ["-i", str(whoosh_path)]
        + music_input_args
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
            "-metadata",
            f"title={post.title}",
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
