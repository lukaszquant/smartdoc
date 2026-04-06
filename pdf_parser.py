"""
pdf_parser.py — Extract blood test results from PDF files in wyniki_pdf/.

Supports three formats:
  - Diagnostyka S.A. (CID-encoded fonts → OCR via fitz+tesseract)
  - Read-Gene / Innowacyjna Medycyna (image-only → OCR via fitz+tesseract)
  - Omega Test / Sannio Tech (text-layer → pdfplumber table extraction)

Skipped formats:
  - Genetic tests (Warsaw Genomics / BadamyGeny)
  - HISTORIA WYBRANYCH (history export)

Returns a DataFrame matching the post-load_raw_data() schema consumed by
normalize_records() in generate_report.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, date
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
import pdfplumber

LOG = logging.getLogger("smartdoc.pdf")

# Cache schema version — covers both the parser row layout AND the format
# detector. Bump when parser output changes OR when _detect_format() is changed
# in a way that could reclassify previously-seen PDFs (e.g. making a file that
# was "unknown" parseable). Stale cache entries are then ignored.
PARSER_VERSION = 1

# ---------------------------------------------------------------------------
# OCR helper
# ---------------------------------------------------------------------------

def _ocr_page(page: fitz.Page, dpi: int = 300) -> str:
    """Render a PyMuPDF page to image and OCR with tesseract."""
    pix = page.get_pixmap(dpi=dpi)
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        pix.save(tmp.name)
        result = subprocess.run(
            ["tesseract", tmp.name, "-", "-l", "eng", "--psm", "6"],
            capture_output=True, text=True,
        )
        return result.stdout


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def _detect_format(pdf_path: Path) -> str:
    """Detect PDF format from first-page content.

    Returns one of: 'diagnostyka', 'readgene', 'omega', 'genetic', 'historia'.
    """
    # Try pdfplumber text layer first (works for omega)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = pdf.pages[0].extract_text() or ""
            if text and "(cid:" not in text:
                return _classify_text(text)
    except Exception:
        pass

    # Fall back to OCR for CID-encoded or image-only PDFs
    doc = fitz.open(str(pdf_path))
    try:
        text = _ocr_page(doc[0])
        return _classify_text(text)
    finally:
        doc.close()


def _classify_text(text: str) -> str:
    """Classify format from extracted/OCR text."""
    text_lower = text.lower()
    # Check specific formats BEFORE Diagnostyka (Read-Gene mentions "Diagnostyka S.A." as ordering party)
    if "read-gene" in text_lower or "innowacyjna medycyna" in text_lower:
        return "readgene"
    if "omega test" in text_lower or "sannio" in text_lower:
        return "omega"
    if "warsaw genomics" in text_lower or "badamygeny" in text_lower:
        return "genetic"
    if "historia wybranych" in text_lower:
        return "historia"
    if "diagnostyka" in text_lower or "sprawozdanie z badania" in text_lower:
        return "diagnostyka"
    return "unknown"


# ---------------------------------------------------------------------------
# Diagnostyka S.A. parser (OCR)
# ---------------------------------------------------------------------------

# Date in header: "Data/godz. pobrania: 2024-12-18 08:49"
_RE_DIAG_DATE = re.compile(
    r'Data/godz\.\s*pobrania:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})',
    re.IGNORECASE,
)

# Result line pattern — captures marker name, value, unit, range
# Examples from OCR:
#   Leukocyty 2,69 tys/pl* 4,23 - 9,07 L
#   Cholesterol catkowity 268,70 mg/dl 115,00 - 190,00 H
#   AST 25 U/L 0 - 40
#   eGFR (ICD-9: M37) >90 ml/min/1,73m2* -
#   TSH (ICD-9: L69) 2,220 ulU/ml* 0,270 - 4,200
_RE_DIAG_RESULT = re.compile(
    r'^(?P<name>[A-Za-z][A-Za-z0-9 \-\(\)/#%.,éèêëàâäùûüôöîïçñ]+?)'  # marker name
    r'\s+'
    r'(?P<comp>[<>≤≥]?)\s*'                     # optional comparator
    r'(?P<value>\d+[.,]?\d*)'                   # numeric value
    r'\s+'
    r'(?P<unit>[^\s]+(?:/[^\s]+)*\*?)'          # unit (may contain /, may end with *)
    r'(?:\s+'
    r'(?P<range>.+?))?'                         # optional range
    r'\s*(?P<liw>[LH])?\s*$'                    # optional L/H flag
)

# Valid unit patterns (after OCR cleanup) — used to filter false positives
_VALID_UNITS = {
    "tys/µl", "mln/µl", "g/dl", "mg/dl", "ng/ml", "pg/ml", "µg/l", "µg/dl",
    "µIU/ml", "mmol/l", "µmol/l", "U/l", "%", "fl", "pg", "TU/ml", "U/ml",
    "Ratio", "IU/ml", "mm/h", "g/l", "ml/min/1,73m2", "ng/dl", "pmol/l",
    "nmol/l", "mIU/ml", "s", "mg/l",
}

# Section header: "Morfologia krwi (ICD-9: C55)" or standalone test name
_RE_DIAG_SECTION = re.compile(
    r'^(?P<badanie>[A-Za-z][A-Za-z0-9 \-().,éèêëàâäùûüôöîïçñ]+?)\s*\(ICD-9:\s*\w+\)'
)

# Lines to skip
_RE_DIAG_SKIP = re.compile(
    r'(?:Badanie wykonano|Strona:|Informacje dodatkowe|Data wygenerowania|'
    r'Oznacza, ze|LIW - Laboratoryjna|Dowiedz sie|kontynuacja z poprzedniej|'
    r'Diagnostyka S\.A\.|MEDYCZNE LABORATORIUM|SPRAWOZDANIE|Zlecajacy:|Oddziat:|'
    r'Lekarz kierujacy|Odbiorca wyniku|Pacjent:|Adres:|Plee:|Data rejestracji|'
    r'Data urodzenia|Nr ksiegi|prof\. M\.|Jutrzenki|Badanie\s+Wynik\s+Jedn|'
    r'Badanie\s+Daty\s+Materiat|Data/godz\.\s*przyjecia|Data/godz\.\s*wydania|'
    r'Data wykonania|Brak uwag|Dokument zawiera|mgr\s|Wersja:|\*\*\*|'
    r'Stezenie zalecane|Ponizej\s|prawidiowa|niewiele obnizona|umiarkowanie|'
    r'znamiennie|niewydolnosc|schytkowa|nieprawidtowa glikemia|cukrzyca|'
    r'wg aktualnych|Wz6r wg|Wynik wyliczono|Zgodnie z zaleceniami|'
    r'Deficyt|suboptymalne|\boptymalne\b|\bwysokie\b|\btoksyczne\b|'
    r'Oznaczenie wykonano|W przypadku|'
    r'ul\.\s*prof\.|ul\.\s*WILCZYCKA|KRAKOW|WARSZAWA|'
    r'^\s*$|^[\s.*\d]+$|^\s*[.\-]+\s*$)',
    re.IGNORECASE,
)

# Qualitative results to skip
_RE_QUALITATIVE = re.compile(
    r'(?:nie wykryto|przejrzysty|jasnozolty|dodatni|ujemny)',
    re.IGNORECASE,
)


def _parse_diagnostyka(pdf_path: Path) -> list[dict]:
    """Extract results from a Diagnostyka S.A. PDF using OCR."""
    doc = fitz.open(str(pdf_path))
    results = []
    collected_at = None
    current_badanie = ""

    try:
        for page_idx in range(doc.page_count):
            text = _ocr_page(doc[page_idx])
            lines = text.split("\n")

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Extract date from header (first occurrence wins)
                if collected_at is None:
                    m = _RE_DIAG_DATE.search(line)
                    if m:
                        try:
                            collected_at = datetime.strptime(
                                f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M"
                            )
                        except ValueError:
                            pass

                # Check for section header BEFORE skip filter
                # (section headers may contain skip-triggering words like "wysokie")
                m_section = _RE_DIAG_SECTION.match(line)
                if m_section:
                    current_badanie = m_section.group("badanie").strip()
                    # Section header line might also contain a result after the ICD code
                    # e.g. "CRP wysokiej czutosci (ICD-9: 181) 0,240 mg/l 0,000 - 5,000"
                    after_icd = re.sub(r'^.*\(ICD-9:\s*\w+\)\s*', '', line).strip()
                    if after_icd and re.match(r'[<>≤≥]?\s*\d', after_icd):
                        # Build a synthetic line: "MarkerName value unit range"
                        synth_line = f"{current_badanie} {after_icd}"
                        m_res = _RE_DIAG_RESULT.match(synth_line)
                        if m_res:
                            row = _build_diag_row(m_res, current_badanie, collected_at, pdf_path)
                            if row:
                                results.append(row)
                    continue

                # Skip non-result lines
                if _RE_DIAG_SKIP.search(line):
                    continue

                # Handle "Wynik badania: VALUE UNIT" lines (e.g. Vitamin D)
                m_wynik = re.match(
                    r'Wynik badania:\s*([<>≤≥]?\s*\d+[.,]?\d*)\s+(\S+)\s*(.*)',
                    line,
                )
                if m_wynik and current_badanie:
                    synth = f"{current_badanie} {m_wynik.group(1)} {m_wynik.group(2)} {m_wynik.group(3)}"
                    m_res = _RE_DIAG_RESULT.match(synth.strip())
                    if m_res:
                        row = _build_diag_row(m_res, current_badanie, collected_at, pdf_path)
                        if row:
                            results.append(row)
                    continue

                # Try to match result line
                m_res = _RE_DIAG_RESULT.match(line)
                if m_res:
                    row = _build_diag_row(m_res, current_badanie, collected_at, pdf_path)
                    if row:
                        results.append(row)

    finally:
        doc.close()

    return results


# Map OCR-mangled marker names to canonical Parametr strings used in ALIAS_MAP
_OCR_TO_PARAMETR = {
    # Diacritic-stripped OCR variants
    "Cholesterol catkowity": "Cholesterol całkowity",
    "Bilirubina catkowita": "Bilirubina całkowita",
    "Biatko catkowite": "Białko całkowite",
    "Wapnh catkowity": "Wapń całkowity",
    "Wapn catkowity": "Wapń całkowity",
    "Plytki krwi": "Płytki krwi",
    "Zelazo": "Żelazo",
    "Sod": "Sód",
    "Séd": "Sód",
    "Selen": "Selen",
    "Fosfataza zasadowa": "Fosfataza zasadowa",
    "Miedz": "Miedź",
    "Cynk": "Cynk",
    "Niedojrzate granulocyty IG": "Niedojrzałe granulocyty IG il.",
    "Witamina D metabolit 25(OH)": "Witamina D3 metabolit 25(OH)",
    "Witamina B12": "Witamina B12",
    "CRP wysokiej czutosci": "CRP wysokiej czułości",
    "CRP wysokiej czulosci": "CRP wysokiej czułości",
    "hs-CRP": "CRP wysokiej czułości",
    "Hemoglobina glikowana": "Hemoglobina glikowana",
    "Kwas moczowy": "Kwas moczowy",
    "PSA - wskaznik (fPSA/PSA)": "PSA - wskaźnik (fPSA/PSA)",
    "PSA wolny": "PSA wolny",
    "PSA wolny (fPSA)": "PSA wolny",
    "PSA catkowity (PSA)": "PSA",
    "PSA catkowity": "PSA",
    "Fosfor nieorganiczny": "Fosfor nieorganiczny",
    "OB": "OB",
    "Fibrynogen": "Fibrynogen",
    "Mocznik": "Mocznik",
    "Kwas moczowy": "Kwas moczowy",
    "Transferyna": "Transferyna",
    "NT pro-BNP": "NT pro-BNP",
    "Apo B": "Apo B",
    "Ferrytyna": "Ferrytyna",
    "Albumina": "Albumina",
    "Biatko catkowite": "Białko całkowite",
}

# OCR commonly mangles µ in unit strings
_OCR_UNIT_FIXES = {
    "tys/pl": "tys/µl",
    "tys/pl*": "tys/µl",
    "tys/ul": "tys/µl",
    "tys/ul*": "tys/µl",
    "min/pl": "mln/µl",
    "min/pl*": "mln/µl",
    "mln/pl": "mln/µl",
    "mln/pl*": "mln/µl",
    "ulU/ml": "µIU/ml",
    "ulU/ml*": "µIU/ml",
    "uIU/ml": "µIU/ml",
    "uIU/ml*": "µIU/ml",
    "umol/l": "µmol/l",
    "ug/l": "µg/l",
    "ug/dl": "µg/dl",
    "U/L": "U/l",
    "U/L*": "U/l",
    "U/*": "U/l",
}


def _fix_unit(raw_unit: str) -> str:
    """Fix OCR-mangled units."""
    cleaned = raw_unit.rstrip("*")
    result = _OCR_UNIT_FIXES.get(raw_unit) or _OCR_UNIT_FIXES.get(cleaned) or cleaned
    return result


def _fix_parametr(raw_name: str) -> str:
    """Map OCR-mangled marker names to canonical Parametr strings."""
    name = raw_name.strip().rstrip(".")
    # Remove trailing ICD-9 codes if present
    name = re.sub(r'\s*\(ICD-9:\s*\w+\)\s*$', '', name).strip()
    # Check the mapping
    if name in _OCR_TO_PARAMETR:
        return _OCR_TO_PARAMETR[name]
    return name


def _build_diag_row(match: re.Match, badanie: str, collected_at: datetime | None,
                    pdf_path: Path) -> dict | None:
    """Build a result dict from a Diagnostyka regex match."""
    name = match.group("name").strip()
    comp = match.group("comp") or ""
    value_str = match.group("value")
    unit_raw = match.group("unit")
    range_str = (match.group("range") or "").strip()

    # Skip qualitative results
    if _RE_QUALITATIVE.search(value_str):
        return None

    # Fix unit and validate against known units
    unit = _fix_unit(unit_raw)
    if unit not in _VALID_UNITS:
        return None

    # Clean up range — remove trailing L/H flag
    range_str = re.sub(r'\s*[LH]\s*$', '', range_str).strip()
    if range_str == "-":
        range_str = ""

    # Fix parametr name
    parametr = _fix_parametr(name)

    return {
        "parametr": parametr,
        "wynik_raw": f"{comp}{value_str}",
        "unit": unit,
        "range_raw": range_str,
        "badanie": badanie,
        "notes": "",
        "collected_at": collected_at,
        "source_file": pdf_path.name,
    }


# ---------------------------------------------------------------------------
# Read-Gene parser (OCR)
# ---------------------------------------------------------------------------

# Date: "Data pobrania | ... 2025-06-02 09:02:29"
_RE_RG_DATE = re.compile(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})')

# Result rows: "Selen* 130,55 Osoba niepalaca 100-110"
# Pattern: element name, value, then optional sub-group and optimal range
# OCR variants: Oléw, Olow, Ołów; kKadm (OCR artifact)
_RE_RG_RESULT = re.compile(
    r'^(?P<name>[kK]?(?:Selen|Arsen|Ol[eéoó]w|Kadm|Cynk|Mied[zź]?))'
    r'\*?\s*'                          # optional asterisk
    r'(?:\([A-Za-z]+\)\s*)?'           # optional symbol like (Se)
    r'(?P<value>\d+[.,]?\d*)',
)

# Read-Gene markers to skip (whole-blood vs serum incompatibility)
_RG_SKIP = {"Cynk", "Miedz", "Miedź", "Mied"}


def _parse_readgene(pdf_path: Path) -> list[dict]:
    """Extract results from a Read-Gene metals panel PDF using OCR."""
    doc = fitz.open(str(pdf_path))
    results = []

    try:
        text = _ocr_page(doc[0])
        lines = text.split("\n")

        # Find collection date
        collected_at = None
        for line in lines:
            m = _RE_RG_DATE.search(line)
            if m:
                try:
                    collected_at = datetime.strptime(
                        f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    pass
                break

        for line in lines:
            m = _RE_RG_RESULT.match(line.strip())
            if not m:
                continue

            name = m.group("name").strip()

            # Skip incomparable specimen types
            if name in _RG_SKIP:
                continue

            value_str = m.group("value")

            # Normalize OCR name variants (strip leading k artifact, etc.)
            name = re.sub(r'^[kK](?=[A-Z])', '', name)

            # Map to canonical Parametr name
            parametr_map = {
                "Selen": "Selen",
                "Arsen": "Arsen we krwi",
                "Olow": "Ołów we krwi",
                "Olów": "Ołów we krwi",
                "Oléw": "Ołów we krwi",
                "Olew": "Ołów we krwi",
                "Kadm": "Kadm we krwi",
            }
            parametr = parametr_map.get(name, name)
            unit = "µg/l"

            # Build optimal range string from OCR if possible
            # Read-Gene uses µg/l for all metals
            range_raw = ""  # We'll rely on catalog ranges

            results.append({
                "parametr": parametr,
                "wynik_raw": value_str,
                "unit": unit,
                "range_raw": range_raw,
                "badanie": "Onkoskrining - metale ciężkie",
                "notes": "Read-Gene, krew pełna",
                "collected_at": collected_at,
                "source_file": pdf_path.name,
            })

    finally:
        doc.close()

    return results


# ---------------------------------------------------------------------------
# Omega Test parser (pdfplumber)
# ---------------------------------------------------------------------------

# Date: "DATA/GODZ. POBRANIA: 24/03/2025"
_RE_OMEGA_DATE = re.compile(r'DATA/GODZ\.\s*POBRANIA:\s*(\d{2}/\d{2}/\d{4})')


def _parse_omega(pdf_path: Path) -> list[dict]:
    """Extract omega index results from Omega Test PDF.

    Uses the summary table on page 3 (index 2) with columns:
    Wskaźnik/Indeks | Status | Twój wynik | Wartość docelowa
    """
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        # Get collection date from first page
        collected_at = None
        first_text = pdf.pages[0].extract_text() or ""
        m = _RE_OMEGA_DATE.search(first_text)
        if m:
            try:
                collected_at = datetime.strptime(m.group(1), "%d/%m/%Y")
            except ValueError:
                LOG.warning("Failed to parse omega date %r in %s", m.group(1), pdf_path.name)

        # Map omega index names to canonical Parametr strings
        # Includes page-2 and page-4 name variants
        omega_map = {
            "NKT/JNKT": "NKT/JNKT",
            "Indeks tłuszczów trans": "Indeks tłuszczów TRANS",
            "Indeks omega 3": "Indeks Omega-3",
            "AA/EPA": "AA/EPA",
            "Indeks AA/EPA": "AA/EPA",
            "Omega 6/omega 3": "Omega 6/omega 3",
        }

        unit_map = {
            "NKT/JNKT": "ratio",
            "Indeks tłuszczów TRANS": "%",
            "Indeks Omega-3": "%",
            "AA/EPA": "ratio",
            "Omega 6/omega 3": "ratio",
        }

        # Scan all pages for tables with omega indices
        found_parametrs: set[str] = set()
        for page_idx in range(len(pdf.pages)):
            tables = pdf.pages[page_idx].extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                for row in table:
                    if not row or not row[0]:
                        continue

                    name = row[0].strip()
                    # Case-insensitive lookup
                    name_lower = name.lower()
                    omega_key = None
                    for k in omega_map:
                        if k.lower() == name_lower:
                            omega_key = k
                            break
                    if omega_key is None:
                        continue
                    name = omega_key

                    parametr = omega_map[name]
                    if parametr in found_parametrs:
                        continue  # skip duplicates across pages

                    # Find the numeric value in the row
                    value_str = None
                    for cell in row[1:]:
                        if cell and re.match(r'^\d+(?:[.,]\d+)?$', cell.strip()):
                            value_str = cell.strip()
                            break

                    if not value_str:
                        LOG.debug("No numeric value for omega index %r in %s", name, pdf_path.name)
                        continue

                    # Find range/target string — last non-empty non-numeric cell
                    range_raw = ""
                    for cell in reversed(row):
                        if cell and cell.strip() and not re.match(r'^\d+(?:[.,]\d+)?$', cell.strip()):
                            range_raw = cell.strip()
                            break

                    unit = unit_map.get(parametr, "")
                    found_parametrs.add(parametr)

                    results.append({
                        "parametr": parametr,
                        "wynik_raw": value_str,
                        "unit": unit,
                        "range_raw": range_raw,
                        "badanie": "Omega Test - profil kwasów tłuszczowych",
                        "notes": "Sannio Tech, błony komórkowe erytrocytów",
                        "collected_at": collected_at,
                        "source_file": pdf_path.name,
                    })

        if not results:
            LOG.warning("No omega indices found in %s", pdf_path.name)

    return results


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_key(pdf_path: Path, pdf_root: Path) -> str:
    """SHA-1 hash of the PDF's path relative to pdf_root (POSIX-style)."""
    rel = pdf_path.relative_to(pdf_root).as_posix()
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(pdf_path: Path, *, include_sha1: bool) -> dict:
    stat = pdf_path.stat()
    fp = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if include_sha1:
        fp["sha1"] = _sha1_file(pdf_path)
    return fp


