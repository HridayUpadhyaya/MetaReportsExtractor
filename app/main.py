from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from .config import get_settings
from .db import SessionLocal, init_db
from .models import Export, Job, NormalizedRow, Report
from .services.storage import download_url

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup(): init_db()


@app.get("/")
def home(request: Request):
    with SessionLocal() as db:
        last_job = db.scalar(select(Job).order_by(Job.created_at.desc()).limit(1))
        latest_export = db.scalar(select(Export).order_by(Export.created_at.desc()).limit(1))
        report_count = db.scalar(select(func.count(Report.id))) or 0
        row_count = db.scalar(select(func.count(NormalizedRow.id))) or 0
        review_count = db.scalar(select(func.count(NormalizedRow.id)).where(NormalizedRow.validation_status == "review")) or 0
    return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name, "last_job": last_job,
        "latest_export": latest_export, "report_count": report_count, "row_count": row_count, "review_count": review_count})


@app.get("/health")
def health(): return {"ok": True}


@app.post("/api/run")
def run_sync(x_admin_token: str | None = Header(default=None)):
    if settings.admin_token and x_admin_token != settings.admin_token:
        raise HTTPException(401, "Invalid admin token")
    with SessionLocal() as db:
        active = db.scalar(select(Job).where(Job.status.in_(["queued", "running"])).order_by(Job.created_at.desc()).limit(1))
        if active: return {"job_id": active.id, "status": active.status, "message": "Existing job reused"}
        job = Job(kind="sync", status="queued", message="Queued from website")
        db.add(job); db.commit(); db.refresh(job)
        return {"job_id": job.id, "status": job.status}


@app.get("/api/status/{job_id}")
def job_status(job_id: int):
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job: raise HTTPException(404, "Job not found")
        return {"id": job.id, "status": job.status, "message": job.message, "result_key": job.result_key}


@app.get("/download/latest")
def download_latest():
    with SessionLocal() as db:
        exp = db.scalar(select(Export).order_by(Export.created_at.desc()).limit(1))
        if not exp: raise HTTPException(404, "No export yet")
        signed = download_url(exp.object_key)
        if signed: return RedirectResponse(signed)
        path = Path("storage") / exp.object_key
        if not path.exists(): raise HTTPException(404, "Export file missing")
        return FileResponse(path, filename="meta_india_reports_latest.xlsx")
