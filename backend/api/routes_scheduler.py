# backend/api/routes_scheduler.py
from fastapi import APIRouter, Depends

from backend.models.user import User
from backend.api.auth import get_current_user

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

_holder = {"scheduler": None}


def is_running() -> bool:
    sched = _holder["scheduler"]
    return sched is not None and sched.running


def start_scheduler():
    if _holder["scheduler"] is not None and _holder["scheduler"].running:
        return
    from backend.pipeline.scheduler import create_scheduler
    sched = create_scheduler()
    sched.start()
    _holder["scheduler"] = sched


def stop_scheduler():
    if _holder["scheduler"] is not None and _holder["scheduler"].running:
        _holder["scheduler"].shutdown(wait=False)
    _holder["scheduler"] = None


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    running = is_running()
    jobs = []
    if running:
        for j in _holder["scheduler"].get_jobs():
            jobs.append({"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None})
    return {"running": running, "jobs": jobs}


@router.post("/start")
def start(user: User = Depends(get_current_user)):
    start_scheduler()
    return {"running": is_running()}


@router.post("/stop")
def stop(user: User = Depends(get_current_user)):
    stop_scheduler()
    return {"running": is_running()}
