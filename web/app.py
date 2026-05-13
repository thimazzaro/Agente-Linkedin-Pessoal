"""
FastAPI web app — serves the post approval UI and handles approve/feedback actions.
APScheduler runs the daily generation and publishing jobs inside this process.
Hosted on Railway (always-on), so the scheduler never misses a beat.
"""
import os
import json
import logging
from datetime import datetime, date
from contextlib import asynccontextmanager

import pytz
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import load_config
from database.models import init_db, SessionLocal, Post, PostStatus
from agent.researcher import research_topic
from agent.writer import generate_post
from agent.safety import safety_review, SafetyError
from agent.scheduler_logic import get_next_topic, get_today_format, should_include_cta
from agent.linkedin_publisher import publish_post, LinkedInError
from agent.image_generator import generate_post_image
from notifier.email_notifier import send_review_email, send_published_notification
from web.security import (
    SecurityHeadersMiddleware,
    validate_startup_secrets,
    is_token_expired,
    is_valid_uuid,
    sanitize_feedback,
    rate_limiter,
)

logger = logging.getLogger("linkedin_agent")
security_logger = logging.getLogger("linkedin_agent.security")
logging.basicConfig(level=logging.INFO)

cfg = load_config()
templates = Jinja2Templates(directory="web/templates")
scheduler = AsyncIOScheduler()

MAX_SAFETY_RETRIES = 3


# ── Publish helper (shared by scheduled job and immediate approval) ────────────

async def _publish_single_post(post_id: str) -> None:
    """Publishes a single approved post. Used by both the cron job and immediate approval."""
    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post or post.status != PostStatus.approved:
            return

        # Load image bytes if available
        image_bytes: bytes | None = None
        if post.image_path and os.path.exists(post.image_path):
            try:
                with open(post.image_path, "rb") as fh:
                    image_bytes = fh.read()
            except OSError as exc:
                logger.warning("Could not read image %s: %s", post.image_path, exc)

        result = publish_post(text=post.content, image_bytes=image_bytes)
        post.status = PostStatus.published
        post.linkedin_post_id = result.post_id
        post.published_at = datetime.utcnow()
        db.commit()

        send_published_notification(
            to=cfg.approval.email,
            topic_name=post.topic_name,
            linkedin_url=result.url,
        )
        logger.info("Published post %s → %s", post.id, result.url)

    except LinkedInError as exc:
        post = db.get(Post, post_id)
        if post:
            post.status = PostStatus.failed
            db.commit()
        logger.error("LinkedIn publish failed for %s: %s", post_id, exc)
    except Exception as exc:
        logger.exception("_publish_single_post failed for %s: %s", post_id, exc)
    finally:
        db.close()


# ── Core agent job ────────────────────────────────────────────────────────────

