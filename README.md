# Meta India Regulatory Reports → Excel Website

This project is a deployable pipeline for the Meta Regulatory Transparency Reports hub:

- discovers **India-only** regulatory transparency reports;
- downloads and caches each source PDF;
- extracts policy-category tables with deterministic code;
- normalises abbreviated values (`25.6 M` → `25,600,000`) and rates;
- extracts platform-level grievances;
- validates for duplicates, impossible rates, missing periods, row-count failures and scale anomalies;
- optionally sends **only suspicious rows** to an AI visual verifier;
- stores provenance (source URL, PDF checksum, source page, extraction method, confidence, validation state);
- generates an `.xlsx` with the same four-sheet structure as the supplied workbook;
- exposes a small FastAPI website with **Run sync** and **Download latest spreadsheet**;
- supports scheduled runs through Railway Cron.

## Why this design

Do **not** make an agent the primary PDF-to-Excel converter. The primary path is deterministic and reproducible. AI is an exception checker. This gives you much better auditability and makes parser mistakes visible instead of silently turning into spreadsheet values.

Architecture:

```text
Meta hub
  ↓
India report discovery (HTTP → browser fallback)
  ↓
PDF downloader + SHA-256 cache
  ↓
Deterministic PDF/table parser
  ↓
Normalisation
  ↓
Validation rules
  ↓ suspicious only
Optional AI page-image verifier
  ↓
PostgreSQL audit store
  ↓
Template-based Excel generator
  ↓
Railway Bucket
  ↓
FastAPI website / signed download
```

## Project layout

```text
app/
  main.py                 FastAPI website/API
  worker.py               background job worker
  cli.py                  scheduler/CLI commands
  db.py, models.py        PostgreSQL/SQLite audit database
  services/
    discover.py           Meta hub discovery, India filter, browser fallback
    downloader.py         conservative PDF downloader with retries/backoff
    parser.py             deterministic PDF/table extraction
    normalize.py          numeric/rate/category normalisation
    validate.py           anomaly and completeness checks
    ai_verify.py          optional visual AI checker for flagged rows
    pipeline.py           orchestration
    exporter.py           Excel template population
  templates/index.html
  static/app.css
config/manual_reports.json emergency/manual official report manifest
data/meta_india_template.xlsx supplied workbook used as the template
```

## Accuracy policy

A row is automatically accepted only when it parses and passes deterministic validation. The database retains:

- source report URL;
- source PDF SHA-256 hash;
- source page number;
- raw policy label;
- normalised policy label;
- extraction method;
- extraction confidence;
- validation status and notes.

The optional AI verifier sees only the page containing a suspicious row. By default it **does not overwrite** the deterministic value. To allow high-confidence AI corrections set `AI_AUTOFIX=true`; keeping it `false` is safer for regulated/research use.

## Important Meta access note

The Meta Transparency hub can return HTTP `429 Too Many Requests` to automated/cloud clients. This project therefore:

1. requests the hub conservatively;
2. caches already processed reports and does not re-download them;
3. uses exponential backoff;
4. can fall back to a normal headless Chromium session;
5. supports `config/manual_reports.json` for verified official report URLs if discovery is temporarily unavailable.

Do not increase request frequency or try to evade access controls. If Meta blocks your hosting provider, use the manual manifest or run the acquisition component from an environment Meta permits, while keeping the rest of the pipeline unchanged.

---

# 1. Run locally first

Requirements: Docker Desktop is the easiest route. Without Docker, use Python 3.12 and install Playwright Chromium.

### Docker

```bash
cp .env.example .env
# Change ADMIN_TOKEN in .env
docker build -t meta-india-pipeline .
docker run --rm -p 8000:8000 --env-file .env meta-india-pipeline
```

Open `http://localhost:8000`.

The container uses SQLite and local `storage/` when no Railway/Postgres/Bucket values are supplied. This is suitable for local testing only.

### Native Python

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
playwright install --with-deps chromium
cp .env.example .env
uvicorn app.main:app --reload
```

In a second terminal run the worker:

```bash
python -m app.worker
```

Then open `http://127.0.0.1:8000`, enter the `ADMIN_TOKEN`, and click **Run India sync now**.

You can also bypass the queue for debugging:

```bash
python -m app.cli run-sync
```

Run tests:

```bash
pytest -q
```

---

# 2. Put the project on GitHub

Create a new private GitHub repository, then from this project folder:

