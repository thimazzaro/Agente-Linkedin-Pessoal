"""
Generates a professional image for LinkedIn posts.

Strategy (in order):
  1. Google Gemini Flash Exp via v1alpha API  (requires GOOGLE_AI_API_KEY)
  2. Pollinations.ai FLUX model               (free, no API key required)

Falls back gracefully to None only if both methods fail.
"""
import os
import logging
import urllib.parse
import requests

logger = logging.getLogger("linkedin_agent")

_FORMAT_STYLES: dict[str, str] = {
    "analysis":     "data visualization with abstract charts and graphs, corporate style",
    "list":         "clean numbered list visual with modern icons and bold typography",
    "news_context": "bold news-headline typography over a minimal background",
    "trend":        "upward trend arrow with data points, futuristic design",
    "week_wrap":    "weekly summary dashboard layout with metrics tiles",
}


def generate_post_image(
    post_content: str,
    topic_name: str,
    post_format: str,
) -> bytes | None:
    """
    Returns PNG/JPEG bytes for a professional LinkedIn infographic,
    or None if every generation method fails.
    """
    prompt = _build_prompt(post_content, topic_name, post_format)

    # 1 — Try Gemini (needs GOOGLE_AI_API_KEY)
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if api_key:
        result = _try_gemini(prompt, topic_name, api_key)
        if result:
            return result

    # 2 — Fallback: Pollinations.ai (free, no key needed, uses FLUX)
    return _try_pollinations(prompt, topic_name)


# ── Gemini Flash (v1alpha — image generation feature) ────────────────────────

def _try_gemini(prompt: str, topic_name: str, api_key: str) -> bytes | None:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed — skipping Gemini image generation")
        return None

    try:
        # Image generation requires the v1alpha API endpoint
        client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1alpha"},
        )
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                logger.info("Gemini image generated for topic '%s'", topic_name)
                return part.inline_data.data
        logger.warning("Gemini returned no image parts for '%s'", topic_name)
        return None
    except Exception as exc:
        logger.warning("Gemini image generation failed: %s — trying fallback", exc)
        return None


# ── Pollinations.ai fallback (FLUX, free, no key) ────────────────────────────

def _try_pollinations(prompt: str, topic_name: str) -> bytes | None:
    try:
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&nologo=true"
        resp = requests.get(url, timeout=60)
        if resp.ok and resp.content:
            logger.info("Pollinations image generated for topic '%s'", topic_name)
            return resp.content
        logger.warning("Pollinations returned %s for '%s'", resp.status_code, topic_name)
        return None
    except Exception as exc:
        logger.exception("Pollinations image generation failed: %s", exc)
        return None


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(post_content: str, topic_name: str, post_format: str) -> str:
    visual_style = _FORMAT_STYLES.get(post_format, "professional business infographic")
    snippet = post_content[:250].replace("\n", " ").strip()
    return (
        f"Professional LinkedIn post infographic about {topic_name}. "
        f"Visual style: {visual_style}. "
        f"Content theme: {snippet}. "
        "Design: dark navy blue and white palette, minimalist corporate style, "
        "no human faces, abstract data visuals and icons, clean bold typography, "
        "premium business look for financial markets and AI audience, high resolution."
    )