async def run_generation_job() -> None:
    """Researches, writes, safety-checks, optionally generates an image, and emails the draft."""
    logger.info("Generation job started")
    db = SessionLocal()
    try:
        topic = get_next_topic(cfg, db)
        post_format = get_today_format(cfg)
        cta = should_include_cta(cfg, db)

        logger.info("Topic: %s | Format: %s | CTA: %s", topic.name, post_format, cta)

        exclude_urls: list[str] = []
        post_text = sources = warnings = None

        for attempt in range(1, MAX_SAFETY_RETRIES + 1):
            articles = research_topic(topic, max_results=5, exclude_urls=exclude_urls or None)
            if not articles:
                logger.warning("No articles found — skipping today")
                return

            post_text, sources = generate_post(
                cfg=cfg,
                topic_name=topic.name,
                post_format=post_format,
                articles=articles,
                cta=cta,
            )

            warnings = []
            try:
                safety_result = safety_review(post_text)
                warnings = safety_result.issues
                break
            except SafetyError:
                exclude_urls.extend(sources)
                if attempt == MAX_SAFETY_RETRIES:
                    logger.error(
                        "Safety blocked all %d attempts — skipping today", MAX_SAFETY_RETRIES
                    )
                    return
                logger.warning(
                    "Safety blocked attempt %d/%d, retrying with different sources",
                    attempt, MAX_SAFETY_RETRIES,
                )

        post = Post(
            agent_id=cfg.agent_id,
            topic_name=topic.name,
            post_format=post_format,
            content=post_text,
            sources=json.dumps(sources),
            status=PostStatus.pending_review,
            scheduled_date=date.today(),
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        # Generate image asynchronously-ish (blocking but fast ~5-10s)
        image_bytes = generate_post_image(post_text, topic.name, post_format)
        if image_bytes:
            image_path = f"data/images/{post.id}.jpg"
            try:
                with open(image_path, "wb") as fh:
                    fh.write(image_bytes)
                post.image_path = image_path
                db.commit()
                logger.info("Post image saved: %s", image_path)
            except OSError as exc:
                logger.warning("Could not save image: %s", exc)

        send_review_email(
            to=cfg.approval.email,
            post_id=post.id,
            review_token=post.review_token,
            topic_name=topic.name,
            post_format=post_format,
            post_content=post_text,
            rewrite_count=0,
            safety_warnings=warnings or None,
        )
        logger.info("Draft sent for review. Post ID: %s", post.id)

    except Exception as exc:
        logger.exception("Generation job failed: %s", exc)
    finally:
        db.close()


async def run_publish_job() -> None:
    """Publishes all approved posts scheduled for today (09:00 cron)."""
    logger.info("Publish job started")
    db = SessionLocal()
    try:
        today_posts = (
            db.query(Post)
            .filter(
                Post.agent_id == cfg.agent_id,
                Post.status == PostStatus.approved,
                Post.scheduled_date == date.today(),
            )
            .all()
        )
        post_ids = [p.id for p in today_posts]
    finally:
        db.close()

    for post_id in post_ids:
        await _publish_single_post(post_id)


# ── Rewrite job (triggered by feedback) ──────────────────────────────────────

async def run_rewrite_job(post_id: str) -> None:
    """Regenerates a post using the user's feedback."""
    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post or not post.last_feedback:
            return

        topic_cfg = next(
            (t for t in cfg.topics.items if t.name == post.topic_name),
            cfg.topics.items[0],
        )
        articles = research_topic(topic_cfg, max_results=5)

        new_text, new_sources = generate_post(
            cfg=cfg,
            topic_name=post.topic_name,
            post_format=post.post_format,
            articles=articles,
            feedback=post.last_feedback,
            previous_post=post.content,
        )

        warnings: list[str] = []
        try:
            safety_result = safety_review(new_text)
            warnings = safety_result.issues
        except SafetyError as exc:
            logger.error("Rewrite blocked by safety: %s", exc)
            return

        post.content = new_text
        post.sources = json.dumps(new_sources)
        post.rewrite_count += 1
        post.status = PostStatus.pending_review

        # Regenerate image for the rewrite
        image_bytes = generate_post_image(new_text, post.topic_name, post.post_format)
        if image_bytes:
            image_path = f"data/images/{post.id}.jpg"
            try:
                with open(image_path, "wb") as fh:
                    fh.write(image_bytes)
                post.image_path = image_path
            except OSError as exc:
                logger.warning("Could not save rewrite image: %s", exc)

        db.commit()

        send_review_email(
            to=cfg.approval.email,
            post_id=post.id,
            review_token=post.review_token,
            topic_name=post.topic_name,
            post_format=post.post_format,
            post_content=new_text,
            rewrite_count=post.rewrite_count,
            safety_warnings=warnings or None,
        )
        logger.info("Rewrite #%d sent for review. Post ID: %s", post.rewrite_count, post.id)

    except Exception as exc:
        logger.exception("Rewrite job failed: %s", exc)
    finally:
        db.close()


# ── App lifespan (scheduler setup) ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_secrets()
    init_db()
    tz = pytz.timezone(cfg.schedule.timezone)

    gen_h, gen_m = cfg.schedule.generate_time.split(":")
    pub_h, pub_m = cfg.schedule.publish_time.split(":")
    days = ",".join(d[:3] for d in cfg.schedule.days)

    scheduler.add_job(
        run_generation_job,
        CronTrigger(day_of_week=days, hour=gen_h, minute=gen_m, timezone=tz),
        id="generation",
        replace_existing=True,
    )
    scheduler.add_job(
        run_publish_job,
        CronTrigger(day_of_week=days, hour=pub_h, minute=pub_m, timezone=tz),
        id="publish",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — generate at %s, publish at %s (%s)",
        cfg.schedule.generate_time, cfg.schedule.publish_time, cfg.schedule.timezone,
    )
    yield
    scheduler.shutdown()


app = FastAPI(title="LinkedIn Agent", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")


def _check_rate_limit(key: str, max_req: int = 10, window: int = 60, request: Request = None):
    ip = _get_client_ip(request) if request else "unknown"
    if not rate_limiter.is_allowed(f"{key}:{ip}", max_req, window):
        security_logger.warning("Rate limit hit: %s from %s", key, ip)
        raise HTTPException(status_code=429, detail="Too many requests. Try again later.")


def _validate_post_token(post_id: str, token: str, request: Request) -> Post:
    """Load post, validate UUID + token + expiry. Raises 400/403 on failure."""
    if not is_valid_uuid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format.")

    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
    finally:
        db.close()

    if not post or post.review_token != token:
        ip = _get_client_ip(request)
        security_logger.warning(
            "Invalid token for post %s from %s", post_id, ip
        )
        raise HTTPException(status_code=403, detail="Invalid or expired review link.")

    if is_token_expired(post.created_at):
        raise HTTPException(
            status_code=403,
            detail="This review link has expired (older than 72 h). Contact the agent admin.",
        )

    return post


# ── Web routes ────────────────────────────────────────────────────────────────

@app.get("/review/{post_id}", response_class=HTMLResponse)
async def review_page(request: Request, post_id: str, token: str):
    _check_rate_limit("review", max_req=30, window=60, request=request)

    if not is_valid_uuid(post_id):
        return HTMLResponse("<h2>Invalid link.</h2>", status_code=400)

    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post or post.review_token != token:
            return HTMLResponse("<h2>Invalid or expired link.</h2>", status_code=403)
        if is_token_expired(post.created_at):
            return HTMLResponse(
                "<h2>Review link expired (72 h). Please request a new draft.</h2>",
                status_code=403,
            )
        post_data = {
            "id": post.id,
            "topic_name": post.topic_name,
            "post_format": post.post_format,
            "content": post.content,
            "rewrite_count": post.rewrite_count,
            "scheduled_date": post.scheduled_date,
            "status": post.status,
        }
    finally:
        db.close()

    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={"post": post_data, "token": token},
    )


@app.post("/approve/{post_id}")
async def approve_post(request: Request, post_id: str, token: str = Form(...)):
    _check_rate_limit("approve", max_req=5, window=60, request=request)
    post = _validate_post_token(post_id, token, request)

    if post.status not in (PostStatus.pending_review, PostStatus.rewrite_requested):
        return HTMLResponse("<h2>This post was already processed.</h2>")

    # Mark approved
    db = SessionLocal()
    try:
        p = db.get(Post, post_id)
        p.status = PostStatus.approved
        p.approved_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    # Decide: immediate publish or wait for 09:00 cron
    tz = pytz.timezone(cfg.schedule.timezone)
    now_local = datetime.now(tz)
    pub_h, pub_m = cfg.schedule.publish_time.split(":")
    publish_dt = now_local.replace(
        hour=int(pub_h), minute=int(pub_m), second=0, microsecond=0
    )

    if now_local >= publish_dt:
        # Past scheduled time — publish immediately in background
        scheduler.add_job(
            _publish_single_post,
            args=[post_id],
            id=f"immediate_pub_{post_id}",
            replace_existing=True,
        )
        return HTMLResponse(
            "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
            "<h2 style='color:#0077b5'>✓ Post aprovado!</h2>"
            "<p>O horário agendado já passou — publicando <strong>agora mesmo</strong>.</p>"
            "<p style='color:#888;font-size:13px'>Você receberá um e-mail de confirmação em instantes.</p>"
            "</body></html>"
        )

    pub_display = os.getenv("PUBLISH_TIME_DISPLAY", cfg.schedule.publish_time)
    return HTMLResponse(
        "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
        "<h2 style='color:#0077b5'>✓ Post aprovado!</h2>"
        f"<p>Será publicado às <strong>{pub_display}</strong>.</p>"
        "</body></html>"
    )


@app.post("/feedback/{post_id}")
async def submit_feedback(
    request: Request,
    post_id: str,
    token: str = Form(...),
    feedback: str = Form(...),
):
    _check_rate_limit("feedback", max_req=5, window=60, request=request)
    _validate_post_token(post_id, token, request)

    clean_feedback = sanitize_feedback(feedback, max_length=500)
    if not clean_feedback:
        raise HTTPException(status_code=400, detail="Feedback cannot be empty.")

    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post or post.review_token != token:
            raise HTTPException(status_code=403, detail="Invalid link.")

        if post.rewrite_count >= cfg.approval.max_rewrites:
            post.status = PostStatus.rejected
            db.commit()
            return HTMLResponse(
                "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
                "<h2>Max rewrites reached. Post rejected.</h2>"
                "</body></html>"
            )

        post.last_feedback = clean_feedback
        post.status = PostStatus.rewrite_requested
        db.commit()
    finally:
        db.close()

    scheduler.add_job(
        run_rewrite_job,
        args=[post_id],
        id=f"rewrite_{post_id}",
        replace_existing=True,
    )

    return HTMLResponse(
        "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
        "<h2 style='color:#0077b5'>Feedback recebido!</h2>"
        "<p>Um novo rascunho será enviado por e-mail em instantes.</p>"
        "</body></html>"
    )


@app.get("/trigger/generate")
async def manual_trigger_generate(request: Request, secret: str):
    _check_rate_limit("trigger", max_req=10, window=3600, request=request)
    if secret != os.environ.get("TRIGGER_SECRET", "changeme"):
        security_logger.warning("Failed trigger auth from %s", _get_client_ip(request))
        raise HTTPException(status_code=401)
    scheduler.add_job(run_generation_job, id="manual_gen", replace_existing=True)
    return {"status": "generation job queued"}


@app.get("/trigger/publish")
async def manual_trigger_publish(request: Request, secret: str):
    _check_rate_limit("trigger", max_req=10, window=3600, request=request)
    if secret != os.environ.get("TRIGGER_SECRET", "changeme"):
        security_logger.warning("Failed trigger auth from %s", _get_client_ip(request))
        raise HTTPException(status_code=401)
    scheduler.add_job(run_publish_job, id="manual_pub", replace_existing=True)
    return {"status": "publish job queued"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent_id": cfg.agent_id}
