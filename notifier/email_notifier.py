"""
Sends approval emails via Gmail SMTP.
Uses SMTP_USER + SMTP_APP_PASSWORD env vars (Gmail App Password, not account password).
APP_BASE_URL must be set to the Railway deployment URL so review links work.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_connection() -> smtplib.SMTP_SSL:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_APP_PASSWORD"]
    conn = smtplib.SMTP_SSL(smtp_host, smtp_port)
    conn.login(user, password)
    return conn


def _base_url() -> str:
    url = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    return url


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
    """
    Sends the draft post to the approver with Approve / Request Changes links.
    """
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
        If the button above doesn't work, copy and paste this link into your browser:<br>
        <code style="background:#f0f0f0;padding:4px 8px;border-radius:4px;word-break:break-all;">{review_url}</code>
      </p>
      <p style="color:#888;font-size:12px;">
        This post will be published at {os.getenv("PUBLISH_TIME_DISPLAY","09:00 BRT")} if approved before then.<br>
        Post ID: {post_id}
      </p>
    </body></html>
    """

    _send(to=to, subject=subject, html=html)


def send_published_notification(to: str, topic_name: str, linkedin_url: str) -> None:
    """Confirms to the user that the post was published."""
    subject = f"✓ Published on LinkedIn — {topic_name}"
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;">
      <h2 style="color:#0077b5;">Post published!</h2>
      <p>Your LinkedIn post about <strong>{topic_name}</strong> is now live.</p>
      <p><a href="{linkedin_url}">View on LinkedIn →</a></p>
    </body></html>
    """
    _send(to=to, subject=subject, html=html)


def _send(to: str, subject: str, html: str) -> None:
    user = os.environ["SMTP_USER"]
    sender_name = os.getenv("SMTP_SENDER_NAME", "LinkedIn Agent")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{user}>"
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    with _smtp_connection() as conn:
        conn.sendmail(user, to, msg.as_string())