def _serialize_cache_rows(rows: list[dict]) -> list[dict]:
    serialized = []
    for row in rows:
        out = dict(row)
        ca = out.get("collected_at")
        if isinstance(ca, datetime):
            out["collected_at"] = ca.isoformat()
        elif ca is None:
            out["collected_at"] = None
        serialized.append(out)
    return serialized


def _deserialize_cache_rows(rows: list[dict]) -> list[dict]:
    deserialized = []
    for row in rows:
        out = dict(row)
        ca = out.get("collected_at")
        if isinstance(ca, str):
            try:
                out["collected_at"] = datetime.fromisoformat(ca)
            except ValueError:
                out["collected_at"] = None
        deserialized.append(out)
    return deserialized


def _root_namespace(pdf_root: Path) -> str:
    """SHA-1 (prefix) of the resolved pdf_root path, used to scope cache files
    so that two different pdf_dirs never share cache entries.
    """
    resolved = str(pdf_root.resolve())
    return hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:16]


def _cache_path(pdf_path: Path, pdf_root: Path, cache_dir: Path) -> Path:
    return cache_dir / _root_namespace(pdf_root) / f"{_cache_key(pdf_path, pdf_root)}.json"


def _cache_load(pdf_path: Path, pdf_root: Path, cache_dir: Path) -> dict | None:
    """Return cached parser rows for pdf_path or None on miss.

    On hit via fast-path (size+mtime_ns), returns the cached entry directly.
    On hit via SHA-1 fallback, refreshes stored size/mtime_ns in the cache file.
    On any failure (missing, unreadable, version mismatch, content change),
    returns None.
    """
    cache_file = _cache_path(pdf_path, pdf_root, cache_dir)
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, encoding="utf-8") as f:
            entry = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        LOG.warning("Ignoring unreadable PDF cache for %s: %s", pdf_path.name, exc)
        return None

    if entry.get("parser_version") != PARSER_VERSION:
        return None

    cached_fp = entry.get("fingerprint") or {}
    try:
        current_fp = _fingerprint(pdf_path, include_sha1=False)
    except OSError as exc:
        LOG.warning("Failed to stat %s: %s", pdf_path.name, exc)
        return None

    if (cached_fp.get("size") == current_fp["size"]
            and cached_fp.get("mtime_ns") == current_fp["mtime_ns"]):
        entry["rows"] = _deserialize_cache_rows(entry.get("rows", []))
        return entry

    # Fallback: compare content SHA-1
    cached_sha1 = cached_fp.get("sha1")
    if not cached_sha1:
        return None
    try:
        current_sha1 = _sha1_file(pdf_path)
    except OSError as exc:
        LOG.warning("Failed to hash %s: %s", pdf_path.name, exc)
        return None
    if current_sha1 != cached_sha1:
        return None

    # Content unchanged: refresh metadata in cache file.
    entry["fingerprint"] = {
        "size": current_fp["size"],
        "mtime_ns": current_fp["mtime_ns"],
        "sha1": cached_sha1,
    }
    try:
        _atomic_write_json(cache_file, entry)
    except OSError as exc:
        LOG.warning("Failed to refresh cache metadata for %s: %s", pdf_path.name, exc)

    entry["rows"] = _deserialize_cache_rows(entry.get("rows", []))
    return entry


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _cache_store(pdf_path: Path, pdf_root: Path, cache_dir: Path,
                 fmt: str, rows: list[dict]) -> None:
    try:
        fp = _fingerprint(pdf_path, include_sha1=True)
    except OSError as exc:
        LOG.warning("Failed to fingerprint %s: %s", pdf_path.name, exc)
        return
    entry = {
        "source_path": pdf_path.relative_to(pdf_root).as_posix(),
        "fingerprint": fp,
        "format": fmt,
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
        "parser_version": PARSER_VERSION,
        "rows": _serialize_cache_rows(rows),
    }
    cache_file = _cache_path(pdf_path, pdf_root, cache_dir)
    try:
        _atomic_write_json(cache_file, entry)
    except OSError as exc:
        LOG.warning("Failed to write PDF cache for %s: %s", pdf_path.name, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_pdf_data(
    pdf_dir: Path,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Discover and parse all PDF files, returning canonical DataFrame.

    Output schema matches post-load_raw_data():
        Parametr, Wynik, Zakres referencyjny, source_file, source_order_id,
        source_badanie, source_notes, collected_at, collected_date, source_origin
    """
    all_rows: list[dict] = []

    pdf_files = sorted(pdf_dir.rglob("*.pdf"))
    if not pdf_files:
        LOG.info("No PDF files found in %s", pdf_dir)
        return pd.DataFrame()

    parsers = {
        "diagnostyka": _parse_diagnostyka,
        "readgene": _parse_readgene,
        "omega": _parse_omega,
    }
    skip_formats = {"genetic", "historia", "unknown"}

    cache_active = use_cache and cache_dir is not None
    if cache_active:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            LOG.warning("Cannot create PDF cache dir %s: %s — disabling cache", cache_dir, exc)
            cache_active = False
    if not cache_active and not use_cache:
        LOG.info("PDF cache disabled")

    hits = 0
    misses = 0
    skipped_format = 0

    for pdf_path in pdf_files:
        cached = None
        if cache_active:
            cached = _cache_load(pdf_path, pdf_dir, cache_dir)

        if cached is not None:
            fmt = cached.get("format", "unknown")
            raw_rows = cached.get("rows", [])
            hits += 1
            LOG.debug("PDF cache hit: %s", pdf_path.name)
            if fmt in skip_formats:
                skipped_format += 1
                continue
        else:
            LOG.info("PDF cache miss, parsing: %s", pdf_path.name)
            fmt = _detect_format(pdf_path)
            if fmt in skip_formats:
                LOG.info("Skipping %s (format: %s)", pdf_path.name, fmt)
                if cache_active:
                    _cache_store(pdf_path, pdf_dir, cache_dir, fmt, [])
                misses += 1
                skipped_format += 1
                continue

            parser = parsers.get(fmt)
            if not parser:
                LOG.warning("No parser for format %s (%s)", fmt, pdf_path.name)
                continue

            try:
                raw_rows = parser(pdf_path)
                LOG.info("Parsed %d rows from %s (%s)", len(raw_rows), pdf_path.name, fmt)
            except Exception as exc:
                LOG.warning("Failed to parse %s: %s", pdf_path.name, exc)
                continue

            if cache_active:
                _cache_store(pdf_path, pdf_dir, cache_dir, fmt, raw_rows)
            misses += 1

        # Canonicalize into post-load_raw_data() schema
        for row in raw_rows:
            # Date fallback: use directory name (e.g. 20241218)
            collected_at = row["collected_at"]
            if collected_at is None:
                dir_name = pdf_path.parent.name
                try:
                    collected_at = datetime.strptime(dir_name, "%Y%m%d")
                except ValueError:
                    LOG.warning("No date for %s, skipping", pdf_path.name)
                    continue

            # Build Wynik string: "value unit" matching CSV format
            wynik = f"{row['wynik_raw']} {row['unit']}" if row["unit"] else row["wynik_raw"]

            all_rows.append({
                "Parametr": row["parametr"],
                "Wynik": wynik,
                "Zakres referencyjny": row["range_raw"],
                "source_file": f"pdf/{pdf_path.parent.name}/{row['source_file']}",
                "source_order_id": "",
                "source_badanie": row["badanie"],
                "source_notes": row["notes"],
                "collected_at": collected_at,
                "collected_date": collected_at.date() if collected_at else None,
                "source_origin": "pdf",
            })

    if cache_active:
        LOG.info("PDF cache: %d hits, %d misses, %d skipped-format",
                 hits, misses, skipped_format)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    LOG.info("Total PDF records: %d", len(df))
    return df
