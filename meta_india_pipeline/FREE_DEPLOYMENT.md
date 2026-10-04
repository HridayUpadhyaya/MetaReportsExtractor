# 100% Free Deployment: GitHub Actions + GitHub Pages

This deployment deliberately does **not** use Railway, PostgreSQL, S3, or a paid AI API.

## What replaces the paid components

| Original component | Free replacement |
|---|---|
| Railway web service | GitHub Pages static website |
| Railway worker | GitHub Actions runner |
| Railway cron | GitHub Actions `schedule` |
| PostgreSQL | Versioned JSON state in `data/free_state.json` |
| Object storage | Generated XLSX + audit JSON committed to the repository |
| OpenAI verifier | Disabled; validation flags suspicious rows for human review |

The main pipeline remains deterministic: discover -> download -> parse -> normalize -> validate -> export.

## One-time GitHub setup

1. Keep the repository public if you want GitHub-hosted Actions to be free/unlimited on standard runners and GitHub Pages on GitHub Free.
2. Repository **Settings -> Actions -> General -> Workflow permissions**: choose **Read and write permissions** and save.
3. Repository **Settings -> Pages**:
   - Source: **Deploy from a branch**
   - Branch: **main**
   - Folder: **/docs**
   - Save.
4. Open the repository's **Actions** tab, select **Update Meta India reports**, click **Run workflow**, and run it once.
5. After a successful run, refresh **Settings -> Pages**. GitHub will show the public `github.io` URL.

## Automatic schedule

`.github/workflows/update.yml` checks every Monday at 03:17 UTC (08:47 IST). It only re-downloads reports not already marked successfully parsed in `data/free_state.json`.

## Manual rebuild

Actions -> Update Meta India reports -> Run workflow -> enable **Reprocess all previously seen reports**.

Use this only after changing parser logic; a normal run is faster and gentler on Meta's servers.

## If Meta returns HTTP 429 / discovery finds nothing

Add verified official Meta PDF URLs to `config/manual_reports.json`:

```json
{
  "reports": [
    {
      "title": "India Monthly Report ...",
      "url": "https://...official-meta-url....pdf"
    }
  ]
}
```

Commit and push the file, then rerun the Action. The same parser/validator/exporter is used.

## Accuracy policy

- Parsing is deterministic.
- Every row in the audit JSON keeps source URL, PDF checksum, source page, extraction method, confidence, validation status, and notes.
- Suspicious rows appear in `docs/data/review.json`.
- The free setup intentionally does not auto-correct flagged values with AI.

## Important GitHub scheduling caveat

GitHub may automatically disable scheduled workflows in a public repository after 60 days with no repository activity. The workflow's own commits normally create activity whenever data changes, but if Meta publishes nothing for a long period, check the Actions page and re-enable the workflow if needed.
