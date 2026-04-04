# Plan v2: PDF Ingestion for wyniki_pdf/

Revised after external review. Changes from v1 marked with **(REV)**.

---

## Goal

Parse blood test results from PDF files in `wyniki_pdf/` and merge them into the existing data pipeline so they appear alongside CSV-sourced data in the report.

---

## PDF Inventory (corrected counts)

| Format | Files | Count | Action |
|--------|-------|-------|--------|
| A: Diagnostyka S.A. | `20241218/` (8 files excl. HISTORIA), `20250107/` (1), `20250602/` (4 excl. onko) | **13** | Parse |
| B: Read-Gene metals | `20250602/onko.pdf` | **1** | Parse (with unit handling) |
| C: Omega Test | `20250325/omega.pdf` | **1** | Parse |
| D: Genetic tests | `genetyczne/` (2 files) | **2** | Skip |
| E: History export | `20241218/HISTORIA_WYBRANYCH.pdf` | **1** | Skip |
| **Total** | | **18** | **15 parsed, 3 skipped** |

---

## Implementation Steps

### Step 1: Install pdfplumber

```bash
.venv/bin/pip install pdfplumber
```

Text-layer extraction only, no OCR needed (verified all PDFs have embedded text).

### Step 2: Create `pdf_parser.py` — extraction layer

New module. Each format-specific parser extracts raw text/tables from PDFs and returns intermediate dicts.

```python
def _detect_pdf_format(pdf_path: Path) -> str:
    """First-page text signature detection:
    - 'Diagnostyka S.A.' -> 'diagnostyka'
    - 'read-gene' or 'INNOWACYJNA MEDYCYNA' -> 'readgene'
    - 'OMEGA TEST' or 'SANNIO' -> 'omega'
    - 'Warsaw Genomics' or 'BadamyGeny' -> 'genetic' (skip)
    - 'HISTORIA WYBRANYCH' -> 'historia' (skip)
    """
```

**Extraction functions** return lists of dicts with raw extracted fields:
```python
{
    "parametr": str,           # Marker name exactly as in PDF
    "wynik_raw": str,          # Raw value string, e.g. "178,60"
    "unit": str,               # Unit, e.g. "mg/dl"
    "range_raw": str,          # Reference range string
    "badanie": str,            # Test panel name
    "notes": str,              # Method notes
    "collected_at": datetime,  # Parsed from PDF header
    "source_file": str,        # PDF filename
}
```

### Step 3: Create canonicalization layer in `pdf_parser.py` **(REV)**

A `load_pdf_data()` function that:
1. Calls extraction functions per PDF
2. Canonicalizes output into the **post-`load_raw_data()` schema** — the same column set that `normalize_records()` expects as input

**(REV)** This directly addresses Finding 1. The output matches what `load_raw_data()` returns:
```python
{
    "Parametr": str,
    "Wynik": str,              # Value + unit combined, e.g. "178,60 mg/dl"
    "Zakres referencyjny": str,
    "source_file": str,
    "source_order_id": "",     # Not available in PDFs
    "source_badanie": str,     # Panel name
    "source_notes": str,       # Method notes
    "collected_at": datetime,
    "collected_date": date,
    "source_origin": "pdf",    # (REV) New provenance field, not source_type
}
```

**(REV)** Unit conversion for Read-Gene rows happens here:
- **Selen, Arsen, Olow, Kadm**: No existing catalog entries -> add with Read-Gene units (`µg/l`) directly
- **Cynk, Miedz**: Read-Gene measures whole blood (`µg/l`), catalog has serum (`µg/dl`). These are **incomparable specimen types**. Create separate markers `cynk__whole_blood` and `miedz__whole_blood`, or skip these two if they add no analytical value (only one data point each). **Decision: skip Cynk and Miedz from Read-Gene** — one whole-blood measurement can't be compared to the serum time series from Diagnostyka.

### Step 4: Integrate into `generate_report.py`

Minimal change — add `source_origin` column to CSV data for symmetry, then concat:

```python
PDF_DIR = Path(__file__).parent / "wyniki_pdf"

# In load_raw_data(), after building the DataFrame:
raw_df["source_origin"] = "csv"  # (REV) new provenance field

# New wrapper:
def load_all_data() -> pd.DataFrame:
    csv_df = load_raw_data()
    if PDF_DIR.exists():
        from pdf_parser import load_pdf_data
        pdf_df = load_pdf_data(PDF_DIR)
        if not pdf_df.empty:
            combined = pd.concat([csv_df, pdf_df], ignore_index=True)
            log.info("Combined %d CSV + %d PDF = %d total raw records",
                     len(csv_df), len(pdf_df), len(combined))
            return combined
    return csv_df
```