```bash
git init
git add .
git commit -m "Initial Meta India report pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Do **not** commit `.env` or API keys. `.gitignore` already excludes `.env`.

---

# 3. Create the Railway project

1. Sign in to Railway.
2. Choose **New Project**.
3. Choose **Deploy from GitHub repo**.
4. Select your repository.
5. Let Railway build the Dockerfile.

This first service will become the **web service**.

In the web service settings:

- Start command: leave the Dockerfile default command.
- Healthcheck path: `/health` (also included in `railway.toml`).
- Networking → **Generate Domain**.

Your public website will then have a Railway domain.

---

# 4. Add PostgreSQL

In the Railway project canvas:

1. Click **+ New**.
2. Choose **Database → PostgreSQL**.
3. Wait for Postgres to deploy.
4. Open the web service → **Variables**.
5. Add:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Use Railway's variable-reference picker if your Postgres service has a different display name.

The app creates its tables automatically on startup.

---

# 5. Add a Railway Storage Bucket

The bucket stores source PDFs and generated spreadsheets durably.

1. On the project canvas click **+ New → Bucket**.
2. Name it, for example, `meta-reports`.
3. Open the bucket's **Credentials** tab.
4. In the web service's Variables, reference the bucket variables:

```text
BUCKET=${{meta-reports.BUCKET}}
ACCESS_KEY_ID=${{meta-reports.ACCESS_KEY_ID}}
SECRET_ACCESS_KEY=${{meta-reports.SECRET_ACCESS_KEY}}
REGION=${{meta-reports.REGION}}
ENDPOINT=${{meta-reports.ENDPOINT}}
```

If Railway's bucket has another service name, replace `meta-reports` with that exact name. You can also use Railway's automatic variable injection.

The app generates presigned download links, so the bucket itself can remain private.

---

# 6. Add production environment variables

Add these variables to the **web service**:

```text
META_HUB_URL=https://transparency.meta.com/reports/regulatory-transparency-reports/
META_COUNTRY=India
META_DOWNLOAD_DELAY_SECONDS=2.5
HTTP_MAX_RETRIES=5
PLAYWRIGHT_FALLBACK=true
ADMIN_TOKEN=<a-long-random-secret>
AI_VERIFY_ENABLED=false
AI_AUTOFIX=false
```

Generate a strong admin token locally, for example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep `AI_VERIFY_ENABLED=false` for the first deterministic test.

---

# 7. Add the background worker

The website should not parse dozens of PDFs inside an HTTP request. Create a separate always-running worker.

1. Railway project → **+ New → GitHub Repo** (same repository).
2. Name this service `worker`.
3. Set its Start Command to:

```text
python -m app.worker
```

4. Give it the **same** `DATABASE_URL` and bucket variables as the web service.
5. Also copy the Meta and AI-related variables.
6. The worker needs no public domain.

When the website creates a job, this worker claims it from PostgreSQL and processes it.

---

# 8. Add a scheduled updater

Meta reports are monthly, so there is no need to hammer the hub every hour. A daily check is already conservative; weekly is also reasonable.

Create another service from the same repo named `scheduler`.

Set its Start Command:

```text
python -m app.cli enqueue-sync
```

Set the Railway **Cron Schedule**, for example once per day at 02:30 UTC:

```text
30 2 * * *
```

The cron service only inserts a queued job and exits. The worker performs the actual download/parse/export work.

Give the scheduler only `DATABASE_URL`; it does not need the bucket credentials because it only queues the job.

---

# 9. Enable the AI verifier (optional, after deterministic testing)

The OpenAI portion is deliberately a fallback rather than the main parser.

1. Create an OpenAI API key.
2. Add it to the **worker** service only:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5
AI_VERIFY_ENABLED=true
AI_AUTOFIX=false
```

With `AI_AUTOFIX=false`, suspicious rows remain reviewable and the model acts as a second opinion. After you have tested a good sample of old and new reports, you may enable `AI_AUTOFIX=true`, but the safer production setting is `false`.

The implementation uses the Responses API with a rendered image of the source PDF page.

---

# 10. First production run

1. Open the deployed website.
2. Enter your `ADMIN_TOKEN`.
3. Click **Run India sync now**.
4. Watch the status message.
5. When complete, click **Download latest spreadsheet**.
6. Check:
   - earliest and latest reporting periods;
   - Facebook/Instagram (and Threads when present);
   - total number of categories per month;
   - grievance totals;
   - all rows flagged for review.

For the first historical backfill, manually spot-check at least one PDF from each distinct layout era. Once parser coverage is confirmed, future monthly runs should normally add only the new report.

---

# 11. If Meta returns 429 in Railway

First do **not** increase retries/frequency.

Check worker logs. If the hub is inaccessible from Railway:

1. Open `config/manual_reports.json`.
2. Add only verified official India report PDF URLs:

```json
{
  "reports": [
    {
      "url": "https://...official-meta-report.pdf",
      "title": "India report - YYYY-MM"
    }
  ]
}
```

3. Commit and push.
4. Re-run the sync.

This bypasses only *discovery*, not source validation or parsing. Do not add third-party copies if your requirement is official Meta reports only.

A longer-term alternative is to separate acquisition into a permitted network/environment and upload the untouched official PDFs to the same bucket; the parser/exporter does not need to change.

---

# 12. Updating the parser when Meta changes layouts

Do not rewrite the entire pipeline. Add a layout-specific parser or header rule, then add a regression test with a representative PDF/text fixture.

The most important functions are:

- `app/services/parser.py::_header_indexes`
- `app/services/parser.py::_find_period`
- `app/services/parser.py::_find_grievances`
- `app/services/normalize.py::CATEGORY_RULES`

Keep raw labels in the database even when you add a canonical category mapping.

---

# 13. Recommended production acceptance rules

Before considering a run fully accepted, require:

- all PDFs to start with a valid `%PDF` signature;
- a SHA-256 checksum for every stored source;
- a valid reporting period;
- at least five policy rows per platform;
- no duplicate `(report, platform, category)` rows;
- `0 <= proactive_rate <= 1`;
- all content-actioned fields numeric after normalisation;
- anomaly review for extreme scale differences or malformed raw values;
- spot-check of every newly encountered report layout;
- review count = zero, or explicit human acceptance of each review item.

This is a much stronger accuracy model than “agent reads PDF and makes Excel”.

---

# 14. Useful commands

Web server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Worker:

```bash
python -m app.worker
```

Queue a sync:

```bash
python -m app.cli enqueue-sync
```

Run immediately in the current process:

```bash
python -m app.cli run-sync
```

Tests:

```bash
pytest -q
```

---

# What is still intentionally not “magic”

Meta has changed report layouts and access behaviour over time. No generic parser can truthfully promise 100% extraction accuracy across every future layout without calibration. This project is designed so failures become **review flags** instead of plausible-looking wrong spreadsheet values. That is the correct tradeoff when accuracy is the priority.
