# backend/api/main.py
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.database import init_db
from backend.api.routes_auth import router as auth_router
from backend.api.routes_profile import router as profile_router
from backend.api.routes_companies import router as companies_router
from backend.api.routes_tracker import router as tracker_router
from backend.api.routes_replies import router as replies_router
from backend.api.routes_scheduler import router as scheduler_router, start_scheduler

app = FastAPI(title="JobPilot AI")

# Permissive CORS for local dev (Vite dev server on a different port).
# In production the frontend is served from this same app, so CORS is moot.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(companies_router)
app.include_router(tracker_router)
app.include_router(replies_router)
app.include_router(scheduler_router)


@app.on_event("startup")
def _startup():
    init_db()
    try:
        start_scheduler()
        logger.info("Scheduler auto-started")
    except Exception as e:
        logger.warning(f"Scheduler auto-start failed: {e}")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Serve the built React app (client/dist) ─────────────────────────────────
_CLIENT_DIST = os.path.join(os.path.dirname(__file__), "..", "..", "client", "dist")

if os.path.isdir(_CLIENT_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_CLIENT_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # Any non-API route falls back to index.html so React Router can handle it.
        requested = os.path.join(_CLIENT_DIST, full_path)
        if full_path and os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(os.path.join(_CLIENT_DIST, "index.html"))
