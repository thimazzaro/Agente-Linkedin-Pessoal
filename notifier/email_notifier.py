"""
Sends approval emails via Resend (https://resend.com).
Resend uses HTTPS — works on Railway where direct SMTP is blocked.
Requires: RESEND_API_KEY env var.
Optional: EMAIL_FROM (defaults to onboarding@resend.dev for testing).
"""
import os
import resend


def _send(to: str, subject: str, html: str) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    sender = os.getenv("EMAIL_FROM", "LinkedIn Agent <onboarding@resend.dev>")
    resend.Emails.send({"from": sender, "to": to, "subject": subject, "html": html})


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")


def send_review_email(
    to: str,
    post_id: str,
    review_token: str,
    topic_name: str,
    post_format: str,
    post_content: str,
    rewrite_count: int = 0,
    safety_warnings: list[str] | None = None,
) -> None:
    base = _base_url()
    review_url = f"{base}/review/{post_id}?token={review_token}"

    subject_prefix = f"[REWRITE #{rewrite_count}] " if rewrite_count > 0 else ""
    subject = f"{subject_prefix}LinkedIn Draft — {topic_name} ({post_format.replace('_', ' ').title()})"

    warning_block = ""
    if safety_warnings:
        items = "".join(f"<li>{w}</li>" for w in safety_warnings)
        warning_block = f"""
        <div style="background:#fff3cd;border:1px solid #ffc107;padding:12px;border-radius:6px;margin-bottom:16px;">
          <strong>⚠ Safety warnings (non-blocking):</strong><ul>{items}</ul>
        </div>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#333;">
      <h2 style="color:#0077b5;">LinkedIn Post Draft</h2>
      <p><strong>Topic:</strong> {topic_name} &nbsp;|&nbsp; <strong>Format:</strong> {post_format.replace("_", " ").title()}</p>
      {warning_block}
      <div style="background:#f5f5f5;border-left:4px solid #0077b5;padding:16px;white-space:pre-wrap;border-radius:4px;font-size:15px;line-height:1.6;">
{post_content}
      </div>
      <br>
      <p>
        <a href="{review_url}" style="background:#0077b5;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;display:inline-block;">
          Review &amp; Approve / Request Changes
        </a>
      </p>
      <p style="font-size:13px;color:#555;">
        If the button above doesn't work, copy and paste this link:<br>
        <code style="background:#f0f0f0;padding:4px 8px;border-radius:4px;word-break:break-all;">{review_url}</code>
      </p>
      <p style="color:#888;font-size:12px;">
        Post will be published at {os.getenv("PUBLISH_TIME_DISPLAY", "09:00 BRT")} if approved before then.<br>
        Post ID: {post_id}
      </p>
    </body></html>
    """

    _send(to=to, subject=subject, html=html)


def send_published_notification(to: str, topic_name: str, linkedin_url: str) -> None:
    subject = f"✓ Published on LinkedIn — {topic_name}"
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;">
      <h2 style="color:#0077b5;">Post published!</h2>
      <p>Your LinkedIn post about <strong>{topic_name}</strong> is now live.</p>
      <p><a href="{linkedin_url}">View on LinkedIn →</a></p>
    </body></html>
    """
    _send(to=to, subject=subject, html=html)
