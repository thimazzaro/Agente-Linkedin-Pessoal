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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        loop="asyncio",
    )
