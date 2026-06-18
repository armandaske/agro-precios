# AGENTS.md

## Project mission

This repository exists to collect agro-industry data from multiple public and commercial sources in Mexico and turn it into consulting-grade analysis inputs.

The current codebase remains extraction-first, with an initial governed analytics layer:

- Reliable source acquisition matters more than adding speculative modeling code.
- Every dataset should preserve provenance, query parameters, and enough metadata to audit where a number came from.
- The near-term goal is to build repeatable data assets and operational analyses for an agro consulting firm.
- Modeling, forecasting, pricing intelligence, and executive reporting now have runnable v1 pipelines, but agents must not present candidate models as operational unless temporal backtesting beats the configured baselines.

## What this repo currently is

- Python 3.12-oriented data extraction project.
- Main implemented value: source-specific scrapers plus a daily orchestrator.
- Main sources today:
  - `SNIIM` for frutas y hortalizas market prices.
- `SIAP Cierre Agricola` via legacy HTTP/xajax flow.
- `SIAP Avance Agricola` via legacy HTTP/xajax flow.
- `SIAP Cierre Agricola` Playwright fallback.
- `Presas Agricolas` via direct HTTP endpoints for corte por decena and series historicas por presa.
- `Walmart Mexico` fresh produce search scraping.
- `Chedraui Mexico` fresh produce search scraping.
- Tests cover extraction, feature engineering, public-data parsing, and daily orchestration.
- `scikit-learn`, `xgboost`, and `pyarrow` support the formal v1 analysis pipelines.

Agents should treat this repo as a data acquisition and analysis foundation with governed v1 models, not as a finished analytics platform.

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
- `src/extract/avance_agricola_requests.py`: primary SIAP Avance Agricola HTTP/xajax implementation.
- `src/extract/scraper_cierre_agricola_playwright.py`: browser fallback for SIAP when HTTP flow breaks.
- `src/extract/presas_agricolas.py`: Presas Agricolas scraper plus workbook bootstrap for parameterized queries.
- `src/extract/walmart_produce_scraper.py`: Walmart produce scraper and record ranking logic.
- `src/extract/chedraui_produce_scraper.py`: Chedraui produce scraper and search-result normalization.
- `src/extract/spreadsheet_localization.py`: column aliases, workbook sheet names, and Spanish export naming.
- `scripts/run_daily_extracts.py`: main daily orchestrator across enabled sources.
- `scripts/fetch_cierre_batch.py`: batch runner that fetches normalized annual Cierre Agricola exports for the configured canonical products.
- `scripts/fetch_avance_batch.py`: batch runner that fetches normalized monthly Avance Agricola exports for the configured canonical products.
- `scripts/normalize_company_avance_history.py`: adapter that turns the internal `siembras_cosechas_*.csv` matrix into Avance-like monthly XLSX files for historical training coverage.
- `scripts/build_master_price_workbook.py`: builds the analysis-ready comparative workbook from dated daily runs plus normalized Avance exports and optional normalized Cierre exports.
- `src/analysis/`: shared feature engineering, temporal validation, model governance, and reporting code.
- `scripts/run_water_risk_model.py`: creates decena reservoir features, backtests candidate forecasts, and writes alerts and a map.
- `scripts/run_production_nowcast.py`: creates crop-state cutoff features and trains only when historical Avance and Cierre years overlap.
- `scripts/run_price_shock_model.py`: creates product-market daily features, price forecasts, and margin anomalies.
- `scripts/run_analysis_pipeline.py`: rebuilds the master workbook and runs all three analytical projects in order.
- `scripts/fetch_public_international_prices.py`: downloads unauthenticated public international price files for World Bank Pink Sheet and FRED USD/MXN.
- `scripts/build_international_price_features.py`: builds the optional audited international price feature parquet from public files and `proxies_internacionales`.
- `scripts/fetch_nasa_power_weather.py`: optional NASA POWER climate enrichment.
- `scripts/run_daily_extracts_task.cmd`: Windows Task Scheduler wrapper using the local virtualenv.
- `COMMANDS.md`: quick command reference for the main extractors, batch runners, workbook builder, tests, and Windows scheduler workflow.
- `ANALYSIS_GUIDE.md`: detailed operational and interpretation guide for the analytical pipelines, caveats, limitations, and demo framing.
- `config/products.xlsx`: operational config workbook for product mappings and enabled sources.
- `config/presas_agricolas.xlsx`: operational config workbook for dam queries by year, month, day-block, and `id_conagua`.
- `config/presas_agricolas.xlsx` also carries a `catalogo_presas` sheet so operators can resolve `id_conagua` from `nombre_oficial` and `estado`.
- The Presas workbook bootstrap supports `catalog_scope`: `latest` for a fast single-cut catalog and `all-available` for a slower union across published periods.
- `notebooks/master_price_eda.ipynb`: starter notebook for charting the comparative workbook.
- `tests/`: unit tests and fixtures.
- `data/`: generated raw data and daily runs.
- `debug_cierre_agricola/`: saved HTTP/xajax debug artifacts plus frontend reference files such as `funciones_cierre.js`.

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

