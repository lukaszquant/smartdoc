# Plan v3: PDF Ingestion for wyniki_pdf/

Revised after second external review. Changes from v2 marked with **(REV2)**.

---

## Goal

Parse blood test results from PDF files in `wyniki_pdf/` and merge them into the existing data pipeline so they appear alongside CSV-sourced data in the report.

---

## PDF Inventory

| Format | Files | Count | Action |
|--------|-------|-------|--------|
| A: Diagnostyka S.A. | `20241218/` (8 excl. HISTORIA), `20250107/` (1), `20250602/` (4 excl. onko) | **13** | Parse |
| B: Read-Gene metals | `20250602/onko.pdf` | **1** | Parse (unit handling) |
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

### Step 2: Create `pdf_parser.py` — extraction layer

Format detection + per-format extractors returning intermediate dicts:

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

Format detection by first-page text signature:
- `'Diagnostyka S.A.'` -> diagnostyka
- `'read-gene'` or `'INNOWACYJNA MEDYCYNA'` -> readgene
- `'OMEGA TEST'` or `'SANNIO'` -> omega
- `'Warsaw Genomics'` or `'BadamyGeny'` -> genetic (skip)
- `'HISTORIA WYBRANYCH'` -> historia (skip)

### Step 3: Canonicalization into post-`load_raw_data()` schema

`load_pdf_data()` converts extraction output into the schema that `normalize_records()` consumes:

```python
{
    "Parametr": str,
    "Wynik": str,              # Value + unit, e.g. "178,60 mg/dl"
    "Zakres referencyjny": str,
    "source_file": str,
    "source_order_id": "",
    "source_badanie": str,
    "source_notes": str,
    "collected_at": datetime,
    "collected_date": date,
    "source_origin": "pdf",
}
```

**Read-Gene unit handling:**
- Selen, Arsen, Olow, Kadm: Use Read-Gene units directly (these markers already exist in catalog with matching or compatible units)
- Cynk, Miedz: **Skip** — whole-blood vs serum incompatibility

### Step 4: Integrate into `generate_report.py`

**4a:** In `load_raw_data()`, add `source_origin` column:
```python
raw_df["source_origin"] = "csv"
```

**4b:** **(REV2)** In `normalize_records()`, preserve `source_origin` in the output dict (~line 248-266):
```python
"source_origin": row.get("source_origin", "csv"),
```

**4c:** New wrapper function:
```python
def load_all_data() -> pd.DataFrame:
    csv_df = load_raw_data()
    if PDF_DIR.exists():
        from pdf_parser import load_pdf_data
        pdf_df = load_pdf_data(PDF_DIR)
        if not pdf_df.empty:
            combined = pd.concat([csv_df, pdf_df], ignore_index=True)
            return combined
    return csv_df
```

Replace `load_raw_data()` call in `main()` with `load_all_data()`.

**4d:** **(REV2, REV3)** Add CSV-preference rule in dedup. This applies to **all** same-day cross-source overlaps, not just value conflicts — because Step 1 dedup uses `source_order_id` in its key, CSV and PDF rows for the same measurement typically survive Step 1 even when values are identical.

Rule (applied before existing repeat/conflict logic in Step 2, ~line 321-340):
1. If both CSV and PDF rows exist for the same `marker_id` + `collected_date`, keep only CSV rows.
2. Within the preferred source, apply existing latest-timestamp selection.
3. Existing repeat/conflict bookkeeping (stats, flags) runs after this source-preference filter so counts remain accurate.

### Step 5: Extend marker_catalog.py

#### 5a: New GROUPS entry

```python
"kwasy_tluszczowe": "Kwasy tłuszczowe / Omega",
```

#### 5b: New marker definitions (omega indices only)

| marker_id | label_pl | unit | group | optimal | source |
|-----------|----------|------|-------|---------|--------|
| `indeks_omega3__direct` | Indeks Omega-3 | % | kwasy_tluszczowe | >8.0 | Harris & von Schacky 2004 |
| `aa_epa__ratio` | AA/EPA | ratio | kwasy_tluszczowe | 1.5-3.0 | Omega test guidelines |
| `omega6_omega3__ratio` | Omega-6/Omega-3 | ratio | kwasy_tluszczowe | 3.5-5.5 | Omega test guidelines |
| `indeks_tluszczow_trans__direct` | Indeks tłuszczów trans | % | kwasy_tluszczowe | <2.0 | Omega test guidelines |
| `nkt_jnkt__ratio` | NKT/JNKT | ratio | kwasy_tluszczowe | 1.7-2.0 | Omega test guidelines |

**(REV2)** No new entries for Selen, Arsen, Olow, Kadm — these already exist in the catalog. Only ALIAS_MAP entries needed for PDF name variants.

#### 5c: ALIAS_MAP entries

Exact strings confirmed during Step 2 testing, then added. Expected additions:

**Read-Gene PDF names** (to be verified):
```python
("Selen", "*"):  "selen__direct",      # if pdfplumber returns "Selen"
("Arsen", "*"):  "arsen__direct",      # verify against existing aliases
("Olow", "*"):   "olow__direct",       # verify exact string with diacritics
("Kadm", "*"):   "kadm__direct",       # verify exact string
```

**Omega PDF names:**
```python
("Indeks Omega-3", "*"):          "indeks_omega3__direct",
("AA/EPA", "*"):                  "aa_epa__ratio",
("Omega 6/omega 3", "*"):         "omega6_omega3__ratio",
("Indeks tłuszczów TRANS", "*"):  "indeks_tluszczow_trans__direct",
("NKT/JNKT", "*"):               "nkt_jnkt__ratio",
```

**Diagnostyka PDFs:** Likely identical to CSV names (same lab system). Add aliases only for actual mismatches found during testing.

### Step 6: Test and verify

1. `_tmp.py`: Extract each PDF format, print rows, verify values against visually read PDFs
2. Check pdfplumber marker name strings against ALIAS_MAP — confirm diacritics
3. Full `generate_report.py` run — verify:
   - New markers appear in report under correct groups
   - Overlapping data deduplicates correctly (CSV preferred)
   - No unexpected unmapped marker warnings
   - `source_origin` survives into consolidated data
4. Spot-check report values against PDF originals

### Step 7: Update CLAUDE.md

- Add `pdf_parser.py` to key files table
- Add `wyniki_pdf/` to sensitive data section (already gitignored)
- Note pdfplumber dependency in tech stack

---

## Execution Order

1. `pip install pdfplumber`
2. Write `pdf_parser.py` — Diagnostyka parser first (13 files)
3. Test with `_tmp.py` — capture exact pdfplumber strings, verify values
4. Add Read-Gene and Omega parsers
5. Add ALIAS_MAP entries using confirmed pdfplumber strings
6. Add omega markers + GROUPS entry to `marker_catalog.py`
7. Integrate into `generate_report.py` (`source_origin`, `load_all_data()`, dedup preference)
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
- **CSV/PDF overlap**: **(REV2, REV3)** Explicit CSV preference for all same-day cross-source overlaps (both repeats and conflicts). Log overlap count.
