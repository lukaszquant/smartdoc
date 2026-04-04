# Plan: PDF Ingestion for wyniki_pdf/

## Goal

Parse blood test results from 18 PDF files in `wyniki_pdf/` and merge them into the existing data pipeline so they appear alongside CSV-sourced data in the report.

---

## PDF Inventory & Format Analysis

### Format A: Diagnostyka S.A. (structured lab reports)
**Files (15):** All PDFs in `20241218/`, `20250107/`, `20250602/` except `HISTORIA_WYBRANYCH.pdf`

**Layout:** Consistent tabular format with columns: Badanie | Wynik | Jedn. | Zakres referencyjny | LIW

**Key fields extractable:**
- `Data/godz. pobrania:` -> collection datetime
- Marker name (e.g. "Cholesterol calkowity") -> Parametr
- Wynik (e.g. "178,60") -> numeric value
- Jedn. (e.g. "mg/dl") -> unit
- Zakres referencyjny (e.g. "115,00 - 190,00") -> lab range
- Descriptive notes below each marker (method, remarks)

**Extractable markers (from PDFs reviewed):**
- Lipidogram: Cholesterol calkowity, HDL, nie-HDL, LDL, Triglicerydy
- Homocysteina
- Morfologia krwi (full panel: 30+ parameters)
- Badanie ogolne moczu (qualitative - skip or flag)
- CRP wysokiej czulosci, Cynk
- Apo B, Czynnik reumatoidalny RF IgM, Testosteron wolny, IGF-1
- FT3, FT4, Testosteron, PSA (calkowity, wolny, wskaznik), anty-CCP
- Profil Dermatologiczny ELISA (Ratio values - not standard lab markers)

### Format B: Read-Gene / Innowacyjna Medycyna (metals panel)
**Files (1):** `20250602/onko.pdf`

**Layout:** Different lab, table with columns: Pierwiastek | Wynik | Podgrupa | Optymalne stezenie | Zalecana modyfikacja...

**Extractable markers:** Selen, Arsen, Olow, Kadm, Cynk, Miedz
**Date:** `Data pobrania: 2025-06-02 09:02:29`

### Format C: Sannio Tech / Omega Test
**Files (1):** `20250325/omega.pdf`

**Layout:** Multi-page report with fatty acid profile table on page 4. Columns: Grupy kwasow tluszczowych | Suma | Zakres referencyjny

**Extractable markers (indices only for now):** Indeks omega-3 (4.83%), AA/EPA (6.13), NKT/JNKT (1.83), Indeks tluszczow trans (0.23), Omega 6/omega 3 (7.29)
**Individual fatty acids:** ~25 compounds with values and ranges
**Date:** `DATA/GODZ. POBRANIA: 24/03/2025`

### Format D: Genetic test (excluded)
**Files (2):** `genetyczne/wynik.pdf`, `genetyczne/4163_...pdf`

**Content:** Gene mutation screening (KIF1B variant found). No numeric lab values.
**Decision: SKIP** - not blood test results, no numeric markers to track.

### Format E: History export (excluded)
**Files (1):** `20241218/HISTORIA_WYBRANYCH.pdf` (17KB, likely a summary)

**Decision: SKIP** - likely a historical summary, not primary results.

---

## Overlap with existing CSV data

Many Diagnostyka PDFs cover the same dates as existing CSVs (2024-12-18, 2025-01-07). The deduplication logic in Phase 2 will handle this, but we should:
1. Tag PDF-sourced records with `source_type="pdf"` so we can trace provenance
2. Let the existing dedup logic resolve conflicts (same marker + same date)
3. Log overlap stats so we know how much is truly new data

**Truly new data (not in CSVs):**
- `20250602/` files - June 2025 data (IGF-1 152.00, metals panel from Read-Gene)
- `20250325/omega.pdf` - Omega fatty acid profile (entirely new marker category)
- Some markers from `20241218/` that may not have CSV counterparts (dermatological profile, RF IgM, anty-CCP)

---

## Implementation Plan

### Step 1: Add pdfplumber dependency

```bash
.venv/bin/pip install pdfplumber
```

`pdfplumber` is the best fit here: it extracts tables from text-layer PDFs (no OCR needed - all these PDFs have embedded text). Lightweight, no system dependencies.

### Step 2: Create `pdf_parser.py` module

A new module with format-specific parsers that produce rows matching the normalized DataFrame schema from Phase 1.

```python
# pdf_parser.py

def load_pdf_data(pdf_dir: Path) -> pd.DataFrame:
    """Discover and parse all PDFs in wyniki_pdf/, return raw DataFrame
    matching the schema of load_raw_data() output."""
    ...

def _parse_diagnostyka_pdf(pdf_path: Path) -> list[dict]:
    """Parse Format A: Diagnostyka S.A. lab reports.
    Extract: collection date, marker rows (name, value, unit, range, notes)."""
    ...

def _parse_readgene_pdf(pdf_path: Path) -> list[dict]:
    """Parse Format B: Read-Gene metals panel.
    Extract: collection date, element rows (name, value, unit, optimal range)."""
    ...

def _parse_omega_pdf(pdf_path: Path) -> list[dict]:
    """Parse Format C: Sannio Tech omega test.
    Extract: collection date, fatty acid indices and individual compounds."""
    ...

def _detect_pdf_format(pdf_path: Path) -> str:
    """Detect PDF format by checking first-page text for known signatures:
    - 'Diagnostyka S.A.' or 'DIAGNOSTYKA' -> 'diagnostyka'
    - 'read-gene' or 'INNOWACYJNA MEDYCYNA' -> 'readgene'
    - 'OMEGA TEST' or 'SANNIO TECH' -> 'omega'
    - 'Warsaw Genomics' or 'BadamyGeny' -> 'genetic' (skip)
    """
    ...
```

