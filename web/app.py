"""
FastAPI web app — serves the post approval UI and handles approve/feedback actions.
APScheduler runs the daily generation and publishing jobs inside this process.
Hosted on Railway (always-on), so the scheduler never misses a beat.
"""
import os
import json
import logging
from datetime import datetime, date, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import load_config
from database.models import init_db, SessionLocal, Post, PostStatus
from agent.researcher import research_topic
from agent.writer import generate_post
from agent.safety import safety_review, SafetyError
from agent.scheduler_logic import get_next_topic, get_today_format, should_include_cta
from agent.linkedin_publisher import publish_post, LinkedInError
from notifier.email_notifier import send_review_email, send_published_notification

logger = logging.getLogger("linkedin_agent")
logging.basicConfig(level=logging.INFO)

cfg = load_config()
templates = Jinja2Templates(directory="web/templates")
scheduler = AsyncIOScheduler()


# ── Core agent job ────────────────────────────────────────────────────────────

async def run_generation_job() -> None:
    """Researches, writes, safety-checks, and emails the daily draft for approval."""
    logger.info("Generation job started")
    db = SessionLocal()
    try:
        topic = get_next_topic(cfg, db)
        post_format = get_today_format(cfg)
        cta = should_include_cta(cfg, db)

        logger.info(f"Topic: {topic.name} | Format: {post_format} | CTA: {cta}")

        articles = research_topic(topic, max_results=5)
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

        warnings: list[str] = []
        try:
            safety_result = safety_review(post_text)
            warnings = safety_result.issues
        except SafetyError as e:
            logger.error(f"Safety check blocked post: {e}")
            return

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
        logger.info(f"Draft sent for review. Post ID: {post.id}")

    except Exception as e:
        logger.exception(f"Generation job failed: {e}")
    finally:
        db.close()


async def run_publish_job() -> None:
    """Publishes all approved posts scheduled for today."""
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

        for post in today_posts:
            try:
                result = publish_post(text=post.content)
                post.status = PostStatus.published
                post.linkedin_post_id = result.post_id
                post.published_at = datetime.utcnow()
                db.commit()

                send_published_notification(
                    to=cfg.approval.email,
                    topic_name=post.topic_name,
                    linkedin_url=result.url,
                )
                logger.info(f"Published post {post.id} → {result.url}")

            except LinkedInError as e:
                post.status = PostStatus.failed
                db.commit()
                logger.error(f"LinkedIn publish failed for {post.id}: {e}")

    except Exception as e:
        logger.exception(f"Publish job failed: {e}")
    finally:
        db.close()


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
        except SafetyError as e:
            logger.error(f"Rewrite blocked by safety: {e}")
            return

        post.content = new_text
        post.sources = json.dumps(new_sources)
        post.rewrite_count += 1
        post.status = PostStatus.pending_review
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
        logger.info(f"Rewrite #{post.rewrite_count} sent for review. Post ID: {post.id}")

    except Exception as e:
        logger.exception(f"Rewrite job failed: {e}")
    finally:
        db.close()


# ── App lifespan (scheduler setup) ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tz = pytz.timezone(cfg.schedule.timezone)

    gen_h, gen_m = cfg.schedule.generate_time.split(":")
    pub_h, pub_m = cfg.schedule.publish_time.split(":")
    days = ",".join(d[:3] for d in cfg.schedule.days)  # mon,tue,wed,thu,fri

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
        f"Scheduler started — generate at {cfg.schedule.generate_time}, "
        f"publish at {cfg.schedule.publish_time} ({cfg.schedule.timezone})"
    )
    yield
    scheduler.shutdown()


app = FastAPI(title="LinkedIn Agent", lifespan=lifespan)


# ── Web routes ────────────────────────────────────────────────────────────────

def _get_post_or_403(post_id: str, token: str) -> Post:
    db = SessionLocal()
    post = db.get(Post, post_id)
    db.close()
    if not post or post.review_token != token:
        raise HTTPException(status_code=403, detail="Invalid or expired review link.")
    return post


@app.get("/review/{post_id}", response_class=HTMLResponse)
async def review_page(request: Request, post_id: str, token: str):
    db = SessionLocal()
    try:
        post = db.get(Post, post_id)
        if not post or post.review_token != token:
            return HTMLResponse("<h2>Invalid or expired link.</h2>", status_code=403)
        # Extract all fields while session is open to avoid DetachedInstanceError
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
async def approve_post(post_id: str, token: str = Form(...)):
    db = SessionLocal()
    post = db.get(Post, post_id)
    if not post or post.review_token != token:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid link.")
    if post.status not in (PostStatus.pending_review, PostStatus.rewrite_requested):
        db.close()
        return HTMLResponse("<h2>This post was already processed.</h2>")

    post.status = PostStatus.approved
    post.approved_at = datetime.utcnow()
    db.commit()
    db.close()
    return HTMLResponse(
        "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
        "<h2 style='color:#0077b5'>✓ Post approved!</h2>"
        "<p>It will be published at the scheduled time.</p>"
        "</body></html>"
    )


@app.post("/feedback/{post_id}")
async def submit_feedback(post_id: str, token: str = Form(...), feedback: str = Form(...)):
    db = SessionLocal()
    post = db.get(Post, post_id)
    if not post or post.review_token != token:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid link.")

    if post.rewrite_count >= cfg.approval.max_rewrites:
        post.status = PostStatus.rejected
        db.commit()
        db.close()
        return HTMLResponse(
            "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
            "<h2>Max rewrites reached. Post rejected.</h2>"
            "</body></html>"
        )

    post.last_feedback = feedback
    post.status = PostStatus.rewrite_requested
    db.commit()
    db.close()

    # Trigger rewrite in the background
    scheduler.add_job(
        run_rewrite_job,
        args=[post_id],
        id=f"rewrite_{post_id}",
        replace_existing=True,
    )

    return HTMLResponse(
        "<html><body style='font-family:Arial;text-align:center;padding:60px'>"
        "<h2 style='color:#0077b5'>Feedback received!</h2>"
        "<p>A revised draft will be emailed to you shortly.</p>"
        "</body></html>"
    )


@app.get("/trigger/generate")
async def manual_trigger_generate(secret: str):
    """Manual trigger for testing — protected by TRIGGER_SECRET env var."""
    if secret != os.environ.get("TRIGGER_SECRET", "changeme"):
        raise HTTPException(status_code=401)
    scheduler.add_job(run_generation_job, id="manual_gen", replace_existing=True)
    return {"status": "generation job queued"}


@app.get("/trigger/publish")
async def manual_trigger_publish(secret: str):
    if secret != os.environ.get("TRIGGER_SECRET", "changeme"):
        raise HTTPException(status_code=401)
    scheduler.add_job(run_publish_job, id="manual_pub", replace_existing=True)
    return {"status": "publish job queued"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent_id": cfg.agent_id}
