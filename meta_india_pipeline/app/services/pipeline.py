from __future__ import annotations
from datetime import datetime
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from ..models import Export, NormalizedRow, Report
from .discover import discover_india_reports
from .downloader import download_pdf
from .storage import put_bytes, get_bytes
from .parser import parse_pdf
from .validate import validate_rows
from .ai_verify import verify_row
from .normalize import parse_number, parse_rate
from .exporter import build_workbook
from ..config import get_settings

settings = get_settings()


def _apply_ai(pdf_bytes: bytes, rows: list[dict]) -> list[dict]:
    if not settings.ai_verify_enabled:
        return rows
    for row in rows:
        if row.get("validation_status") != "review":
            continue
        result = verify_row(pdf_bytes, row)
        if not result:
            continue
        row["confidence"] = float(result.get("confidence", row.get("confidence", 0.5)))
        if result.get("exists") and row["confidence"] >= 0.98:
            row["extraction_method"] = "ai_verified"
            if settings.ai_autofix:
                try:
                    row["content_actioned_raw"] = result["content_actioned_raw"]
                    row["content_actioned_numeric"] = parse_number(result["content_actioned_raw"])
                    row["proactive_rate"] = parse_rate(str(result["proactive_rate_percent"]) + "%")
                    row["validation_status"] = "ok_ai"
                    row["validation_notes"] = "AI visual verification/autofix; audit source page"
                except Exception:
                    pass
    return rows


def run_pipeline(db: Session, progress=lambda msg: None) -> dict:
    progress("Discovering India reports from Meta")
    discovered = discover_india_reports()
    if not discovered:
        raise RuntimeError("No India report PDFs discovered. Meta may be rate-limiting the host; add verified URLs to config/manual_reports.json and rerun.")

    failed = []
    for idx, item in enumerate(discovered, start=1):
        url = item["url"]
        progress(f"Report {idx}/{len(discovered)}: {item.get('title') or url}")
        report = db.scalar(select(Report).where(Report.source_url == url))
        if report and report.parse_status == "parsed" and report.sha256:
            continue
        if not report:
            report = Report(source_url=url, title=item.get("title"), country="India")
            db.add(report); db.commit(); db.refresh(report)
        try:
            pdf_bytes, sha = download_pdf(url)
            report.sha256 = sha
            report.pdf_key = put_bytes(f"reports/{sha}.pdf", pdf_bytes, "application/pdf")
            parsed = parse_pdf(pdf_bytes, report.title)
            parsed_rows, issues = validate_rows(parsed["rows"])
            parsed_rows = _apply_ai(pdf_bytes, parsed_rows)
            db.execute(delete(NormalizedRow).where(NormalizedRow.report_id == report.id))
            for r in parsed_rows:
                db.add(NormalizedRow(report_id=report.id, **r))
            report.period_start = parsed.get("period_start")
            report.period_end = parsed.get("period_end")
            report.report_published = parsed.get("report_published")
            report.parse_status = "parsed" if parsed_rows else "review"
            report.validation_status = "review" if issues or any(r.get("validation_status") == "review" for r in parsed_rows) else "ok"
            report.error = "\n".join(issues) if issues else None
            db.commit()
        except Exception as exc:
            report.parse_status = "failed"; report.validation_status = "failed"; report.error = str(exc)
            db.commit(); failed.append(f"{url}: {exc}")

    all_rows = []
    for r in db.scalars(select(NormalizedRow).order_by(NormalizedRow.period_end, NormalizedRow.platform, NormalizedRow.policy_category)):
        all_rows.append({
            "month": r.month, "period_start": r.period_start, "period_end": r.period_end, "report_published": r.report_published,
            "platform": r.platform, "raw_policy_category": r.raw_policy_category, "policy_category": r.policy_category,
            "content_actioned_raw": r.content_actioned_raw, "content_actioned_numeric": r.content_actioned_numeric,
            "proactive_rate": r.proactive_rate, "total_user_grievances": r.total_user_grievances,
            "source_page": r.source_page, "extraction_method": r.extraction_method, "confidence": r.confidence,
            "validation_status": r.validation_status, "validation_notes": r.validation_notes,
        })
    if not all_rows:
        raise RuntimeError("Reports were discovered but no rows could be extracted. Review parser logs and report layouts.")

    progress("Generating Excel workbook")
    xlsx = build_workbook(all_rows, failed)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    key = put_bytes(f"exports/meta_india_reports_{stamp}.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    review_count = sum(1 for r in all_rows if r.get("validation_status") not in {"ok", "ok_ai"})
    exp = Export(object_key=key, row_count=len(all_rows), review_count=review_count)
    db.add(exp); db.commit(); db.refresh(exp)
    return {"export_key": key, "row_count": len(all_rows), "review_count": review_count, "failed_reports": len(failed)}
