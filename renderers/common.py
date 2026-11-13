"""Common drawing utilities for OLED renderers."""


def get_text_width(font, text):
    """Calculate pixel width of rendered text."""
    bbox = font.getbbox(str(text))
    return bbox[2] - bbox[0]


def draw_progress_bar(draw, x, y, width, height, percent):
    """
    Draw a clean, geometric progress bar without decorative borders.
    Outer frame: 1px black outline.
    Inner fill: Solid black rectangle proportional to percent (0-100).
    """
    pct = max(0.0, min(100.0, float(percent)))
    draw.rectangle((x, y, x + width - 1, y + height - 1), outline=0)
    inner_width = max(0, width - 4)
    inner_height = max(0, height - 4)
    fill_width = int(round((pct / 100.0) * inner_width))
    if fill_width > 0:
        draw.rectangle(
            (x + 2, y + 2, x + 2 + fill_width - 1, y + 2 + inner_height - 1),
            fill=0
        )
