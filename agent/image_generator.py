"""
Generates a professional image for LinkedIn posts using Google Gemini Imagen 3.

Requires:  GOOGLE_AI_API_KEY env var (Google AI Studio key).
Falls back gracefully to None if the key is absent or generation fails,
so the agent continues working without images.
"""
import os
import logging

logger = logging.getLogger("linkedin_agent")

# Aspect ratio optimised for LinkedIn feed images (landscape 1.91:1 or square 1:1)
_ASPECT_RATIO = "1:1"

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

    Returns JPEG/PNG bytes, or None when generation is skipped or fails.
    """
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        logger.info("GOOGLE_AI_API_KEY not configured — skipping image generation")
        return None

    try:
        from google import genai
        from google.genai import types as genai_types

        prompt = _build_prompt(post_content, topic_name, post_format)
        client = genai.Client(api_key=api_key)

        response = client.models.generate_images(
            model="imagen-3.0-generate-001",
            prompt=prompt,
            config=genai_types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=_ASPECT_RATIO,
                safety_filter_level="block_some",
                person_generation="dont_allow",
            ),
        )

        if response.generated_images:
            logger.info("Image generated successfully for topic '%s'", topic_name)
            return response.generated_images[0].image.image_bytes

        logger.warning("Imagen returned no images for topic '%s'", topic_name)
        return None

    except ImportError:
        logger.warning("google-genai package not installed — skipping image generation")
        return None
    except Exception as exc:
        logger.warning("Image generation failed: %s", exc)
        return None


def _build_prompt(post_content: str, topic_name: str, post_format: str) -> str:
    """Builds a detailed Imagen prompt from post metadata and content."""
    visual_style = _FORMAT_STYLES.get(post_format, "professional business infographic")
    # Use only the first 250 chars to keep the prompt tight
    snippet = post_content[:250].replace("\n", " ").strip()

    return (
        f"Professional LinkedIn post infographic about {topic_name}. "
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
