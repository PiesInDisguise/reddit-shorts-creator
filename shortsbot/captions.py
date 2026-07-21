from dataclasses import dataclass
from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont

from . import ffmpeg_utils
from .tts_client import Alignment

FONT_SIZE = 130
MIN_FONT_SIZE = 60
STROKE_WIDTH = 8
FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
SAFE_WIDTH = int(FRAME_WIDTH * 0.9)


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Chunk:
    text: str
    start: float
    end: float


def words_from_alignment(alignment: Alignment, time_offset: float = 0.0) -> List[Word]:
    """Walk character-level alignment and split into words on whitespace boundaries."""
    words: List[Word] = []
    current_chars: List[str] = []
    current_start = None

    for ch, start, end in zip(alignment.characters, alignment.start_times, alignment.end_times):
        if ch.isspace():
            if current_chars:
                words.append(
                    Word(
                        text="".join(current_chars),
                        start=current_start + time_offset,
                        end=prev_end + time_offset,
                    )
                )
                current_chars = []
                current_start = None
            continue

        if current_start is None:
            current_start = start
        current_chars.append(ch)
        prev_end = end

    if current_chars:
        words.append(
            Word(
                text="".join(current_chars),
                start=current_start + time_offset,
                end=prev_end + time_offset,
            )
        )

    return words


def chunk_words(words: List[Word], chunk_size: int = 2, final_end: float = None) -> List[Chunk]:
    """Group words into chunks of at most `chunk_size`. Each chunk's end is set to
    the next chunk's start so exactly one caption is showing at every instant
    (no blank gaps between spoken words)."""
    chunks: List[Chunk] = []
    for i in range(0, len(words), chunk_size):
        group = words[i : i + chunk_size]
        text = " ".join(w.text for w in group)
        chunks.append(Chunk(text=text, start=group[0].start, end=group[-1].end))

    for i in range(len(chunks) - 1):
        chunks[i].end = chunks[i + 1].start

    if chunks and final_end is not None:
        chunks[-1].end = max(chunks[-1].end, final_end)

    return chunks


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: Path) -> ImageFont.FreeTypeFont:
    size = FONT_SIZE
    while size > MIN_FONT_SIZE:
        font = ImageFont.truetype(str(font_path), size)
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=STROKE_WIDTH)
        if bbox[2] - bbox[0] <= SAFE_WIDTH:
            return font
        size -= 6
    return ImageFont.truetype(str(font_path), MIN_FONT_SIZE)


def _render_chunk_image(text: str, font_path: Path) -> Image.Image:
    canvas = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    display_text = text.upper()
    font = _fit_font(draw, display_text, font_path)
    draw.text(
        (FRAME_WIDTH // 2, FRAME_HEIGHT // 2),
        display_text,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=STROKE_WIDTH,
        stroke_fill=(0, 0, 0, 255),
        anchor="mm",
    )
    return canvas


def build_caption_overlay(
    chunks: List[Chunk],
    title_duration: float,
    work_dir: Path,
    font_path: Path,
) -> Path:
    """Render each unique chunk once, build a concat-demuxer list spanning the
    entire clip timeline (transparent during the title window, then each chunk
    for its duration), and decode it to a single alpha-channel .mov so the final
    composite only needs one overlay filter for captions."""
    captions_dir = work_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)

    blank_path = captions_dir / "blank.png"
    Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0)).save(blank_path)

    rendered: dict = {}
    list_lines: List[str] = []

    def add_entry(path: Path, duration: float):
        list_lines.append(f"file '{path.resolve().as_posix()}'")
        list_lines.append(f"duration {max(duration, 1 / 60):.6f}")

    if title_duration > 0:
        add_entry(blank_path, title_duration)

    for i, chunk in enumerate(chunks):
        if chunk.text not in rendered:
            safe_name = f"chunk_{len(rendered):04d}.png"
            chunk_path = captions_dir / safe_name
            _render_chunk_image(chunk.text, font_path).save(chunk_path)
            rendered[chunk.text] = chunk_path
        add_entry(rendered[chunk.text], chunk.end - chunk.start)

    # concat demuxer quirk: the last entry's duration is ignored, so repeat the
    # final file once more without a duration line.
    last_file_line = list_lines[-2]
    list_lines.append(last_file_line)

    list_path = captions_dir / "list.txt"
    list_path.write_text("\n".join(list_lines), encoding="utf-8")

    overlay_path = work_dir / "captions_overlay.mov"
    ffmpeg_utils.run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vsync",
            "vfr",
            "-pix_fmt",
            "rgba",
            "-c:v",
            "qtrle",
            str(overlay_path),
        ]
    )
    return overlay_path
