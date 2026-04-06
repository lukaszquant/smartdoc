# Claude Code conventions for smartdoc

## Project overview

Reusable Python script (`generate_report.py`) that generates an interactive HTML health report in Polish from ~77 CSV blood test files and ~15 PDF files (2022-2026). Built in 6 phases:

1. **Data ingestion** — parse semicolon-delimited CSVs from `wynki_diag/` and PDFs from `wyniki_pdf/` (OCR via tesseract for Diagnostyka/Read-Gene, pdfplumber for Omega), normalize dates, handle comparators (`<`, `>`)
2. **Deduplication** — consolidate duplicate files (e.g. `(1)` suffixes), resolve conflicting values
3. **Marker catalog** — canonical `marker_id` mapping, optimal ranges (preventive medicine, not just lab norms), status assessment (OK / GRANICA OPT / POWYŻEJ OPT / POWYŻEJ NORMY / etc.)
4. **Trend analysis** — Theil–Sen slope + Mann–Kendall test with sufficiency gate, bootstrap CI, same-day collapse; trend states (supported_up/down, no_clear_trend, insufficient)
5. **Recommendations** — prioritized, Polish-language recs covering diet, supplementation, lifestyle, retesting
6. **HTML report** — Jinja2 template with Plotly interactive charts, trend summaries, color-coded status badges

## Key files

| File | Description |
|---|---|
| `generate_report.py` | Main script (~3300 lines) — all 6 phases |
| `config.json` | Local config for data paths (gitignored, see `config.example.json`) |
| `config.example.json` | Example config template with default relative paths |
| `pdf_parser.py` | PDF extraction layer — OCR (Diagnostyka, Read-Gene) + pdfplumber (Omega), with per-file cache |
| `marker_catalog.py` | `MARKERS` dict (canonical marker definitions, optimal ranges, units) and `GROUPS` |
| `report_template.html` | Jinja2 HTML template with Plotly chart rendering |
| `wynki_diag/` | Input CSV data (sensitive, gitignored) |
| `wyniki_pdf/` | Input PDF data (sensitive, gitignored) |
| `.pdf_cache/` | Per-PDF extraction cache (sensitive, gitignored) |
| `raport_zdrowotny.html` | Generated output (sensitive, gitignored) |
| `PLAN/` | Plans and reviews, organized by feature and version |
| `PLAN/ANALIZY/v1/` | Original project plan in Polish |
| `PLAN/PDF_INGESTION/` | PDF ingestion plans, reviews, validations (v1–v3) |
| `PLAN/SPECIALIST_RECS/` | Specialist recommendations plan and review |
| `PLAN/TREND_ROBUSTNESS/` | Trend robustness refactor plan and review |
| `NOTES/` | Implementation notes (NOTES_PHASE1–6.md, NOTES_PDF_CACHE.md) |
| `tests/` | pytest test suite (trend stats, trend state, ingestion, recs, etc.) |

## Tech stack

- Python 3.12, virtualenv at `.venv/`
- pandas, numpy, plotly 6.6, jinja2 3.1
- pdfplumber, PyMuPDF (fitz) — PDF parsing
- tesseract-ocr (system) — OCR for CID-encoded/image-only PDFs
- playwright (headless Chromium) — PDF export of generated HTML reports
  - Install: `.venv/bin/pip install playwright && .venv/bin/playwright install chromium`
- Report language: Polish

## Running the generator

```bash
.venv/bin/python3 generate_report.py
```

Output: `raport_zdrowotny.html`

### Configuration

Copy `config.example.json` to `config.json` and adjust paths. All paths can be absolute or relative to the script directory. If `config.json` is absent, defaults to `wynki_diag/` and `wyniki_pdf/` in the project root.

```json
{
  "data_dir": "/path/to/wynki_diag",
  "pdf_dir": "/path/to/wyniki_pdf",
  "output_path": "raport_zdrowotny.html",
  "pdf_cache_dir": ".pdf_cache"
}
```

Set `SMARTDOC_NO_PDF_CACHE=1` to disable the PDF extraction cache for a run.

## Running temporary test scripts

Use the **Write tool** to create throwaway scripts as `_tmp_<unique>.py` (e.g., `_tmp_a3f2.py`, `_tmp_check_9x.py`) in the project root. Use a short random suffix to avoid conflicts when multiple sessions run in parallel. Then run with:

```bash
.venv/bin/python3 _tmp_<unique>.py 2>&1
```

Clean up after use:

```bash
rm _tmp_*.py
```

Do NOT use `cat << 'PYEOF'`, `python3 << 'EOF'`, or any bash heredocs — use the Write tool to create the file, then run it. This keeps both steps auto-approved.

This ensures the correct virtualenv is used and both stdout and stderr are captured.

## Running one-off commands

Always use `_tmp*.py` for quick checks (dependency availability, data exploration, etc.) instead of running Python one-liners directly in the shell.

## Running tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```

## PDF cache and PARSER_VERSION

`pdf_parser.py` caches per-PDF extraction results in `.pdf_cache/`. The cache is keyed by relative source path and validated by file fingerprint (size + mtime, SHA-1 fallback).

**When editing `pdf_parser.py`, bump `PARSER_VERSION`** if your change alters:
- the row schema returned by any parser (`_parse_diagnostyka`, `_parse_readgene`, `_parse_omega`)
- the format detection logic in `_detect_format` or `_classify_text` (e.g. making a previously-`unknown` file parseable)

Forgetting to bump will cause stale cached rows or stale skip-format decisions to persist silently.

## Sensitive data

`wynki_diag/` (raw CSVs), `wyniki_pdf/` (PDF results), and `raport_zdrowotny.html` (generated report) contain personal health data. All are gitignored. Never commit these.

## Keeping structured notes

When implementing multi-step work (patches, new features, reviews), keep structured notes as you go. Update the relevant `NOTES/NOTES_PHASE*.md` file with:
- What was changed and why
- Validation results (counts, status checks, test outcomes)
- Known differences or design decisions
- Impact summary

This ensures future conversations have full context without re-deriving it.

## Planning new features

When planning a new feature or significant change:

1. **Create a plan file** in `PLAN/<FEATURE_NAME>/PLAN_v1.md` (increment version for revisions).
2. **Present the plan** to the user for approval before implementing.
3. Plans stay in `PLAN/` for reference — they are gitignored.

Do NOT put plans inline in the conversation. Always write them to a file.

## Handling external reviews

When reacting to an external review of the implementation:

1. **First** — write a `REVIEW_RESPONSE_<phase>.md` file with analysis of each finding (agree/disagree, root cause, impact).
2. **Second** — write a `REVIEW_PLAN_<phase>.md` file with the concrete fix plan (what to change, where, in what order).
3. **Stop and present both files** to the user for approval before implementing any fixes.
