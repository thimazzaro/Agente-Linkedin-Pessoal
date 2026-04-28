"""
Second-pass safety review — Claude checks its own output for copyright and policy issues.
Runs as a fast, separate call with a focused prompt.
Returns the post unchanged if it passes, or raises SafetyError with reason.
"""
import os
import json
import anthropic
from dataclasses import dataclass
from typing import List


class SafetyError(Exception):
    """Raised when a post fails safety review and cannot be published."""


@dataclass
class SafetyResult:
    passed: bool
    issues: List[str]
    severity: str   # "ok" | "warning" | "block"


SAFETY_SYSTEM = """You are a compliance reviewer for LinkedIn posts.
Evaluate the post against these rules and return a JSON result.

Rules to check:
1. COPYRIGHT: Does the post reproduce verbatim sentences (>15 words) from a news article?
2. FINANCIAL ADVICE: Does it recommend buying, selling, or investing in specific securities?
3. DEFAMATION: Does it make unverified negative claims about specific individuals or companies?
4. SENSITIVE TOPICS: Does it express political opinions, discuss active legal cases, or cover medical topics?
5. MISLEADING: Does it present speculation as fact without qualification?

Return JSON:
{
  "passed": true/false,
  "issues": ["<description of each issue found>"],
  "severity": "ok" | "warning" | "block"
}

severity = "ok" if no issues.
severity = "warning" if minor issues that could be fixed with light editing.
severity = "block" if the post should not be published as-is (serious copyright or legal risk)."""


def safety_review(post_text: str) -> SafetyResult:
    """
    Runs a focused safety check on the generated post.
    Fast — uses a short focused prompt with no caching needed.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",   # Haiku is fast and cheap for structured checks
        max_tokens=512,
        system=SAFETY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Review this LinkedIn post:\n\n{post_text}",
            }
        ],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    data = json.loads(raw)
    result = SafetyResult(
        passed=data.get("passed", False),
        issues=data.get("issues", []),
        severity=data.get("severity", "block"),
    )

    if result.severity == "block":
        raise SafetyError(
            "Post blocked by safety review:\n" + "\n".join(f"- {i}" for i in result.issues)
        )

    return result
