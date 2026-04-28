"""
Config schema — every value that drives agent behavior lives here.
Adding a new user = new config.yaml. No code changes needed.
"""
from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, field_validator


class Profile(BaseModel):
    name: str
    role: str                          # Shown in system prompt to shape tone
    bio: Optional[str] = None          # Optional extended context for the LLM
    voice: Literal["first_person", "third_person"] = "third_person"
    tone: Literal["formal", "semi_formal", "informal"] = "semi_formal"
    language: str = "en"               # ISO 639-1 code


class Topic(BaseModel):
    name: str
    keywords: List[str]                # Used to build search queries
    sources: Optional[List[str]] = None  # Restrict Tavily to these domains
    description: Optional[str] = None   # Extra context for the LLM


class TopicsConfig(BaseModel):
    rotation: Literal["alternating", "random"] = "alternating"
    items: List[Topic]

    @field_validator("items")
    @classmethod
    def at_least_one(cls, v: List[Topic]) -> List[Topic]:
        if not v:
            raise ValueError("At least one topic required")
        return v


class WeekSchedule(BaseModel):
    monday: str = "analysis"
    tuesday: str = "list"
    wednesday: str = "news_context"
    thursday: str = "trend"
    friday: str = "week_wrap"


class PostFormatConfig(BaseModel):
    min_words: int = 400
    max_words: int = 600
    emojis: Literal["none", "minimal", "moderate"] = "minimal"
    hashtags_max: int = 4
    cta_frequency: int = 2             # CTA on every Nth post (0 = never)
    week_schedule: WeekSchedule = WeekSchedule()


class ScheduleConfig(BaseModel):
    generate_time: str = "06:00"       # Local time to generate + email draft
    publish_time: str = "09:00"        # Local time to publish if approved
    timezone: str = "America/Sao_Paulo"
    days: List[str] = ["monday", "tuesday", "wednesday", "thursday", "friday"]


class ApprovalConfig(BaseModel):
    email: str                         # Where to send drafts for review
    auto_publish_if_no_response: bool = False
    max_rewrites: int = 3              # Max feedback rounds before dropping post


class LinkedInConfig(BaseModel):
    profile_type: Literal["personal", "company"] = "personal"


class SafetyConfig(BaseModel):
    no_financial_advice: bool = True   # Block "buy X" / "sell Y" language
    no_political: bool = True
    cite_sources: bool = True
    max_verbatim_pct: int = 15         # Claude instructed to stay below this


class AgentConfig(BaseModel):
    agent_id: str = "default"          # Unique ID for multi-tenant logging
    profile: Profile
    topics: TopicsConfig
    post_format: PostFormatConfig = PostFormatConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    approval: ApprovalConfig
    linkedin: LinkedInConfig = LinkedInConfig()
    safety: SafetyConfig = SafetyConfig()
