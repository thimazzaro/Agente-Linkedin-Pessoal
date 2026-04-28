"""
Posts text to LinkedIn via the official REST API v2.
Requires:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 Bearer token (60-day TTL)
  LINKEDIN_PERSON_URN    — e.g., "urn:li:person:AbCdEfG12345"

Run scripts/setup_linkedin_auth.py once to obtain both values.
"""
import os
import requests
from dataclasses import dataclass


class LinkedInError(Exception):
    pass


@dataclass
class PublishResult:
    post_id: str       # LinkedIn post URN, e.g. "urn:li:share:123456789"
    url: str           # Direct link to the post


def _get_headers() -> dict:
    token = os.environ["LINKEDIN_ACCESS_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def get_person_urn() -> str:
    """Fetches the authenticated user's LinkedIn person URN."""
    resp = requests.get(
        "https://api.linkedin.com/v2/me",
        headers=_get_headers(),
        timeout=10,
    )
    if not resp.ok:
        raise LinkedInError(f"Failed to fetch LinkedIn profile: {resp.status_code} {resp.text}")
    data = resp.json()
    return f"urn:li:person:{data['id']}"


def publish_post(text: str, author_urn: str | None = None) -> PublishResult:
    """
    Publishes a text-only post to LinkedIn.
    author_urn: LinkedIn person URN. If None, reads from LINKEDIN_PERSON_URN env var.
    """
    if author_urn is None:
        author_urn = os.environ.get("LINKEDIN_PERSON_URN")
        if not author_urn:
            author_urn = get_person_urn()

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    resp = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers=_get_headers(),
        json=payload,
        timeout=15,
    )

    if not resp.ok:
        raise LinkedInError(
            f"LinkedIn API error {resp.status_code}: {resp.text}"
        )

    post_id = resp.headers.get("x-restli-id", "")
    # Construct a best-effort profile URL (exact post URL requires the numeric ID)
    url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "https://www.linkedin.com/feed/"
    return PublishResult(post_id=post_id, url=url)
