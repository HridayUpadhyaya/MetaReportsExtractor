from __future__ import annotations
import base64, io, json, re
import fitz
from openai import OpenAI
from ..config import get_settings

settings = get_settings()


def _page_data_url(pdf_bytes: bytes, page_number: int) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(page_number - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
    data = pix.tobytes("jpeg")
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def verify_row(pdf_bytes: bytes, row: dict) -> dict | None:
    if not settings.ai_verify_enabled or not settings.openai_api_key or not row.get("source_page"):
        return None
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"""You are verifying one row extracted from an official Meta India regulatory transparency report.
Read the supplied page visually. Do not infer missing values. Return JSON only with keys:
exists (boolean), platform, policy_category, content_actioned_raw, proactive_rate_percent, confidence (0..1), evidence_short.
Candidate: {json.dumps(row, ensure_ascii=False)}
If the candidate row does not exist, exists=false. evidence_short must be under 25 words."""
    response = client.responses.create(
        model=settings.openai_model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": _page_data_url(pdf_bytes, row["source_page"]), "detail": "high"},
        ]}],
    )
    text = response.output_text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
