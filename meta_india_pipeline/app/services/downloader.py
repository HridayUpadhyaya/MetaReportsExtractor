from __future__ import annotations
import hashlib, time
import requests
from ..config import get_settings

settings = get_settings()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"


def download_pdf(url: str) -> tuple[bytes, str]:
    last_error = None
    for attempt in range(settings.http_max_retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"}, timeout=90)
            if r.status_code == 200 and (r.content.startswith(b"%PDF") or "pdf" in r.headers.get("content-type", "").lower()):
                time.sleep(settings.meta_download_delay_seconds)
                return r.content, hashlib.sha256(r.content).hexdigest()
            last_error = RuntimeError(f"HTTP {r.status_code} for {url}")
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"Failed to download PDF: {last_error}")
