"""
Generates a professional image for LinkedIn posts using Google Gemini
(gemini-2.0-flash-preview-image-generation), which works with a standard
Google AI Studio API key — no Vertex AI / GCP project required.

Requires:  GOOGLE_AI_API_KEY env var  (get one free at aistudio.google.com)
Falls back gracefully to None if the key is absent or generation fails.
"""
import os
import logging

logger = logging.getLogger("linkedin_agent")

# Model that supports image output via Google AI Studio API key
_MODEL = "gemini-2.0-flash-preview-image-generation"

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
    Generates a professional infographic image for a LinkedIn post.
    Returns PNG/JPEG bytes, or None when generation is skipped or fails.
    """
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        logger.info("GOOGLE_AI_API_KEY not configured — skipping image generation")
        return None

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai package not installed — skipping image generation")
        return None

    try:
        prompt = _build_prompt(post_content, topic_name, post_format)
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract the first image part from the response
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                logger.info("Image generated successfully for topic '%s'", topic_name)
                return part.inline_data.data  # bytes (PNG)

        logger.warning("Gemini returned no image parts for topic '%s'", topic_name)
        return None

    except Exception as exc:
        logger.exception("Image generation failed for topic '%s': %s", topic_name, exc)
        return None


def _build_prompt(post_content: str, topic_name: str, post_format: str) -> str:
    """Builds a detailed prompt from post metadata and content."""
    visual_style = _FORMAT_STYLES.get(post_format, "professional business infographic")
    snippet = post_content[:250].replace("\n", " ").strip()

    return (
        f"Create a professional LinkedIn post infographic about {topic_name}. "
        f"Visual style: {visual_style}. "
        f"Content theme: {snippet}. "
        "Design requirements: "
        "dark navy blue and white color palette, "
        "minimalist modern corporate design, "
        "no human faces or people, "
        "abstract data visuals or icons only, "
        "clean typography with key stats or keywords, "
        "premium business look suitable for a financial markets or AI executive audience, "
        "high resolution, sharp edges, gradient accents."
    )
