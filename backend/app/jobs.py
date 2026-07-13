"""A minimal in-memory job tracker for long-running background work (video
object removal). This is intentionally simple — a single dict guarded by a
lock, and a plain OS thread per job — which is appropriate for a
single-process dev server. If this app is ever deployed with multiple
worker processes, this would need to move to something shared (e.g.
Redis) since each process would otherwise have its own separate job dict.
"""
import threading
import uuid

_jobs = {}
_lock = threading.Lock()


def create_job() -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"status": "pending", "progress": 0.0, "error": None}
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job is not None else None


def run_in_background(job_id: str, fn, *args, **kwargs) -> None:
    def _run():
        try:
            update_job(job_id, status="processing")
            fn(job_id, *args, **kwargs)
            update_job(job_id, status="done", progress=1.0)
        except Exception as exc:
            update_job(job_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()