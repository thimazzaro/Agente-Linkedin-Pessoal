"""
Generates LinkedIn posts using Claude.
System prompt is cached (ephemeral) — saves tokens on rewrites.
Model: claude-sonnet-4-6 — best cost/quality ratio for structured long-form text.
"""
import os
import json
from typing import List, Optional
import anthropic
from config.schema import AgentConfig, PostFormatConfig
from .researcher import SearchResult

FORMAT_INSTRUCTIONS = {
    "analysis": (
        "Write an analysis or opinion piece. Open with a bold assertion, "
        "develop the argument with data or examples from the sources, and close with implications."
    ),
    "list": (
        "Write a numbered list post (e.g., '5 things about X'). "
        "Each item should be a concise, standalone insight. "
        "Add a short intro and a brief closing paragraph."
    ),
    "news_context": (
        "Summarize recent news and add essential context a business audience needs. "
        "Explain *why* this matters, not just *what* happened."
    ),
    "trend": (
        "Identify an emerging trend from the sources. Describe the signal, the trajectory, "
        "and what business leaders should watch for."
    ),
    "week_wrap": (
        "Write a week-in-review post. Highlight 2–3 key developments of the week in this topic "
        "and draw a connecting thread or takeaway."
    ),
}

EMOJI_RULES = {
    "none": "Do not use any emojis.",
    "minimal": "Use at most 2 emojis, only where they add clarity, never decoratively.",
    "moderate": "Use emojis to structure the post (e.g., bullet markers), up to 5 total.",
}


def _build_system_prompt(cfg: AgentConfig) -> str:
    fmt = cfg.post_format
    safety = cfg.safety
    profile = cfg.profile

    voice_instruction = (
        "Write in first person (I, my, we)."
        if profile.voice == "first_person"
        else "Write in third person or impersonal constructions. Avoid 'I' statements."
    )

    tone_map = {
        "formal": "Use formal, professional language throughout.",
        "semi_formal": "Use a professional but conversational tone — authoritative yet approachable.",
        "informal": "Write in a casual, conversational style.",
    }

    safety_rules = []
    if safety.no_financial_advice:
        safety_rules.append(
            "Never give specific financial advice. Do not say 'buy', 'sell', 'invest in', "
            "or recommend specific securities. Frame everything as analysis, not advice."
        )
    if safety.no_political:
        safety_rules.append("Avoid political opinions, party references, or electoral topics.")
    if safety.cite_sources:
        safety_rules.append(
            "Always attribute key claims to a source using 'according to [Publication]' "
            "or 'as reported by [Publication]'. Include the source URL at the end."
        )
    safety_rules.append(
        f"Never reproduce more than {safety.max_verbatim_pct}% of any source text verbatim. "
        "Synthesize and paraphrase; do not plagiarize."
    )

    return f"""You are a LinkedIn content writer for {profile.name}, a {profile.role}.

VOICE: {voice_instruction}
TONE: {tone_map[profile.tone]}
LANGUAGE: Write entirely in {profile.language}.

LENGTH: Between {fmt.min_words} and {fmt.max_words} words. Count carefully.
EMOJIS: {EMOJI_RULES[fmt.emojis]}
HASHTAGS: Include at most {fmt.hashtags_max} hashtags, only the most relevant. Place them at the very end.

SAFETY AND COPYRIGHT RULES:
{chr(10).join(f'- {r}' for r in safety_rules)}

OUTPUT FORMAT:
Return a JSON object with exactly these fields:
{{
  "post": "<the LinkedIn post text, ready to publish>",
  "sources": ["<url1>", "<url2>"]
}}
Do not include any text outside the JSON object."""


def generate_post(
    cfg: AgentConfig,
    topic_name: str,
    post_format: str,
    articles: List[SearchResult],
    feedback: Optional[str] = None,
    previous_post: Optional[str] = None,
    cta: bool = False,
) -> tuple[str, List[str]]:
    """
    Generates (or rewrites) a LinkedIn post.
    Returns (post_text, source_urls).
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system_prompt = _build_system_prompt(cfg)

    # Prepare article summaries for the user message
    article_blocks = []
    for i, art in enumerate(articles, 1):
        block = f"[Article {i}]\nTitle: {art.title}\nURL: {art.url}\n\nContent:\n{art.content[:2000]}"
        if art.published_date:
            block = f"Published: {art.published_date}\n" + block
        article_blocks.append(block)
    articles_text = "\n\n---\n\n".join(article_blocks)

    format_instruction = FORMAT_INSTRUCTIONS.get(post_format, FORMAT_INSTRUCTIONS["analysis"])

    cta_instruction = (
        "\nEnd with a genuine question to the audience to encourage engagement."
        if cta else ""
    )

    rewrite_section = ""
    if feedback and previous_post:
        rewrite_section = f"""
This is a REWRITE request. The previous draft was:

--- PREVIOUS DRAFT ---
{previous_post}
--- END DRAFT ---

The editor's feedback:
{feedback}

Address all feedback points in the rewrite."""

    user_message = f"""Topic: {topic_name}
Post format today: {format_instruction}{cta_instruction}
{rewrite_section}

Here are today's source articles:

{articles_text}

Write the LinkedIn post now."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                # Cache the system prompt — it's identical across generation + rewrites
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    parsed = json.loads(raw)
    return parsed["post"], parsed.get("sources", [])