Run the governed analysis pipeline:

```powershell
python -m scripts.run_analysis_pipeline
```

Quick command lookup:

```powershell
Get-Content COMMANDS.md
```

## Source-specific guidance

### SNIIM

- `src/extract/sniim.py` uses the real ASP.NET form flow.
- Run the extractor from the repo root as `python -m src.extract.sniim ...` so package imports resolve correctly with the current layout.
- Preserve hidden fields and result-page validation; do not simplify the flow unless you verify the site still behaves correctly.
- Keep query metadata in the exported DataFrame so consulting outputs can be audited later.
- Preserve the report-header product label from the result page in the exported rows when available, because SNIIM may display a more specific market product name such as `Aguacate Hass`.
- Parser robustness matters because table headers and encodings can be inconsistent.
- Treat the portal's explicit `NO HAY REGISTROS` page as a valid empty market day, not a parser failure. Unknown result-page shapes must still fail loudly.

### Predictive analysis

- Preserve the generated feature Parquet metadata sidecars; they record source roots, coverage, and generation time.
- Use date-based train/test splits only. Never use random splitting for reservoir, production, or price forecasts.
- Compare every candidate model against the documented simple baselines.
- Only set XGBoost as the operational method for a horizon when it has lower out-of-sample MAE than every baseline.
- Keep non-winning candidate model artifacts for diagnostics, but label the selected `metodo_pronostico` in alert outputs.
- Reservoir alerts should only include dams observed within 45 days of the latest reservoir cut.
- Price alerts should only include markets observed within seven days of the latest SNIIM date.
- Production nowcast requires historical Avance cutoffs joined to Cierre outcomes from the same crop, state, and year. If fewer than 100 labeled cutoffs or fewer than two labeled years exist, use the historical baseline and state the limitation.
- Production nowcast executive outputs should expose an explicit comparison base for each crop-state forecast: prefer `anio anterior`, fall back to `promedio 5 anios`, and show `s/d` when neither exists instead of rendering `nan` percentages.
- If the user explicitly requests a demo override, `scripts.run_production_nowcast.py --force-model xgboost` and `scripts.run_analysis_pipeline.py --production-force-model xgboost` may be used, but the metrics and reports must say that the method was forced.
- The default dry scenarios are explicit assumptions: normal 0%, dry -8%, severe drought -15%. Do not present them as learned causal impacts.
- Optional climate input must use `id_conagua + fecha`.
- Optional international price inputs must be public and unauthenticated. Do not introduce API keys, tokens, Banxico SIE credentials, paid futures feeds, or hidden secrets for this v1.
- International proxy features must use `fecha_disponible` for joins to avoid future leakage. Proxies marked `diagnostico_only` must not enter model training.

### International public prices

- Prefer `scripts.fetch_public_international_prices` for direct public downloads that do not require credentials.
- World Bank Pink Sheet and FRED USD/MXN are fetched directly; USDA AMS and IMF are normalized from public CSV/XLS/XLSX files placed under `data/raw/international_prices/usda_ams/` and `data/raw/international_prices/imf/`.
- `config/products.xlsx` may include `proxies_internacionales` with `activo`, `producto_canonico`, `proxy_id`, `fuente`, `serie`, `tipo_proxy`, `uso_modelo`, `frecuencia`, `moneda`, `unidad_origen`, and `nota_metodologica`.
- Weak proxies such as orange for lemon must stay diagnostic by default unless temporal backtesting proves they improve the operational method.

### SIAP Cierre Agricola

