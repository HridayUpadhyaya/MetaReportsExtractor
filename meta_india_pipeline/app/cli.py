from __future__ import annotations
import argparse
from .db import SessionLocal, init_db
from .models import Job
from .services.pipeline import run_pipeline


def enqueue():
    init_db()
    with SessionLocal() as db:
        job = Job(kind="sync", status="queued", message="Queued by scheduler")
        db.add(job); db.commit(); print(job.id)


def run_now():
    init_db()
    with SessionLocal() as db:
        result = run_pipeline(db, print); print(result)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=["enqueue-sync", "run-sync"]); args = ap.parse_args()
    enqueue() if args.command == "enqueue-sync" else run_now()


if __name__ == "__main__": main()
