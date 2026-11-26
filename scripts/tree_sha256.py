#!/usr/bin/env python3
"""One sha256 for a folder tree, from file paths and file contents only.

    python3 scripts/tree_sha256.py DIR                      # print the checksum and the file count
    python3 scripts/tree_sha256.py DIR --match 'cpa-solo-t*'  # only top-level folders matching a pattern
    python3 scripts/tree_sha256.py DIR --compare OTHER      # list every file that differs, exit 1 if any

The checksum is the sha256 of a manifest with one line per file,

    <sha256 of the file's bytes>  <path relative to DIR>

sorted by path as bytes. Timestamps, owners and permissions are left out, so an
unpacked archive and a fresh build can be compared. The same number comes out of
standard tools, run inside DIR:

    find cpa-solo-t* -type f | LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
from pathlib import Path


def manifest(root: Path, match: str | None = None) -> dict[str, str]:
    """Relative path -> sha256 of contents, for every regular file under root."""
    out = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if match and not fnmatch.fnmatch(rel.split("/")[0], match):
            continue
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(out.items(), key=lambda kv: kv[0].encode()))


def digest(entries: dict[str, str]) -> str:
    h = hashlib.sha256()
    for rel, file_hash in entries.items():
        h.update(f"{file_hash}  {rel}\n".encode())
    return h.hexdigest()


def differences(a: dict[str, str], b: dict[str, str]) -> list[str]:
    lines = [f"only in the first tree: {rel}" for rel in a if rel not in b]
    lines += [f"only in the second tree: {rel}" for rel in b if rel not in a]
    lines += [f"contents differ: {rel}" for rel in a if rel in b and a[rel] != b[rel]]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path)
    ap.add_argument("--match", help="keep only files whose top-level folder matches this pattern")
    ap.add_argument("--compare", type=Path, help="a second tree to compare with the first")
    args = ap.parse_args(argv)
    first = manifest(args.root, args.match)
    if args.compare is None:
        print(f"{digest(first)}  {len(first)} files")
        return 0
    diff = differences(first, manifest(args.compare, args.match))
    print("\n".join(diff) if diff else f"identical: {len(first)} files, same paths and same contents")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
