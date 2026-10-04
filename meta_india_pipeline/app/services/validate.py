from __future__ import annotations
from collections import defaultdict
from statistics import median


def validate_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    issues: list[str] = []
    seen = set()
    groups = defaultdict(list)
    for row in rows:
        notes = []
        key = (row["platform"], row["policy_category"])
        if key in seen:
            notes.append("duplicate platform/category in report")
        seen.add(key)
        if row["content_actioned_numeric"] < 0:
            notes.append("negative content-actioned value")
        if not 0 <= row["proactive_rate"] <= 1:
            notes.append("proactive rate outside 0..1")
        if row.get("month") == "Unknown" or not row.get("period_end"):
            notes.append("reporting period not identified")
        groups[row["platform"]].append(row)
        row["validation_status"] = "review" if notes else "ok"
        row["validation_notes"] = "; ".join(notes) if notes else None

    for platform, group in groups.items():
        vals = [r["content_actioned_numeric"] for r in group if r["content_actioned_numeric"] > 0]
        if len(group) < 5:
            issues.append(f"{platform}: only {len(group)} policy rows found")
        med = median(vals) if vals else 0
        for row in group:
            raw = row["content_actioned_raw"].strip()
            suspicious_scale = med > 0 and row["content_actioned_numeric"] < med / 10_000
            malformed_raw = raw.endswith(".") or raw in {"-", "."}
            if suspicious_scale or malformed_raw:
                row["validation_status"] = "review"
                msg = "extreme scale/raw-format anomaly"
                row["validation_notes"] = (row.get("validation_notes") + "; " if row.get("validation_notes") else "") + msg
                issues.append(f"{platform}/{row['policy_category']}: {msg} ({raw})")

    if not groups:
        issues.append("No policy tables were parsed")
    return rows, issues
