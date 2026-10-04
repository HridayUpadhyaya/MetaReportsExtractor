from __future__ import annotations
import time
from datetime import datetime
from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Job
from .services.pipeline import run_pipeline

settings = get_settings()


def claim_job(db):
    q = select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
    if not settings.database_url.startswith("sqlite"):
        q = q.with_for_update(skip_locked=True)
    job = db.scalar(q)
    if job:
        job.status = "running"; job.started_at = datetime.utcnow(); db.commit(); db.refresh(job)
    return job


def main():
    init_db()
    while True:
        with SessionLocal() as db:
            job = claim_job(db)
            if not job:
                time.sleep(settings.poll_seconds); continue
            try:
                def progress(msg):
                    job.message = msg; db.commit()
                result = run_pipeline(db, progress)
                job.status = "complete"; job.message = f"Complete: {result['row_count']} rows, {result['review_count']} review flags"
                job.result_key = result["export_key"]
            except Exception as exc:
                job.status = "failed"; job.message = str(exc)
            job.finished_at = datetime.utcnow(); db.commit()


if __name__ == "__main__": main()
