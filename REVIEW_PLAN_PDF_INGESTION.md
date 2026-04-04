# Review: PDF Ingestion Plan

Plan reviewed: [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md)

Overall assessment: the direction is reasonable, but the plan is not implementation-ready as written. The biggest problems are a schema mismatch with the current loader, a provenance-field collision, and a unit-conversion gap that would silently corrupt some Read-Gene measurements.

## Findings

1. High: the proposed PDF DataFrame shape does not match what the current pipeline passes into normalization.

The plan says `load_pdf_data()` should emit rows with `Badanie`, `Kod zlecenia`, `Opis`, `Data`, and the other CSV-style raw columns, then concatenate that directly with the output of `load_raw_data()` in Step 3. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L90-L161). That is incompatible with the current code. `load_raw_data()` does not return the untouched CSV schema: it already parses dates into `collected_at` and `collected_date`, and it renames `Kod zlecenia`, `Badanie`, and `Opis` into `source_order_id`, `source_badanie`, and `source_notes`. See [generate_report.py](generate_report.py#L130-L149). `normalize_records()` then reads those renamed columns directly. See [generate_report.py](generate_report.py#L225-L265). As written, the plan's `pd.concat([csv_df, pdf_df])` will yield a mixed schema and either fail during normalization or inject nulls into fields the rest of the pipeline expects.

The plan should be revised to do one of two things: either make PDF parsing output the post-`load_raw_data()` schema, or refactor CSV and PDF ingestion to share a single canonicalization step before normalization.

2. High: `ug/l` versus `ug/dl` cannot remain an open question, because the current alias map would silently assign some PDF values to the wrong unit system.

The plan correctly flags a Read-Gene unit mismatch as a risk, but it leaves it as a follow-up question instead of making conversion part of the core implementation. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L173-L175) and [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L223-L228). In the current catalog, `Cynk` and `Miedź` are defined as `µg/dl`. See [marker_catalog.py](marker_catalog.py#L381-L390). Their aliases also use wildcard unit matching, which means the resolver ignores the incoming unit string and maps by name alone. See [marker_catalog.py](marker_catalog.py#L734-L735) and [marker_catalog.py](marker_catalog.py#L779-L793). If the PDF parser emits Read-Gene zinc or copper in `µg/l`, those values will still resolve to the existing marker IDs and then be assessed against the wrong unit and optimal range.

This is silent data corruption. The plan should require unit normalization before `resolve_marker_id()` for all Read-Gene markers, not treat it as optional validation work.

3. Medium: the proposed provenance field reuses an existing field name that already has a different meaning in the report.

The plan proposes tagging PDF rows with `source_type="pdf"` to track provenance. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L64-L69). In the current code, `source_type` already means evidence provenance from the marker catalog, for example `LAB`, `GUIDELINE`, or `HEURISTIC`. It is added during status assessment and later shown in summaries. See [generate_report.py](generate_report.py#L590-L605) and [generate_report.py](generate_report.py#L675-L683). Reusing that field for file provenance would either overwrite clinically meaningful metadata or create ambiguous mixed semantics.

The plan should introduce a separate ingestion-provenance field, for example `source_origin`, `source_medium`, or `input_format`.

4. Medium: marker matching is understated; the current resolver is exact-string based, but the plan assumes name normalization that does not exist.

The plan says PDF `Parametr` values should be matched to the CSV naming where possible and gives examples such as `Cholesterol calkowity`, `CRP wysokiej czulosci`, `Olow`, and `Miedz`. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L16-L32) and [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L39-L49). The current alias map expects exact strings, including Polish diacritics and exact wording, for example `Cholesterol całkowity`, `CRP wysokiej czułości`, `Miedź`, and `Ołów we krwi`. See [marker_catalog.py](marker_catalog.py#L683-L691) and [marker_catalog.py](marker_catalog.py#L734-L745). `resolve_marker_id()` does only exact tuple lookup followed by a wildcard-unit fallback; there is no text normalization layer. See [marker_catalog.py](marker_catalog.py#L779-L793).

Without an explicit normalization step or a much broader alias table, many PDF rows will remain unmapped. That also weakens the plan's assumption that the existing dedupe logic will cleanly handle CSV/PDF overlap, because unmapped rows bypass marker-level deduplication.

5. Medium: the omega group is not fully integrated into the current report structure.

Step 4 introduces a new group called `kwasy_tluszczowe`, but it only calls out new marker definitions and aliases. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L163-L171). The current report code iterates groups from `GROUPS`, and the HTML group sections are built only for keys declared there. See [marker_catalog.py](marker_catalog.py#L40-L53) and [generate_report.py](generate_report.py#L1823-L1835). If implementation adds omega markers without also extending `GROUPS`, they may appear as unknown in some summaries and will not render in the normal per-group report sections.

The plan should explicitly include a `GROUPS` update as part of marker-catalog work.

6. Low: a few planning details are already inaccurate or redundant.

The plan says Format A covers 15 files and that the first parser covers `15/18` PDFs. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L11-L12) and [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L198-L203). The current workspace has 18 PDFs total, but only 13 Diagnostyka PDFs after excluding the one history export, the two genetic reports, the Read-Gene file, and the omega file. Also, `wyniki_pdf/` is already ignored in [.gitignore](.gitignore#L1-L4), so Step 6 is only partially needed. See [PLAN_PDF_INGESTION.md](PLAN_PDF_INGESTION.md#L191-L194).

These are not blockers by themselves, but they are a sign that the execution order should be tightened before implementation starts.

## Recommended Plan Changes

1. Split PDF ingestion into two explicit layers: extraction from PDF text, then canonicalization into the same post-loader schema currently consumed by `normalize_records()`.
2. Make unit normalization mandatory for Read-Gene rows before marker resolution, especially for `Cynk` and `Miedź`.
3. Use a dedicated provenance field instead of `source_type`.
4. Add a marker-name normalization strategy up front: either normalize extracted text before alias lookup or expand the alias map to cover the PDF spellings actually returned by `pdfplumber`.
5. Explicitly update `GROUPS` when adding omega markers.
6. Correct the file counts and remove the already-completed `.gitignore` step from the execution checklist.

## Open Questions

1. Should PDF records be canonicalized directly into the current post-`load_raw_data()` shape, or should CSV ingestion be refactored so both sources share one canonicalization function?
2. For same-day CSV/PDF overlap, do you want a deterministic source-preference rule, or is the current timestamp-based resolution acceptable once marker mapping is reliable?