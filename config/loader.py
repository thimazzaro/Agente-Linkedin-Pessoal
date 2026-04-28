"""
Loads AgentConfig from a YAML file or the CONFIG_YAML environment variable.
Priority: CONFIG_YAML env var → CONFIG_PATH env var → config.yaml in project root.
For Railway/cloud: paste your config.yaml content into the CONFIG_YAML variable.
"""
import os
from pathlib import Path
import yaml
from .schema import AgentConfig


def load_config(path: str | None = None) -> AgentConfig:
    # Allow full YAML content to be passed as an env var (ideal for Railway)
    inline_yaml = os.getenv("CONFIG_YAML")
    if inline_yaml:
        raw = yaml.safe_load(inline_yaml)
        return AgentConfig.model_validate(raw)

    config_path = Path(path or os.getenv("CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Either set CONFIG_YAML env var with your config content, "
            "or copy config.yaml.example to config.yaml and fill in your values."
        )
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AgentConfig.model_validate(raw)
