from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .services.discover import discover_india_reports
from .services.downloader import download_pdf
from .services.parser import parse_pdf
from .services.validate import validate_rows
from .services.exporter import build_workbook

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "free_state.json"
DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
DOWNLOAD_DIR = DOCS_DIR / "downloads"
LATEST_XLSX = DOWNLOAD_DIR / "meta_india_reports_latest.xlsx"
STATUS_PATH = DATA_DIR / "status.json"
REVIEW_PATH = DATA_DIR / "review.json"
MASTER_JSON_PATH = DATA_DIR / "master_data.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "reports": {}, "rows": [], "last_run": None}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state must be an object")
        data.setdefault("version", 1)
        data.setdefault("reports", {})
        data.setdefault("rows", [])
        data.setdefault("last_run", None)
        return data
    except Exception:
        # Never destroy an unreadable state file silently.
        backup = STATE_PATH.with_suffix(f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
        STATE_PATH.replace(backup)
        return {"version": 1, "reports": {}, "rows": [], "last_run": None}


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _rows_without_report(rows: list[dict], source_url: str) -> list[dict]:
    return [r for r in rows if r.get("source_url") != source_url]


def _safe_report_row(row: dict, source_url: str, title: str | None, sha256: str) -> dict:
    out = dict(row)
    out["source_url"] = source_url
    out["source_title"] = title or "India regulatory report"
    out["source_sha256"] = sha256
    return out


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda r: (
            r.get("period_end") or "9999-12-31",
            r.get("platform") or "",
            r.get("policy_category") or "",
            r.get("source_url") or "",
        ),
    )


def _public_row(row: dict) -> dict:
    """Compact JSON for the static website/audit download."""
    return {
        "month": row.get("month"),
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),
        "report_published": row.get("report_published"),
        "platform": row.get("platform"),
        "policy_category": row.get("policy_category"),
        "content_actioned_raw": row.get("content_actioned_raw"),
        "content_actioned_numeric": row.get("content_actioned_numeric"),
        "proactive_rate": row.get("proactive_rate"),
        "total_user_grievances": row.get("total_user_grievances"),
        "source_page": row.get("source_page"),
        "source_url": row.get("source_url"),
        "source_sha256": row.get("source_sha256"),
        "extraction_method": row.get("extraction_method"),
        "confidence": row.get("confidence"),
        "validation_status": row.get("validation_status"),
        "validation_notes": row.get("validation_notes"),
    }


def run(*, rebuild: bool = False, limit: int | None = None) -> dict[str, Any]:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    state = _load_state()
    if rebuild:
        state = {"version": 1, "reports": {}, "rows": [], "last_run": None}

    print("Discovering India regulatory-transparency reports from Meta...")
    discovered = discover_india_reports()
    if limit:
        discovered = discovered[:limit]

    if not discovered:
        raise RuntimeError(
            "No India PDFs were discovered. Meta may be rate-limiting automated access. "
            "Add verified official PDF URLs to config/manual_reports.json and run again."
        )

    print(f"Discovered {len(discovered)} candidate India report PDF(s).")
    reports: dict[str, dict] = state["reports"]
    all_rows: list[dict] = state["rows"]
    processed = 0
    skipped = 0
    failed_now: list[str] = []

    for idx, item in enumerate(discovered, start=1):
        url = item["url"]
        title = item.get("title") or "India regulatory report"
        prior = reports.get(url) or {}
        if prior.get("status") == "parsed" and not rebuild:
            skipped += 1
            print(f"[{idx}/{len(discovered)}] already parsed; skipping: {title}")
            continue

        print(f"[{idx}/{len(discovered)}] downloading: {title}")
        started_at = _now_iso()
        try:
            pdf_bytes, sha = download_pdf(url)
            parsed = parse_pdf(pdf_bytes, title)
            parsed_rows, issues = validate_rows(parsed.get("rows") or [])
            if not parsed_rows:
                raise RuntimeError("PDF downloaded but no policy rows were parsed")

            all_rows = _rows_without_report(all_rows, url)
            report_rows = [_safe_report_row(r, url, title, sha) for r in parsed_rows]
            all_rows.extend(report_rows)
            reports[url] = {
                "title": title,
                "url": url,
                "sha256": sha,
                "status": "parsed",
                "processed_at": _now_iso(),
                "started_at": started_at,
                "period_start": parsed.get("period_start"),
                "period_end": parsed.get("period_end"),
                "report_published": parsed.get("report_published"),
                "row_count": len(report_rows),
                "review_count": sum(1 for r in report_rows if r.get("validation_status") != "ok"),
                "issues": issues,
            }
            processed += 1
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            reports[url] = {
                **prior,
                "title": title,
                "url": url,
                "status": "failed",
                "last_error": msg,
                "last_attempt_at": _now_iso(),
            }
            failed_now.append(f"{url}: {msg}")
            print(f"  FAILED: {msg}")

    all_rows = _sort_rows(all_rows)
    state["rows"] = all_rows
    state["reports"] = reports
    state["last_run"] = _now_iso()

    if not all_rows:
        _save_json(STATE_PATH, state)
        raise RuntimeError("No usable rows exist yet, so an Excel workbook cannot be generated.")

    failed_reports = [
        f"{url}: {meta.get('last_error', 'failed')}"
        for url, meta in reports.items()
        if meta.get("status") == "failed"
    ]
    xlsx_bytes = build_workbook(all_rows, failed_reports)
    LATEST_XLSX.write_bytes(xlsx_bytes)

    review_rows = [r for r in all_rows if r.get("validation_status") != "ok"]
    successful_reports = [m for m in reports.values() if m.get("status") == "parsed"]
    periods = [r.get("period_end") for r in all_rows if r.get("period_end")]
    status = {
        "generated_at": _now_iso(),
        "has_export": True,
        "report_count": len(successful_reports),
        "row_count": len(all_rows),
        "review_count": len(review_rows),
        "failed_report_count": len(failed_reports),
        "latest_period_end": max(periods) if periods else None,
        "new_reports_processed_this_run": processed,
        "reports_skipped_this_run": skipped,
        "failures_this_run": len(failed_now),
        "download_path": "downloads/meta_india_reports_latest.xlsx",
        "review_path": "data/review.json",
        "master_data_path": "data/master_data.json",
    }

    _save_json(STATE_PATH, state)
    _save_json(STATUS_PATH, status)
    _save_json(REVIEW_PATH, [_public_row(r) for r in review_rows])
    _save_json(MASTER_JSON_PATH, [_public_row(r) for r in all_rows])

    print(json.dumps(status, indent=2))
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Free GitHub Actions runner for the Meta India report pipeline")
    parser.add_argument("--rebuild", action="store_true", help="Ignore saved state and reprocess every discovered report")
    parser.add_argument("--limit", type=int, default=None, help="For testing: process only the first N discovered reports")
    args = parser.parse_args()
    run(rebuild=args.rebuild, limit=args.limit)


if __name__ == "__main__":
    main()
