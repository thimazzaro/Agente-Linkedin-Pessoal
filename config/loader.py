"""
Loads AgentConfig from a YAML file.
CONFIG_PATH env var points to the file; defaults to config.yaml in project root.
"""
import os
from pathlib import Path
import yaml
from .schema import AgentConfig


def load_config(path: str | None = None) -> AgentConfig:
    config_path = Path(path or os.getenv("CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            "Copy config.yaml.example to config.yaml and fill in your values."
        )
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return AgentConfig.model_validate(raw)
