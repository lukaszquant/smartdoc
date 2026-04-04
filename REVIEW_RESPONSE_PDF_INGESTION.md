# Review Response: PDF Ingestion Plan

## Finding 1 (High): Schema mismatch — PDF output vs post-loader schema

**Agree.** The reviewer is correct: `load_raw_data()` already renames columns and parses dates before returning. The plan's proposed `pd.concat` would produce a mixed-schema DataFrame.

**Resolution:** PDF parsing will output the post-`load_raw_data()` schema directly (with `collected_at`, `collected_date`, `source_order_id`, `source_badanie`, `source_notes`, `source_file`). This is simpler than refactoring the CSV loader — the CSV path works fine, and we just need the PDF path to match its output. No shared canonicalization function needed (answering Open Question 1).

## Finding 2 (High): ug/l vs ug/dl silent corruption

**Agree.** This is the most dangerous finding. The Read-Gene PDF reports metals in `µg/l` (whole blood), while the existing catalog defines Cynk and Miedź in `µg/dl`. The wildcard alias match would silently assign wrong units.

**Resolution:** The Read-Gene parser will perform explicit unit conversion:
- Cynk: Read-Gene reports `6182.80 µg/l` which is whole-blood zinc. The catalog has `µg/dl`. Conversion: `µg/l ÷ 10 = µg/dl`, so `6182.80 µg/l = 618.28 µg/dl`. But wait — the catalog optimal range is `70-100 µg/dl` and the Diagnostyka PDF from 2024-12-18 shows `100.00 µg/dl` for cynk. The Read-Gene value of 618.28 µg/dl is way off — this suggests Read-Gene uses a different specimen type (whole blood vs serum). These are **not comparable measurements** and should be treated as separate markers or skipped.
- Miedź: Read-Gene reports `761.67 µg/l`. Catalog has `µg/dl`. Same issue — different specimen.

**Revised approach:** Read-Gene metals that use whole-blood concentrations (µg/l) will be stored as separate markers with `__whole_blood` suffix (e.g. `cynk__whole_blood`) or skipped entirely if they can't be meaningfully compared to serum values. For Selen, Arsen, Olow, Kadm — these don't have existing catalog entries, so we add them with the Read-Gene units directly.

## Finding 3 (Medium): `source_type` field collision

**Agree.** `source_type` already means evidence provenance (LAB/GUIDELINE/HEURISTIC) in the marker catalog. Reusing it would corrupt metadata.

**Resolution:** Use `source_origin` field with values `"csv"` or `"pdf"`. Added during raw data loading, carried through normalization. Existing CSV records get `source_origin="csv"` for symmetry.

## Finding 4 (Medium): Marker name matching is exact-string, no normalization

**Agree.** pdfplumber will return the exact text from the PDF, including diacritics. The alias map requires exact matches. The plan assumed implicit normalization that doesn't exist.

**Resolution:** Two-pronged approach:
1. First, test pdfplumber output against actual PDFs to capture exact strings (diacritics should be preserved since these are text-layer PDFs, not OCR).
2. Then add any PDF-specific name variants to ALIAS_MAP. This is safer than adding a fuzzy normalization layer — exact matches are deterministic and auditable.

Expected: most Diagnostyka PDF names will match CSV names exactly (same lab system). Read-Gene and Omega names will need new ALIAS_MAP entries.

## Finding 5 (Medium): Omega group not in GROUPS

**Agree.** Adding markers without updating `GROUPS` would make them invisible in the report.

**Resolution:** Add `"kwasy_tluszczowe": "Kwasy tluszczowe / Omega"` to `GROUPS` dict in marker_catalog.py as part of Step 4.

## Finding 6 (Low): File count errors and redundant .gitignore step

**Agree.** Correct count: 18 total - 2 genetic - 1 history - 1 Read-Gene - 1 omega = **13 Diagnostyka PDFs**. And .gitignore already covers wyniki_pdf/.

**Resolution:** Fix counts in the plan. Remove .gitignore from execution checklist.

## Open Question 2: Source preference for CSV/PDF overlap

The current timestamp-based dedup resolution is acceptable. Both sources should produce identical values for the same marker+date. If there's a conflict, we log it and prefer CSV (as the established source). This is implemented by concatenating CSV first, so in case of tie-breaking the CSV row appears earlier.
