# AGENTS.md

## Project mission

This repository exists to collect agro-industry data from multiple public and commercial sources in Mexico and turn it into consulting-grade analysis inputs.

The current codebase is extraction-first:

- Reliable source acquisition matters more than adding speculative modeling code.
- Every dataset should preserve provenance, query parameters, and enough metadata to audit where a number came from.
- The near-term goal is to build repeatable data assets and operational analyses for an agro consulting firm.
- The longer-term goal can include modeling, forecasting, pricing intelligence, and executive reporting, but agents should not pretend that pipeline already exists.

## What this repo currently is

- Python 3.12-oriented data extraction project.
- Main implemented value: source-specific scrapers plus a daily orchestrator.
- Main sources today:
  - `SNIIM` for frutas y hortalizas market prices.
  - `SIAP Cierre Agricola` via legacy HTTP/xajax flow.
  - `SIAP Cierre Agricola` Playwright fallback.
  - `Walmart Mexico` fresh produce search scraping.
  - `Chedraui Mexico` fresh produce search scraping.
- Existing tests focus on parser behavior and daily-run orchestration.
- `scikit-learn` and `xgboost` are installed, but there is no formal modeling or forecasting pipeline yet.

Agents should treat this repo as a data acquisition and analysis foundation, not as a finished analytics platform.

## Core product intent

When you work in this repo, optimize for these outcomes:

- Add trustworthy data sources.
- Improve extraction resilience when source HTML or flows change.
- Standardize outputs so cross-source comparison is easier.
- Make consulting analysis reproducible.
- Keep enough structure so future forecasting, dashboards, and client reporting can be built on top without redoing ingestion.

## Repo map

- `src/extract/sniim.py`: SNIIM extractor and export helpers.
- `src/extract/cierre_agricola_requests.py`: primary SIAP Cierre Agricola HTTP/xajax implementation.
- `src/extract/scraper_cierre_agricola_playwright.py`: browser fallback for SIAP when HTTP flow breaks.
- `src/extract/walmart_produce_scraper.py`: Walmart produce scraper and record ranking logic.
- `src/extract/chedraui_produce_scraper.py`: Chedraui produce scraper and search-result normalization.
- `src/extract/spreadsheet_localization.py`: column aliases, workbook sheet names, and Spanish export naming.
- `scripts/run_daily_extracts.py`: main daily orchestrator across enabled sources.
- `scripts/run_daily_extracts_task.cmd`: Windows Task Scheduler wrapper using the local virtualenv.
- `config/products.xlsx`: operational config workbook for product mappings and enabled sources.
- `tests/`: unit tests and fixtures.
- `data/`: generated raw data and daily runs.
- `debug_cierre_agricola*` and `src/extract/debug_cierre_agricola/`: saved HTTP/xajax debug artifacts.

## Operational commands

Run everything from repo root.

Environment setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Run tests:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Run the daily orchestrator:

```powershell
python scripts/run_daily_extracts.py --config config/products.xlsx --output-root data/daily_runs
```

## Source-specific guidance

### SNIIM

- `src/extract/sniim.py` uses the real ASP.NET form flow.
- Run the extractor from the repo root as `python -m src.extract.sniim ...` so package imports resolve correctly with the current layout.
- Preserve hidden fields and result-page validation; do not simplify the flow unless you verify the site still behaves correctly.
- Keep query metadata in the exported DataFrame so consulting outputs can be audited later.
- Preserve the report-header product label from the result page in the exported rows when available, because SNIIM may display a more specific market product name such as `Aguacate Hass`.
- Parser robustness matters because table headers and encodings can be inconsistent.

### SIAP Cierre Agricola

- Prefer `src/extract/cierre_agricola_requests.py` first. It is faster and better for automation than browser-only scraping.
- Use Playwright only as a fallback when the HTTP/xajax flow changes or the portal behavior can no longer be reproduced reliably with requests.
- When debugging this source, keep `--debug` and `--debug-dir` workflows intact. The XML/HTML snapshots are valuable when the portal changes.
- Be careful with session-dependent behavior. The downloader depends on the xajax flow creating the report state before calling `reporte.php`.

### Walmart

- The scraper reads `__NEXT_DATA__` and ranks candidate products per configured crop.
- Preserve blocked-page detection. Silent bad HTML is worse than an explicit failure.
- Ranking quality matters because consulting analyses need the best representative price per crop, not just any search result.

### Chedraui

- The scraper merges multiple search endpoints and deduplicates by normalized product identity.
- Keep query-term filtering strict enough to avoid unrelated produce contaminating a crop result.
- Treat current-price and old-price extraction carefully; promotion logic affects downstream analysis quality.

### Daily orchestrator

- `scripts/run_daily_extracts.py` is the main production-like entrypoint in this repo today.
- It is intentionally fault-tolerant: one source or one product row may fail without killing the entire run.
- Preserve `run_summary.json`, workbook metadata sheets, and per-source failure reporting.
- If you add a new source, integrate it in a way that keeps partial success possible and makes failures diagnosable per row and per source.

## Data and output rules

- Treat generated outputs as disposable unless the user explicitly wants them committed.
- `.gitignore` already excludes `data/daily_runs/`, logs, and spreadsheet outputs such as `*.xlsx`, `*.xls`, and `*.csv`.
- `config/products.xlsx` is operationally important but is currently ignored by git, so do not assume config workbook changes will be versioned automatically.
- Preserve source provenance columns and exported metadata whenever possible.
- Prefer additive changes to schemas over breaking renames unless you update all downstream consumers and docs together.

## Testing and validation rules

- Prefer parser/unit tests over live-site tests for normal development.
- Use fixtures and mocks for external sources whenever possible.
- If you change a source parser, add or update a focused test in `tests/`.
- If you change workbook columns, output sheet names, or summary JSON structure, validate `scripts/run_daily_extracts.py` behavior and update tests accordingly.
- For source breakage investigations, capture the exact failing response or debug artifact before patching heuristics.

## Coding and collaboration rules for agents

- Keep the extraction layer reliable before adding new analytics layers.
- Favor clear, source-specific functions over large generic abstractions that hide scraper behavior.
- Do not remove debug capability from fragile sources just to make code look cleaner.
- Keep user-facing docs and operational guidance aligned with the real commands and file paths in this repo.
- When behavior is worth documenting, document it immediately instead of leaving hidden tribal knowledge in code only.

## Documentation maintenance rule

Every time an agent creates or modifies something worth mentioning, update `README.md` and this `AGENTS.md` in the same change when the docs would otherwise become stale.

Examples that usually require doc updates:

- New source integrations.
- New scripts or entrypoints.
- Changes to workbook columns or sheet names.
- Changes to output files, output directories, or summary JSON.
- Changes to scheduling or operational run commands.
- Important limitations, failure modes, or debugging workflows.

## Recommended next-step areas

High-value work in this repo usually looks like this:

- Add a normalized intermediate dataset that aligns source fields across retailers and public market sources.
- Add data-quality checks for missing prices, outliers, and suspicious unit mismatches.
- Build reusable analysis scripts for spreads, source comparisons, seasonality, and PMR vs retail gaps.
- Version analysis-ready outputs separately from raw extracts.
- Add a formal pipeline for transformation and forecasting once ingestion quality is stable enough.

Agents should be proactive about suggesting or implementing these steps when they clearly support the consulting use case.