Replace the `load_raw_data()` call in `main()` with `load_all_data()`.

### Step 5: Extend marker_catalog.py **(REV)**

#### 5a: New GROUPS entry **(REV)**

```python
"kwasy_tluszczowe": "Kwasy tłuszczowe / Omega",
```

#### 5b: New marker definitions

**Omega indices (group: kwasy_tluszczowe):**
| marker_id | label_pl | unit | optimal | source |
|-----------|----------|------|---------|--------|
| `indeks_omega3__direct` | Indeks Omega-3 | % | >8.0 | Harris & von Schacky 2004 |
| `aa_epa__ratio` | AA/EPA | ratio | 1.5-3.0 | Omega test guidelines |
| `omega6_omega3__ratio` | Omega-6/Omega-3 | ratio | 3.5-5.5 | Omega test guidelines |
| `indeks_tluszczow_trans__direct` | Indeks tłuszczów trans | % | <2.0 | Omega test guidelines |
| `nkt_jnkt__ratio` | NKT/JNKT | ratio | 1.7-2.0 | Omega test guidelines |

**Metals — new entries (group: metale):**
| marker_id | label_pl | unit | optimal | source |
|-----------|----------|------|---------|--------|
| `selen__direct` | Selen | µg/l | 100-130 | Read-Gene |
| `arsen__direct` | Arsen | µg/l | 0.70-1.14 | Read-Gene |

Note: Olow and Kadm already exist in the catalog. Verify their units match Read-Gene before adding aliases.

#### 5c: New ALIAS_MAP entries **(REV)**

**(REV)** Exact strings from pdfplumber output (to be confirmed during Step 2 testing, then added):

**Diagnostyka PDFs** — likely identical to CSV names (same lab system). Verify during testing; add aliases only for actual mismatches.

**Read-Gene PDFs:**
```python
("Selen", "*"):     "selen__direct",
("Arsen", "*"):     "arsen__direct",
# Olow, Kadm: check exact pdfplumber strings against existing aliases
```

**Omega PDFs:**
```python
("Indeks Omega-3", "*"):          "indeks_omega3__direct",
("AA/EPA", "*"):                  "aa_epa__ratio",
("Omega 6/omega 3", "*"):         "omega6_omega3__ratio",
("Indeks tłuszczów TRANS", "*"):  "indeks_tluszczow_trans__direct",
("NKT/JNKT", "*"):               "nkt_jnkt__ratio",
```

### Step 6: Test and verify

1. Write `_tmp.py` to extract each PDF format and print rows — verify against visually read values
2. Check exact pdfplumber marker name strings against ALIAS_MAP
3. Run full `generate_report.py` — verify:
   - New markers appear in report
   - Overlapping data (same marker+date from CSV and PDF) deduplicates correctly
   - No unmapped marker warnings for expected markers
4. Spot-check report values against PDF originals

### Step 7: Update CLAUDE.md

- Add `wyniki_pdf/` to sensitive data section (already gitignored)
- Add `pdf_parser.py` to key files table
- Note pdfplumber dependency

---

## Execution Order Summary

1. `pip install pdfplumber`
2. Write `pdf_parser.py` — Diagnostyka parser first (13 files)
3. Test with `_tmp.py` — capture exact pdfplumber strings
4. Add Read-Gene and Omega parsers
5. Add ALIAS_MAP entries using confirmed pdfplumber strings
6. Add new markers + GROUPS entry to `marker_catalog.py`
7. Integrate into `generate_report.py` (add `source_origin`, `load_all_data()`)
8. Full test run
9. Update CLAUDE.md

---

## Edge Cases

- **Qualitative results** ("nie wykryto", "przejrzysty"): Skip rows with non-numeric Wynik
- **Comparators** (`<0,5`): Same parsing as CSVs via `_parse_wynik()`
- **Comma decimals** (`178,60`): Handled by existing `_parse_decimal()`
- **Multi-page tables** (morfologia): Concatenate per-page pdfplumber results
- **Section headers** ("Morfologia krwi (ICD-9: C55)"): Filter by presence of numeric value
- **Date fallback**: Use directory name (e.g. `20241218`) if PDF header date extraction fails
- **CSV/PDF overlap**: CSV rows appear first in concat; existing dedup resolves ties. Log overlap count.
