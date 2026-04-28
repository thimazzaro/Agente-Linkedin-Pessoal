"""
Determines which topic and post format to use today.
Topic rotation is persisted in the DB so it survives restarts.
Format is determined by weekday — configurable via config.yaml.
"""
from datetime import date
from sqlalchemy.orm import Session
from config.schema import AgentConfig, Topic
from database.models import TopicState


def get_next_topic(cfg: AgentConfig, db: Session) -> Topic:
    """
    Returns the next topic in the rotation.
    Updates the TopicState record so the next call picks the following topic.
    """
    state = db.get(TopicState, cfg.agent_id)
    topics = cfg.topics.items

    if cfg.topics.rotation == "alternating":
        if state is None:
            current_index = 0
            state = TopicState(agent_id=cfg.agent_id, last_topic_index=0)
            db.add(state)
        else:
            current_index = state.last_topic_index

        topic = topics[current_index % len(topics)]
        next_index = (current_index + 1) % len(topics)
        state.last_topic_index = next_index
        db.commit()
        return topic

    elif cfg.topics.rotation == "random":
        import random
        return random.choice(topics)

    return topics[0]


def get_today_format(cfg: AgentConfig) -> str:
    """Returns the post format name for today's weekday."""
    day_map = {
        0: cfg.post_format.week_schedule.monday,
        1: cfg.post_format.week_schedule.tuesday,
        2: cfg.post_format.week_schedule.wednesday,
        3: cfg.post_format.week_schedule.thursday,
        4: cfg.post_format.week_schedule.friday,
    }
    return day_map.get(date.today().weekday(), "analysis")


def should_include_cta(cfg: AgentConfig, db: Session) -> bool:
    """
    Returns True on every Nth post (N = cta_frequency).
    Uses total published + approved post count to determine the cycle.
    """
    if cfg.post_format.cta_frequency == 0:
        return False
    from database.models import Post, PostStatus
    count = db.query(Post).filter(
        Post.agent_id == cfg.agent_id,
        Post.status.in_([PostStatus.published, PostStatus.approved]),
    ).count()
    return (count % cfg.post_format.cta_frequency) == 0
