"""
SQLite via SQLAlchemy — no external DB server needed.
File path is set by DATABASE_URL env var (defaults to ./data/agent.db).
"""
import os
import uuid
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, String, Text, Integer,
    Boolean, Date, DateTime, Enum as SAEnum
)
from sqlalchemy.orm import declarative_base, sessionmaker
import enum

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/agent.db")

# SQLite needs check_same_thread=False when used with async frameworks
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class PostStatus(str, enum.Enum):
    pending_review = "pending_review"     # Generated, email sent, waiting approval
    approved = "approved"                 # User approved, waiting publish time
    published = "published"              # Posted to LinkedIn
    rejected = "rejected"                # User rejected, no rewrite requested
    rewrite_requested = "rewrite_requested"  # User gave feedback, rewriting
    failed = "failed"                    # LinkedIn API or generation error


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False, default="default")

    # Content
    topic_name = Column(String, nullable=False)
    post_format = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)         # JSON list of source URLs
    rewrite_count = Column(Integer, default=0)
    last_feedback = Column(Text, nullable=True)

    # Approval
    review_token = Column(String, unique=True, default=lambda: str(uuid.uuid4()))
    status = Column(SAEnum(PostStatus), default=PostStatus.pending_review)

    # Scheduling
    scheduled_date = Column(Date, nullable=False, default=date.today)

    # LinkedIn
    linkedin_post_id = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)


class TopicState(Base):
    """Tracks which topic index was last used, per agent_id."""
    __tablename__ = "topic_state"

    agent_id = Column(String, primary_key=True)
    last_topic_index = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db() -> None:
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
