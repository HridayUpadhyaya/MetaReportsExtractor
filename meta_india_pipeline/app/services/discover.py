from __future__ import annotations
import json, re, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from ..config import get_settings

settings = get_settings()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153 Safari/537.36"


def _request(url: str) -> requests.Response:
    last = None
    for attempt in range(settings.http_max_retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}, timeout=45)
            last = r
            if r.status_code not in {429, 500, 502, 503, 504}:
                return r
            time.sleep(min(30, 2 ** attempt))
        except requests.RequestException:
            time.sleep(min(30, 2 ** attempt))
    if last is None:
        raise RuntimeError(f"Could not fetch {url}")
    return last


def _extract_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a[href]"):
        href = urljoin(base_url, a.get("href"))
        text = " ".join(a.stripped_strings)
        out.append({"url": href, "title": text})
    # Also capture PDF URLs embedded in JSON/script blobs.
    for m in re.findall(r'https?:\\?/\\?/[^"\'<> ]+?\.pdf(?:\?[^"\'<> ]*)?', html, re.I):
        out.append({"url": m.replace("\\/", "/"), "title": "embedded pdf"})
    return out


def _playwright_links(url: str) -> list[dict]:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)
        items = page.eval_on_selector_all("a[href]", "els => els.map(a => ({url:a.href, title:(a.innerText||a.textContent||'').trim()}))")
        html = page.content()
        browser.close()
    items.extend(_extract_links(html, url))
    return items


def _looks_india(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('url','')}".lower()
    return "india" in text


def _manual() -> list[dict]:
    p = Path("config/manual_reports.json")
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [{"url": x["url"], "title": x.get("title", "manual India report")} for x in data.get("reports", [])]


def discover_india_reports() -> list[dict]:
    hub = settings.meta_hub_url
    items: list[dict] = []
    try:
        r = _request(hub)
        if r.ok:
            items.extend(_extract_links(r.text, hub))
    except Exception:
        pass

    # Meta may rate-limit server-side clients; a normal browser session is the supported fallback.
    if settings.playwright_fallback and (not items or not any(_looks_india(x) for x in items)):
        try:
            items.extend(_playwright_links(hub))
        except Exception:
            pass

    # Follow India-looking report landing pages to find their actual PDFs.
    candidates = []
    for item in items:
        url = item["url"]
        if _looks_india(item) and ("report" in (item.get("title") or "").lower() or ".pdf" in url.lower()):
            candidates.append(item)

    pdfs: list[dict] = []
    for item in candidates:
        url = item["url"]
        if ".pdf" in url.lower():
            pdfs.append(item)
            continue
        try:
            r = _request(url)
            if r.ok:
                for child in _extract_links(r.text, url):
                    if ".pdf" in child["url"].lower():
                        child["title"] = item.get("title") or child.get("title")
                        pdfs.append(child)
        except Exception:
            continue

    pdfs.extend(_manual())
    dedup = {}
    for item in pdfs:
        url = item["url"].split("#")[0]
        dedup[url] = {"url": url, "title": item.get("title") or "India regulatory report"}
    return list(dedup.values())
