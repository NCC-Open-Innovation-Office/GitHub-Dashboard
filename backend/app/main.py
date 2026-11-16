import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .cache import initialize_cache
from .config import settings
from .routers import activity, commit_activity, contributors, org, repos
from .services import api_queue, cache_warming, request_queue

app = FastAPI(
    title="GitHub Dashboard API",
    description=(
        "Metrics dashboard for a GitHub organization, including private and "
        "internal repositories."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(org.router, prefix="/api/org", tags=["organization"])
app.include_router(repos.router, prefix="/api/repos", tags=["repositories"])
app.include_router(
    contributors.router,
    prefix="/api/contributors",
    tags=["contributors"],
)
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(
    commit_activity.router,
    prefix="/api/commit-activity",
    tags=["commit-activity"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize background tasks on startup"""
    initialize_cache()
    request_queue.request_queue.start()
    app.state.api_queue_task = asyncio.create_task(api_queue.process_queue())
    app.state.cache_warming_task = asyncio.create_task(
        cache_warming.schedule_cache_warming(interval_seconds=900)
    )
    if settings.startup_full_refresh:
        api_queue.enqueue_full_refresh(settings.github_org)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up background tasks on shutdown"""
    await request_queue.request_queue.stop()

    api_queue_task = getattr(app.state, "api_queue_task", None)
    if api_queue_task and not api_queue_task.done():
        api_queue_task.cancel()
        try:
            await api_queue_task
        except asyncio.CancelledError:
            pass

    cache_warming_task = getattr(app.state, "cache_warming_task", None)
    if cache_warming_task and not cache_warming_task.done():
        cache_warming_task.cancel()
        try:
            await cache_warming_task
        except asyncio.CancelledError:
            pass


@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# Serve the vanilla JS frontend — must be registered AFTER all API routes
_static_dir = Path(__file__).parent.parent / "static"


def _serve_dashboard() -> FileResponse:
    return FileResponse(_static_dir / "index.html")


@app.get("/", include_in_schema=False)
async def serve_index():
    return _serve_dashboard()


@app.get("/tv", include_in_schema=False)
@app.get("/tv/", include_in_schema=False)
async def serve_tv():
    return _serve_dashboard()

app.mount("/static", StaticFiles(directory=_static_dir), name="static")
