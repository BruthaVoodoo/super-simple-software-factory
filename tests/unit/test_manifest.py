"""Manifest read/write and hash canonicalization."""
from __future__ import annotations

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from sssf_cli import manifest


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = Path(tempfile.mkdtemp())

    def test_round_trip_is_canonical_and_stable(self):
        entries = {"a.txt": manifest.ManifestEntry(source_hash="s1", target_hash="t1"),
                   "b/c.txt": manifest.ManifestEntry(source_hash="s2", target_hash="t2")}
        manifest.write(self.target, entries)
        first = (self.target / ".sssf" / "manifest.json").read_text()
        manifest.write(self.target, entries)          # identical rewrite
        self.assertEqual(first, (self.target / ".sssf" / "manifest.json").read_text())
        loaded = manifest.load(self.target)
        self.assertEqual(loaded.entries["a.txt"].source_hash, "s1")

    def test_load_returns_none_when_not_stamped(self):
        self.assertIsNone(manifest.load(self.target))

    def test_entry_hashes_match_real_files(self):
        (self.target / "f.txt").write_bytes(b"stamped bytes")
        entry = manifest.entry_for(self.target / "f.txt",
                                   (self.target / "f.txt").read_bytes())
        self.assertEqual(entry.target_hash, sha256(b"stamped bytes").hexdigest())


if __name__ == "__main__":
    unittest.main()
