"""
Generates a professional LinkedIn post infographic using Pillow (local, no API).

Design: dark navy background, LinkedIn blue accents, topic headline,
format badge, post excerpt, and author footer. Always produces a
consistent, relevant, branded image — no external API required.
"""
import io
import logging
import textwrap

logger = logging.getLogger("linkedin_agent")

# LinkedIn recommended image size (1.91:1 landscape)
_W, _H = 1200, 627

# Color palette
_BG     = (10,  35,  66)    # #0A2342 dark navy
_DARK   = (6,   22,  44)    # #06162C deeper navy (footer)
_ACCENT = (0,  119, 181)    # #0077B5 LinkedIn blue
_DIM    = (0,   80, 140)    # dimmer blue (decorative)
_WHITE  = (255, 255, 255)
_MUTED  = (160, 200, 230)   # soft blue-grey (body text)

# Font paths for Railway (Debian) — falls back to PIL bitmap if missing
_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_REG_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_FORMAT_LABELS = {
    "analysis":     "ANÁLISE",
    "list":         "LISTA",
    "news_context": "NOTÍCIA",
    "trend":        "TENDÊNCIA",
    "week_wrap":    "RESUMO SEMANAL",
}


def generate_post_image(
    post_content: str,
    topic_name: str,
    post_format: str,
    author_name: str = "LinkedIn Agent",
) -> bytes | None:
    """Returns JPEG bytes of a professional infographic, or None on failure."""
    try:
        return _render(post_content, topic_name, post_format, author_name)
    except Exception as exc:
        logger.exception("Pillow infographic generation failed: %s", exc)
        return None


# ── Renderer ──────────────────────────────────────────────────────────────────

def _render(
    post_content: str,
    topic_name: str,
    post_format: str,
    author_name: str,
) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img  = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    # ── Decorative background shapes ─────────────────────────────────────────
    # Large circle — top-right corner
    draw.ellipse([870, -180, 1420, 370], fill=_DIM)
    # Small accent circles — bottom-right
    for cx, cy, r in [(1100, 520, 55), (1155, 570, 32), (1055, 575, 18)]:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 90, 150))

    # Left accent bar
    draw.rectangle([0, 0, 8, _H], fill=_ACCENT)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_title = _font(_BOLD_FONTS, 46)
    f_badge = _font(_BOLD_FONTS, 15)
    f_body  = _font(_REG_FONTS,  18)
    f_foot  = _font(_REG_FONTS,  14)

    # ── Topic title ───────────────────────────────────────────────────────────
    title_text = topic_name.upper()
    wrapped_title = textwrap.fill(title_text, width=26)
    draw.text((56, 68), wrapped_title, font=f_title, fill=_WHITE)

    # Measure title height to position elements below it
    title_lines = wrapped_title.count("\n") + 1
    title_bottom = 68 + title_lines * 56

    # Short LinkedIn-blue underline beneath title
    draw.rectangle([56, title_bottom + 10, 116, title_bottom + 14], fill=_ACCENT)

    # ── Format badge ──────────────────────────────────────────────────────────
    badge_label = _FORMAT_LABELS.get(post_format, post_format.replace("_", " ").upper())
    bx, by = 56, title_bottom + 28
    try:
        bw = int(draw.textlength(badge_label, font=f_badge))
    except AttributeError:
        bw = len(badge_label) * 9
    _rounded_rect(draw, bx, by, bx + bw + 24, by + 28, 14, _ACCENT)
    draw.text((bx + 12, by + 6), badge_label, font=f_badge, fill=_WHITE)

    # ── Post excerpt ──────────────────────────────────────────────────────────
    excerpt = post_content[:520].replace("\n\n", " ").replace("\n", " ").strip()
    wrapped  = textwrap.fill(excerpt, width=70)
    lines    = wrapped.split("\n")[:7]
    ey = by + 50
    for line in lines:
        draw.text((56, ey), line, font=f_body, fill=_MUTED)
        ey += 30

    # ── Footer bar ────────────────────────────────────────────────────────────
    draw.rectangle([0, _H - 46, _W, _H], fill=_DARK)
    draw.rectangle([0, _H - 46, 8,  _H], fill=_ACCENT)
    footer_txt = f"LinkedIn Agent  ·  {author_name}"
    draw.text((56, _H - 30), footer_txt, font=f_foot, fill=_MUTED)

    # ── Encode ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    logger.info("Infographic generated for topic '%s'", topic_name)
    return buf.getvalue()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _font(paths: list[str], size: int):
    from PIL import ImageFont
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


def _rounded_rect(draw, x0, y0, x1, y1, radius, fill):
    """Draw a rounded rectangle (compatible with older Pillow versions)."""
    try:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)
    except AttributeError:
        # Pillow < 8.2 fallback
        draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
        draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
        draw.ellipse([x0, y0, x0 + radius * 2, y0 + radius * 2], fill=fill)
        draw.ellipse([x1 - radius * 2, y0, x1, y0 + radius * 2], fill=fill)
        draw.ellipse([x0, y1 - radius * 2, x0 + radius * 2, y1], fill=fill)
        draw.ellipse([x1 - radius * 2, y1 - radius * 2, x1, y1], fill=fill)