**Output schema per row:**
```python
{
    "Badanie": str,          # Test panel name
    "Parametr": str,         # Marker name (matched to CSV naming where possible)
    "Kod zlecenia": "",      # Not available in PDFs
    "Data": str,             # Collection datetime as "DD-MM-YYYY HH:MM:SS"
    "Wynik": str,            # Value with unit, e.g. "178,60 mg/dl"
    "Zakres referencyjny": str,  # Lab range, e.g. "115,00 - 190,00"
    "Opis": str,             # Method notes
    "source_file": str,      # PDF filename for traceability
}
```

This matches the CSV raw schema so it feeds directly into `normalize_records()`.

### Step 3: Integrate into generate_report.py

Modify `load_raw_data()` (or add a call right after it) to:

```python
PDF_DIR = Path(__file__).parent / "wyniki_pdf"

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

### Step 4: Extend marker_catalog.py for new markers

Add ALIAS_MAP entries for markers only found in PDFs:

**Omega test indices (new group "kwasy_tluszczowe"):**
- `indeks_omega3__direct` (unit: %, optimal: >8)
- `aa_epa__ratio` (unit: ratio, optimal: 1.5-3.0)
- `omega6_omega3__ratio` (unit: ratio, optimal: 3.5-5.5)
- `indeks_tluszczow_trans__direct` (unit: %, optimal: <2.0)

**Metals from Read-Gene (may partially overlap existing):**
- `selen__direct` (unit: ug/l, optimal: 100-110)
- `arsen__direct` (unit: ug/l, optimal: 0.70-1.14)

**Dermatological / immunological markers (optional, low priority):**
- Skip Profil Dermatologiczny ELISA (Ratio values, not tracked over time)
- Skip Czynnik reumatoidalny RF IgM (one-time screening)
- Skip anty-CCP (one-time screening)

### Step 5: Handle edge cases

1. **Qualitative results** ("nie wykryto", "przejrzysty", "jasnozolty"): Skip rows where Wynik is non-numeric text (urine analysis from morfologia.pdf page 2)
2. **Comparator values** in PDFs: `<0,5 U/ml` (anty-CCP) - same parsing as CSVs
3. **Comma decimals**: PDFs use comma (e.g. "178,60") - already handled by `_parse_decimal()`
4. **Multi-page tables**: morfologia.pdf has table spanning pages 1-2, pdfplumber handles this per-page, concatenate results
5. **Sub-headers in tables**: "Morfologia krwi (ICD-9: C55)" is a section header, not a data row - filter by presence of numeric Wynik
6. **Date from directory name**: As fallback if date extraction from PDF text fails, use the directory name (e.g. `20241218` -> 2024-12-18)

### Step 6: Add `wyniki_pdf/` to CLAUDE.md and .gitignore

- Add `wyniki_pdf/` to `.gitignore` (sensitive health data, same as `wynki_diag/`)
- Update CLAUDE.md key files table

---

## Execution Order

1. Install pdfplumber
2. Write `pdf_parser.py` with `_detect_pdf_format()` + `_parse_diagnostyka_pdf()` first (covers 15/18 files)
3. Test with `_tmp.py` - verify row counts, spot-check values against visually read PDFs
4. Add `_parse_readgene_pdf()` and `_parse_omega_pdf()`
5. Test again
6. Add new marker catalog entries for omega/metals
7. Integrate into `generate_report.py` 
8. Run full report generation, verify new data appears
9. Update .gitignore and CLAUDE.md

---

## What NOT to do

- No OCR - all PDFs have text layers (verified by pdfplumber/Read tool reading them)
- No new dependencies beyond pdfplumber
- Don't parse genetic test PDFs (no numeric lab values)
- Don't parse `HISTORIA_WYBRANYCH.pdf` (summary document)
- Don't create a separate report section for PDF data - it merges into existing markers
- Don't change the existing CSV pipeline - only add PDF data alongside it

---

## Risk / Open Questions

1. **Table extraction reliability**: pdfplumber may struggle with some Diagnostyka PDFs if the table structure is irregular. Mitigation: test each PDF and add fallbacks.
2. **Marker name matching**: PDF marker names may differ slightly from CSV Parametr values (e.g. "Cholesterol calkowity" vs "Cholesterol calkowity"). Need to verify exact strings from pdfplumber output.
3. **Duplicate data**: Some PDF data duplicates CSV data for same dates. The existing Phase 2 dedup should handle this, but we should verify.
4. **Unit format from Read-Gene**: Uses ug/l vs ug/dl - need to check against existing marker catalog units and convert if needed.
