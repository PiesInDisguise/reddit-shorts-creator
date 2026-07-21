from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 1000
CARD_MARGIN_TOP = 140
ICON_SIZE = 80
PADDING = 24


def _circular_mask(im: Image.Image) -> Image.Image:
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, im.size[0], im.size[1]), fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_header_card(
    subreddit: str,
    author: str,
    title: str,
    icon_path: Optional[Path],
    font_path: Path,
    frame_width: int = 1080,
    frame_height: int = 1920,
) -> Image.Image:
    """Render a full-frame RGBA image with the header card positioned near the top;
    everywhere else is transparent so it can be overlaid directly on the composite."""
    canvas = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    name_font = ImageFont.truetype(str(font_path), 40)
    title_font = ImageFont.truetype(str(font_path), 44)

    card_x = (frame_width - CARD_WIDTH) // 2
    y = CARD_MARGIN_TOP

    icon_x = card_x
    if icon_path and icon_path.exists():
        icon = Image.open(icon_path).convert("RGBA").resize((ICON_SIZE, ICON_SIZE))
        icon = _circular_mask(icon)
        canvas.paste(icon, (icon_x, y), icon)

    text_x = icon_x + ICON_SIZE + PADDING
    header_text = f"r/{subreddit}  •  u/{author}"
    draw.text((text_x, y + ICON_SIZE // 2 - 24), header_text, font=name_font, fill=(255, 255, 255, 255))

    title_y = y + ICON_SIZE + PADDING
    max_text_width = CARD_WIDTH
    lines = _wrap_text(draw, title, title_font, max_text_width)

    line_height = 54
    box_height = len(lines) * line_height + PADDING * 2
    box = Image.new("RGBA", (CARD_WIDTH, box_height), (0, 0, 0, 140))
    canvas.paste(box, (card_x, title_y), box)

    for i, line in enumerate(lines):
        draw.text(
            (card_x + PADDING, title_y + PADDING + i * line_height),
            line,
            font=title_font,
            fill=(255, 255, 255, 255),
        )

    return canvas


def save_header_card_png(
    subreddit: str,
    author: str,
    title: str,
    icon_path: Optional[Path],
    font_path: Path,
    out_path: Path,
) -> Path:
    img = render_header_card(subreddit, author, title, icon_path, font_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path
