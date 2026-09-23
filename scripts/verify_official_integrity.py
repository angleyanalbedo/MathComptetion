#!/usr/bin/env python3
"""Create once or verify the project's immutable contest-input/evaluator manifest."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "protection" / "official-files.sha256"


def protected_files() -> dict[str, Path]:
    files: dict[str, Path] = {"README.md": ROOT / "README.md"}
    for folder in ("official/code", "official/docs"):
        base = ROOT / folder
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    files[path.relative_to(ROOT).as_posix()] = path
    config = ROOT / "official" / "data" / "config.txt"
    if config.exists():
        files["official/data/config.txt"] = config
    for path in (ROOT / "official" / "data").glob("case_*.json"):
        files[path.relative_to(ROOT).as_posix()] = path
    return files


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"baseline manifest is missing: {MANIFEST}")
    entries: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        checksum, relpath = line.split("  ", 1)
        entries[relpath] = checksum
    return entries


def initialize() -> int:
    if MANIFEST.exists():
        print(f"Refusing to overwrite existing baseline: {MANIFEST}", file=sys.stderr)
        return 2
    files = protected_files()
    if not files:
        print("No official files found; baseline not created", file=sys.stderr)
        return 2
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{digest(files[name])}  {name}" for name in sorted(files)]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created baseline for {len(files)} official files at {MANIFEST.relative_to(ROOT)}")
    return 0


def verify() -> int:
    try:
        expected = read_manifest()
    except (OSError, ValueError) as exc:
        print(f"Official integrity check failed: {exc}", file=sys.stderr)
        return 2
    actual_files = protected_files()
    actual_names = set(actual_files)
    expected_names = set(expected)
    changed = [name for name in sorted(actual_names & expected_names)
               if digest(actual_files[name]) != expected[name]]
    missing = sorted(expected_names - actual_names)
    added = sorted(actual_names - expected_names)
    if not (changed or missing or added):
        print(f"Official integrity OK ({len(expected)} files)")
        return 0
    print("Official files differ from the committed baseline:", file=sys.stderr)
    for label, names in (("modified", changed), ("missing", missing), ("untracked/additional", added)):
        for name in names:
            print(f"  {label}: {name}", file=sys.stderr)
    print("Stop evaluator runs. Do not refresh the manifest as part of ordinary optimization.", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize", action="store_true", help="create the initial manifest once")
    mode.add_argument("--verify", action="store_true", help="compare official files against the manifest")
    args = parser.parse_args()
    return initialize() if args.initialize else verify()


if __name__ == "__main__":
    raise SystemExit(main())
