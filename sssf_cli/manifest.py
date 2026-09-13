"""Stamped-version manifest: source hash + target hash for every stamped file.

Lives at `.sssf/manifest.json` in the TARGET and is committed there. The
`source` hash records what the template WAS when stamped; the `target` hash
records what the file WAS. `sssf update` compares both against the current
world to classify untouched/user-modified files.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_DIR = ".sssf"
MANIFEST_NAME = "manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ManifestEntry:
    source_hash: str
    target_hash: str


@dataclass
class Manifest:
    version: str
    entries: dict[str, ManifestEntry]


def load(target: Path) -> Manifest | None:
    path = target / MANIFEST_DIR / MANIFEST_NAME
    if not path.is_file():
        return None
    raw = json.loads(path.read_text())
    return Manifest(version=raw.get("sssf_version", ""),
                    entries={rel: ManifestEntry(source_hash=item["source"],
                                                target_hash=item["target"])
                             for rel, item in raw.get("files", {}).items()})


def entry_for(path: Path, stamped_bytes: bytes) -> ManifestEntry:
    """Hash the stamped target file (target) and the given template bytes (source)."""
    return ManifestEntry(source_hash=sha256_bytes(stamped_bytes),
                         target_hash=sha256_bytes(path.read_bytes()))


def write(target: Path, entries: dict[str, ManifestEntry],
          version: str | None = None) -> None:
    from . import __version__
    payload = {
        "sssf_version": version or __version__,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {rel: {"source": e.source_hash, "target": e.target_hash}
                  for rel, e in sorted(entries.items())},
    }
    path = target / MANIFEST_DIR / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    # Canonical form: sorted keys, stable separators — identical entries always
    # serialize identically, so manifest rewrites diff cleanly.
    path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n")
