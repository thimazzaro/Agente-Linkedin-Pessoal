"""
Posts text (with optional image) to LinkedIn via the official REST API v2.
Requires:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 Bearer token (60-day TTL)
  LINKEDIN_PERSON_URN    — e.g., "urn:li:person:AbCdEfG12345"

Run scripts/setup_linkedin_auth.py once to obtain both values.
"""
import os
import logging
import requests
from dataclasses import dataclass

logger = logging.getLogger("linkedin_agent")


class LinkedInError(Exception):
    pass


@dataclass
class PublishResult:
    post_id: str   # LinkedIn post URN, e.g. "urn:li:share:123456789"
    url: str       # Direct link to the post


# ── Auth helpers ──────────────────────────────────────────────────────────────

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
    return f"urn:li:person:{resp.json()['id']}"


def _resolve_author_urn() -> str:
    urn = os.environ.get("LINKEDIN_PERSON_URN")
    return urn if urn else get_person_urn()


# ── Image upload ──────────────────────────────────────────────────────────────

def _upload_image(image_bytes: bytes, author_urn: str) -> str:
    """
    Registers and uploads an image to LinkedIn, returning the asset URN.
    LinkedIn Assets API v2 — requires SYNCHRONOUS_UPLOAD support.
    """
    # Step 1: register upload
    register_payload = {
        "registerUploadRequest": {
            "owner": author_urn,
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
            "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"],
        }
    }

    reg_resp = requests.post(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        headers=_get_headers(),
        json=register_payload,
        timeout=15,
    )
    if not reg_resp.ok:
        raise LinkedInError(
            f"Image register failed {reg_resp.status_code}: {reg_resp.text}"
        )

    reg_data = reg_resp.json()["value"]
    asset_urn: str = reg_data["asset"]
    upload_mechanism = reg_data["uploadMechanism"]
    upload_info = upload_mechanism.get(
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
    )
    upload_url: str = upload_info["uploadUrl"]

    # Step 2: upload binary
    upload_headers = {
        "Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN']}",
        "Content-Type": "application/octet-stream",
    }
    upload_resp = requests.put(
        upload_url,
        headers=upload_headers,
        data=image_bytes,
        timeout=30,
    )
    if not upload_resp.ok and upload_resp.status_code != 201:
        raise LinkedInError(
            f"Image upload failed {upload_resp.status_code}: {upload_resp.text}"
        )

    logger.info("Image uploaded to LinkedIn — asset: %s", asset_urn)
    return asset_urn


# ── Post payloads ─────────────────────────────────────────────────────────────

def _text_payload(text: str, author_urn: str) -> dict:
    return {
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


def _image_payload(text: str, asset_urn: str, author_urn: str) -> dict:
    return {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": [
                    {
                        "status": "READY",
                        "description": {"text": ""},
                        "media": asset_urn,
                        "title": {"text": ""},
                    }
                ],
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }


# ── Main publish function ─────────────────────────────────────────────────────

def publish_post(
    text: str,
    image_bytes: bytes | None = None,
    author_urn: str | None = None,
) -> PublishResult:
    """
    Publishes a post to LinkedIn, optionally with an image.

    image_bytes: raw JPEG/PNG bytes from Imagen (or None for text-only).
    author_urn:  LinkedIn person URN. Reads LINKEDIN_PERSON_URN env var if None.
    """
    if author_urn is None:
        author_urn = _resolve_author_urn()

    # Attempt image upload; fall back to text-only on failure
    payload = _text_payload(text, author_urn)
    if image_bytes:
        try:
            asset_urn = _upload_image(image_bytes, author_urn)
            payload = _image_payload(text, asset_urn, author_urn)
        except LinkedInError as exc:
            logger.warning("Image upload failed — publishing text-only: %s", exc)

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
    url = (
        f"https://www.linkedin.com/feed/update/{post_id}/"
        if post_id
        else "https://www.linkedin.com/feed/"
    )
    return PublishResult(post_id=post_id, url=url)