- Prefer `src/extract/cierre_agricola_requests.py` first. It is faster and better for automation than browser-only scraping.
- Run the HTTP extractor from the repo root as `python -m src.extract.cierre_agricola_requests ...` so the package path stays consistent with the current layout.
- Use `python -m scripts.fetch_cierre_batch ...` when you need a year-by-product batch of normalized Cierre exports to feed the comparative workbook.
- The Cierre batch runner should create one timestamped run folder per invocation under `data/raw/cierre_agricola_batch/` so repeated exports stay grouped.
- Use Playwright only as a fallback when the HTTP/xajax flow changes or the portal behavior can no longer be reproduced reliably with requests.
- When debugging this source, keep `--debug` and `--debug-dir` workflows intact. The XML/HTML snapshots are valuable when the portal changes.
- Treat `debug_cierre_agricola/funciones_cierre.js` as a reverse-engineering aid for the original SIAP browser flow, not as runtime code used by the scraper.
- Preserve `cierre_crop_label_raw` and `cierre_unit_label` in normalized outputs so annual PMR can be reused later without losing the source unit context.
- Be careful with session-dependent behavior. The downloader depends on the xajax flow creating the report state before calling `reporte.php`.

### SIAP Avance Agricola

- Prefer `src/extract/avance_agricola_requests.py` for this source; it reuses the same HTTP/xajax family as Cierre but has a different query contract.
- Run the HTTP extractor from the repo root as `python -m src.extract.avance_agricola_requests ...` so the package path stays consistent with the current layout.
- The intended fixed path for this repo is `Por ubicacion geografica -> Por Entidad Federativa` with `Ciclicos - Perennes`, `Riego + Temporal`, `Nacional`, and `Todo` in the remaining combo filters; only expose year, month, and crop unless the product requirement changes.
- `llenaCultivo` depends on `anio + entidad + mes + ciclo + distrito + municipio`, and `reporte` appends `mesagric` at the end; preserve that exact order if the portal changes.
- Use `python -m scripts.fetch_avance_batch ...` when you need a month-by-product batch from `config/products.xlsx`.
- The Avance batch runner should create one timestamped run folder per invocation under `data/raw/avance_agricola_batch/` so repeated exports stay grouped.
- Preserve `avance_crop_label_raw`, `avance_unit_label`, `query_month`, `query_month_label`, and `report_cutoff_label` in normalized outputs so monthly cuts remain auditable.
- Default standalone outputs for this source should stay under `data/raw/avance_agricola/` unless the operator passes an explicit `--output`.
- If the user provides the internal `siembras_cosechas_*.csv`, prefer `python -m scripts.normalize_company_avance_history --years 2023 2024` to generate Avance-like historical XLSX files without overwriting the richer 2026 official exports.
- Treat that internal CSV as an area-only historical supplement: `SIEMBRA` maps to `superficie_sembrada_ha`, `COSECHA` maps to `superficie_cosechada_ha`, and the missing `produccion`, `rendimiento`, and `superficie_siniestrada` fields must remain empty rather than being fabricated.
- The current production pipeline assumes `anio + mes_corte` are same-calendar-year cutoffs, so the first-pass adapter should keep only `enero..diciembre` from the target agricultural year and leave `pre_*` / `pos_*` months out until calendar-year support is added explicitly.

### Walmart

- The scraper reads `__NEXT_DATA__` and ranks candidate products per configured crop.
- The standalone Walmart entrypoint should use `config/products.xlsx` by default when it exists, so `terminos_busqueda_walmart` stays aligned with the daily runner.
- Standalone Walmart outputs should default to `data/raw/walmart/`; only write elsewhere when the operator passes an explicit `--output`.
- When a configured Walmart crop is being scraped, reject results whose product name clearly infers a different crop instead of relabeling them to the configured product.
- Preserve blocked-page detection. Silent bad HTML is worse than an explicit failure.
- Ranking quality matters because consulting analyses need the best representative price per crop, not just any search result.

### Presas Agricolas

