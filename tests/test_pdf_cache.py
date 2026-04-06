"""Unit tests for PDF extraction cache in pdf_parser.load_pdf_data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdf_parser  # noqa: E402


def _fake_rows(source_name: str, collected_at: datetime | None = None) -> list[dict]:
    return [{
        "parametr": "Test Marker",
        "wynik_raw": "1,23",
        "unit": "mg/dl",
        "range_raw": "1.0 - 2.0",
        "badanie": "Testy",
        "notes": "",
        "collected_at": collected_at or datetime(2025, 1, 2, 10, 30),
        "source_file": source_name,
    }]


class PdfCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.pdf_dir = self.root / "pdfs" / "20250102"
        self.pdf_dir.mkdir(parents=True)
        self.cache_dir = self.root / ".pdf_cache"
        self.pdf_path = self.pdf_dir / "sample.pdf"
        self.pdf_path.write_bytes(b"fake-pdf-contents-v1")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, **kwargs):
        return pdf_parser.load_pdf_data(
            self.root / "pdfs",
            cache_dir=self.cache_dir,
            **kwargs,
        )

    def test_first_run_populates_cache(self):
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            df = self._run()
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(len(df), 1)
        cache_files = list(self.cache_dir.rglob("*.json"))
        self.assertEqual(len(cache_files), 1)
        entry = json.loads(cache_files[0].read_text(encoding="utf-8"))
        self.assertEqual(entry["format"], "diagnostyka")
        self.assertEqual(entry["parser_version"], pdf_parser.PARSER_VERSION)
        self.assertIn("sha1", entry["fingerprint"])

    def test_second_run_hits_fast_path(self):
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            self._run()

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            df = self._run()
        self.assertEqual(det.call_count, 0)
        self.assertEqual(parse.call_count, 0)
        self.assertEqual(len(df), 1)

    def test_touched_file_same_content_sha1_fallback(self):
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            self._run()

        # Bump mtime without changing content.
        future = time.time() + 10
        os.utime(self.pdf_path, (future, future))

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            df = self._run()
        self.assertEqual(det.call_count, 0)
        self.assertEqual(parse.call_count, 0)
        self.assertEqual(len(df), 1)

        # Cache should now record refreshed mtime_ns.
        entry = json.loads(next(self.cache_dir.rglob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(entry["fingerprint"]["mtime_ns"], self.pdf_path.stat().st_mtime_ns)

    def test_modified_content_invalidates_cache(self):
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            self._run()

        self.pdf_path.write_bytes(b"fake-pdf-contents-v2-different")

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            self._run()
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)

    def test_parser_version_bump_invalidates_cache(self):
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            self._run()

        with patch.object(pdf_parser, "PARSER_VERSION", pdf_parser.PARSER_VERSION + 1), \
             patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            self._run()
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)

    def test_skip_format_is_cached(self):
        with patch.object(pdf_parser, "_detect_format", return_value="unknown") as det:
            self._run()
        self.assertEqual(det.call_count, 1)
        cache_files = list(self.cache_dir.rglob("*.json"))
        self.assertEqual(len(cache_files), 1)
        entry = json.loads(cache_files[0].read_text(encoding="utf-8"))
        self.assertEqual(entry["format"], "unknown")
        self.assertEqual(entry["rows"], [])

        # Second run must not re-detect format.
        with patch.object(pdf_parser, "_detect_format", return_value="unknown") as det2:
            self._run()
        self.assertEqual(det2.call_count, 0)

    def test_corrupted_cache_is_ignored(self):
        # Create a corrupted cache file at the expected path.
        cache_file = pdf_parser._cache_path(
            self.pdf_path, self.root / "pdfs", self.cache_dir)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("{not json", encoding="utf-8")

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            df = self._run()
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(len(df), 1)
        # Cache file should be overwritten with a valid entry.
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(entry["format"], "diagnostyka")

    def test_use_cache_false_skips_reads_and_writes(self):
        # Pre-seed cache with a would-be hit to prove reads are skipped too.
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            self._run()
        self.assertTrue(list(self.cache_dir.rglob("*.json")))

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            pdf_parser.load_pdf_data(
                self.root / "pdfs",
                cache_dir=self.cache_dir,
                use_cache=False,
            )
        # reads skipped: parser was called despite pre-seeded cache entry
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)

    def test_different_pdf_roots_do_not_share_cache(self):
        other_root = self.root / "pdfs_other" / "20250102"
        other_root.mkdir(parents=True)
        other_pdf = other_root / "sample.pdf"
        # Same relative path, same size/mtime-ish, but DIFFERENT content.
        other_pdf.write_bytes(b"different-contents-same-relative-path")

        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka"), \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")):
            pdf_parser.load_pdf_data(
                self.root / "pdfs", cache_dir=self.cache_dir)

        # Loading the other root with the same cache_dir must not hit the
        # first root's entry (even though the relative path matches).
        with patch.object(pdf_parser, "_detect_format", return_value="diagnostyka") as det, \
             patch.object(pdf_parser, "_parse_diagnostyka",
                          return_value=_fake_rows("sample.pdf")) as parse:
            pdf_parser.load_pdf_data(
                self.root / "pdfs_other", cache_dir=self.cache_dir)
        self.assertEqual(det.call_count, 1)
        self.assertEqual(parse.call_count, 1)


if __name__ == "__main__":
    unittest.main()
