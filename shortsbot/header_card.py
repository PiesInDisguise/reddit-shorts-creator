from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CARD_WIDTH = 950
PAD = 44
ICON_SIZE = 96
CORNER_RADIUS = 36
SUPERSAMPLE = 3

BADGE_FONT_SIZE = 30
AUTHOR_FONT_SIZE = 28
TITLE_FONT_SIZE = 58
TITLE_LINE_HEIGHT = 70
BADGE_PAD_X = 14
BADGE_PAD_Y = 8
BADGE_TO_AUTHOR_GAP = 10
GAP_AFTER_HEADER = 34

REDDIT_ORANGE = (255, 69, 0, 255)
CARD_WHITE = (255, 255, 255, 255)
TITLE_BLACK = (17, 17, 17, 255)
AUTHOR_GRAY = (110, 110, 110, 255)
SHADOW_BLACK = (0, 0, 0, 110)


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
    """Render a full-frame RGBA image with an opaque white "card" centered on
    the frame; everywhere else is transparent so it can be overlaid directly
    on the composite. All layout math below is done in logical (1x) units and
    only scaled up by SUPERSAMPLE at draw time, so spacing stays consistent
    and easy to reason about."""
    ss = SUPERSAMPLE
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    badge_font_1x = ImageFont.truetype(str(font_path), BADGE_FONT_SIZE)
    author_font_1x = ImageFont.truetype(str(font_path), AUTHOR_FONT_SIZE)
    title_font_1x = ImageFont.truetype(str(font_path), TITLE_FONT_SIZE)

    inner_width = CARD_WIDTH - PAD * 2
    icon_column_width = ICON_SIZE + 24 if icon_path and icon_path.exists() else 0
    text_x = icon_column_width

    badge_text = f"r/{subreddit}".upper()
    badge_bbox = measure_draw.textbbox((0, 0), badge_text, font=badge_font_1x)
    badge_h = badge_bbox[3] - badge_bbox[1]
    badge_box_h = badge_h + BADGE_PAD_Y * 2

    author_text = f"u/{author}"
    author_bbox = measure_draw.textbbox((0, 0), author_text, font=author_font_1x)
    author_h = author_bbox[3] - author_bbox[1]

    text_column_height = badge_box_h + BADGE_TO_AUTHOR_GAP + author_h
    header_row_height = max(ICON_SIZE, text_column_height)

    title_lines = _wrap_text(measure_draw, title.upper(), title_font_1x, inner_width)
    title_block_height = len(title_lines) * TITLE_LINE_HEIGHT

    card_height = PAD + header_row_height + GAP_AFTER_HEADER + title_block_height + PAD

    shadow_margin = 40
    hi_w = (CARD_WIDTH + shadow_margin * 2) * ss
    hi_h = (card_height + shadow_margin * 2) * ss
    hi_canvas = Image.new("RGBA", (hi_w, hi_h), (0, 0, 0, 0))

    # Drop shadow: a blurred, offset rounded rect behind the card for depth.
    shadow_layer = Image.new("RGBA", (hi_w, hi_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_offset_1x = 10
    shadow_draw.rounded_rectangle(
        [
            shadow_margin * ss,
            (shadow_margin + shadow_offset_1x) * ss,
            (shadow_margin + CARD_WIDTH) * ss,
            (shadow_margin + card_height + shadow_offset_1x) * ss,
        ],
        radius=CORNER_RADIUS * ss,
        fill=SHADOW_BLACK,
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(14 * ss))
    hi_canvas = Image.alpha_composite(hi_canvas, shadow_layer)

    # The white card itself, rounded corners.
    card_draw = ImageDraw.Draw(hi_canvas)
    card_box = [
        shadow_margin * ss,
        shadow_margin * ss,
        (shadow_margin + CARD_WIDTH) * ss,
        (shadow_margin + card_height) * ss,
    ]
    card_draw.rounded_rectangle(card_box, radius=CORNER_RADIUS * ss, fill=CARD_WHITE)

    origin_x = shadow_margin
    origin_y = shadow_margin

    def pt(x, y):
        return ((origin_x + x) * ss, (origin_y + y) * ss)

    # Icon (circular, thin orange ring), top-aligned with the header row.
    if icon_path and icon_path.exists():
        icon_hi_size = ICON_SIZE * ss
        icon = Image.open(icon_path).convert("RGBA").resize(
            (icon_hi_size, icon_hi_size), Image.LANCZOS
        )
        icon = _circular_mask(icon)
        icon_pos = pt(PAD, PAD)
        ring_pad = 5 * ss
        card_draw.ellipse(
            [
                icon_pos[0] - ring_pad,
                icon_pos[1] - ring_pad,
                icon_pos[0] + icon_hi_size + ring_pad,
                icon_pos[1] + icon_hi_size + ring_pad,
            ],
            outline=REDDIT_ORANGE,
            width=4 * ss,
        )
        hi_canvas.paste(icon, (int(icon_pos[0]), int(icon_pos[1])), icon)

    # "r/subreddit" as a bold orange badge, "u/author" in gray beneath it.
    badge_hi_font = ImageFont.truetype(str(font_path), BADGE_FONT_SIZE * ss)
    author_hi_font = ImageFont.truetype(str(font_path), AUTHOR_FONT_SIZE * ss)

    badge_top_left = pt(PAD + text_x, PAD)
    badge_w = (badge_bbox[2] - badge_bbox[0]) * ss
    badge_box = [
        badge_top_left[0],
        badge_top_left[1],
        badge_top_left[0] + badge_w + BADGE_PAD_X * 2 * ss,
        badge_top_left[1] + badge_box_h * ss,
    ]
    card_draw.rounded_rectangle(badge_box, radius=10 * ss, fill=REDDIT_ORANGE)
    card_draw.text(
        (badge_box[0] + BADGE_PAD_X * ss, badge_box[1] + BADGE_PAD_Y * ss - badge_bbox[1] * ss),
        badge_text,
        font=badge_hi_font,
        fill=CARD_WHITE,
    )

    author_top = pt(PAD + text_x, PAD + badge_box_h + BADGE_TO_AUTHOR_GAP)
    card_draw.text(
        (author_top[0], author_top[1] - author_bbox[1] * ss),
        author_text,
        font=author_hi_font,
        fill=AUTHOR_GRAY,
    )

    # Title, bold black, wrapped, below the header row.
    title_hi_font = ImageFont.truetype(str(font_path), TITLE_FONT_SIZE * ss)
    title_top_y = PAD + header_row_height + GAP_AFTER_HEADER
    for i, line in enumerate(title_lines):
        pos = pt(PAD, title_top_y + i * TITLE_LINE_HEIGHT)
        card_draw.text(pos, line, font=title_hi_font, fill=TITLE_BLACK)

    final_w = hi_w // ss
    final_h = hi_h // ss
    card_image = hi_canvas.resize((final_w, final_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    paste_x = (frame_width - final_w) // 2
    paste_y = (frame_height - final_h) // 2
    canvas.alpha_composite(card_image, (paste_x, paste_y))

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
