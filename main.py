"""
Entry point — starts the FastAPI app with Uvicorn.
Railway calls this via the Dockerfile CMD.
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env before any module reads os.environ

import os
import sys
import asyncio
import uvicorn

# Python 3.12+ on Windows defaults to ProactorEventLoop which breaks APScheduler.
# SelectorEventLoop is required for async scheduler compatibility.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Route ALL logs (uvicorn + app) to stdout so Railway reports severity correctly.
# By default uvicorn writes to stderr, which Railway tags as "error" regardless of level.
_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": False,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            "use_colors": False,
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "access": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "uvicorn":        {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error":  {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"],  "level": "INFO", "propagate": False},
        "linkedin_agent": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "apscheduler":    {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        loop="asyncio",
        log_config=_LOG_CONFIG,
    )