- `src/extract/presas_agricolas.py` should keep using the portal's direct JSON endpoints instead of browser automation as long as `js/funciones.php`, `js/graf.php`, `js/ajax/getInicio.php`, and `js/ajax/getAnios.php` remain stable.
- Treat `anio + mes + decena` as the source-of-truth query contract for snapshots, and `id_conagua + mes + decena + rango de anios` as the source-of-truth contract for historical series.
- For `presas_periodo`, an explicit `anio_final` in the config should expand the row into consecutive decena snapshots from the starting `anio/mes/decena` through the end of that year, capped by the portal's latest published period when needed.
- Support the explicit `presas_estado` batch mode by filtering snapshots on `estado` after retrieval, and treat that filter as part of the auditable query metadata.
- Preserve both the requested query metadata and the returned dam metadata in exports so later analysis can audit exactly which cut was retrieved.
- Keep the workbook bootstrap flow intact: `python -m src.extract.presas_agricolas --init-config` should generate a ready-to-run `config/presas_agricolas.xlsx`.
- Keep name-based lookup stable: if a query provides `nombre_oficial` and optional `estado`, the scraper should resolve `id_conagua` from `catalogo_presas` before calling the portal.
- For stronger catalog coverage, prefer `--catalog-scope all-available`; preserve catalog provenance fields such as periods observed and first/last seen period.
- Default standalone outputs for this source should stay under `data/raw/presas_agricolas/` unless the operator passes an explicit `--output`.

### Chedraui

- The scraper merges multiple search endpoints and deduplicates by normalized product identity.
- Standalone Chedraui outputs should default to `data/raw/chedraui/`; only write elsewhere when the operator passes an explicit `--output`.
- Keep query-term filtering strict enough to avoid unrelated produce contaminating a crop result.
- Treat current-price and old-price extraction carefully; promotion logic affects downstream analysis quality.

### Daily orchestrator

- `scripts/run_daily_extracts.py` is the main production-like entrypoint in this repo today.
- It is intentionally fault-tolerant: one source or one product row may fail without killing the entire run.
- Preserve `run_summary.json`, workbook metadata sheets, and per-source failure reporting.
- If you add a new source, integrate it in a way that keeps partial success possible and makes failures diagnosable per row and per source.

### Comparative workbook

- `scripts/build_master_price_workbook.py` should treat `data/daily_runs/YYYY-MM-DD` as the source of truth for daily comparison inputs.
- A practical refresh workflow is: run the daily scrapers, batch-fetch monthly Avance exports, then rebuild the master workbook against `--avance-root`; pass `--cierre-root` only when annual Cierre context is still useful.
- Keep the comparative output decision-complete for Excel analysis: one long panel sheet, one wide comparison sheet, and explicit supporting stats/coverage sheets.
- Avance Agricola is the primary agricultural-context layer for the comparative workbook and notebook; it should be aggregated by product-month and joined onto daily price rows by normalized `canonical_product + year + month`, where `canonical_product` is stored as a lowercase ASCII slug such as `aguacate`.
- Do not hide unit ambiguity for Cierre Agricola. Preserve and surface the annual PMR unit rather than pretending it is directly kg-comparable when it is not.
- When `--international-features` is provided, the workbook should include `precios_internacionales`, `cobertura_internacional`, and `mapa_proxies`.
- For the EDA notebook, all markdown, comments, figure titles, axis labels, legends, and other user-facing annotations must stay in Spanish.
- When mixing daily datetime series with monthly aggregates in the EDA notebook, keep the monthly plot on real datetimes and do not share that x-axis with the daily chart to avoid Matplotlib unit conflicts. For the Avance overlay on daily price charts, draw each monthly value only across its own month instead of carrying it forward until the next observed month.

## Data and output rules

- Treat generated outputs as disposable unless the user explicitly wants them committed.
- `.gitignore` already excludes `data/daily_runs/`, logs, and spreadsheet outputs such as `*.xlsx`, `*.xls`, and `*.csv`.
- New standalone scrapers should follow the same source-specific raw output layout: default under `data/raw/<source_slug>/` with timestamped filenames, while still allowing an explicit override flag for custom destinations.
- Generated analysis outputs under `data/analysis/` and climate Parquet under `data/raw/climate/` are disposable and ignored by git.
- `config/products.xlsx` is operationally important but is currently ignored by git, so do not assume config workbook changes will be versioned automatically.
- Preserve source provenance columns and exported metadata whenever possible.
- Prefer additive changes to schemas over breaking renames unless you update all downstream consumers and docs together.
- All user-facing text must be in Spanish by default. This includes titles, labels, graph names, workbook sheet names when meant for users, column names, summary fields presented to users, and any other visible output intended for business consumption. However, respond in the chat in English for clarity and consistency with the codebase, and only use Spanish in outputs when it is clearly intended for end users or when preserving source-native field names that are in Spanish.

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
- When adding or renaming any user-facing output, choose Spanish wording unless the user explicitly requests a different language or a source-native field must be preserved for provenance.
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
