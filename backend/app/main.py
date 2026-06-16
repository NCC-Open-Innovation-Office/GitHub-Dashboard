from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import activity, commit_activity, contributors, debug, org, repos

app = FastAPI(
    title="GitHub Dashboard API",
    description="Metrics dashboard for a GitHub organization — including private and internal repositories.",
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
app.include_router(contributors.router, prefix="/api/contributors", tags=["contributors"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(commit_activity.router, prefix="/api/commit-activity", tags=["commit-activity"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])


@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


# Serve the vanilla JS frontend — must be registered AFTER all API routes
_static_dir = Path(__file__).parent.parent / "static"

@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(_static_dir / "index.html")

app.mount("/static", StaticFiles(directory=_static_dir), name="static")
