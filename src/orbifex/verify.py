"""Verifier. Compares /workspace/answer.json with the answer key and writes the reward.

Standalone on purpose: it ships as tests/verify.py inside each Harbor task and
runs in the verifier sandbox, where only this file and the key exist.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _num(x):
    if isinstance(x, bool):
        raise ValueError("boolean is not a number")
    if isinstance(x, (int, float)):
        return float(x)
    return float(str(x).replace("$", "").replace(",", "").strip())


def same(answer, gold) -> bool:
    try:
        if isinstance(gold, bool):
            return answer is gold or str(answer).strip().lower() == str(gold).lower()
        if isinstance(gold, (int, float)):
            return abs(_num(answer) - float(gold)) < 0.005
        if isinstance(gold, list):
            if not isinstance(answer, list):
                return False
            return sorted(str(a).strip().casefold() for a in answer) == sorted(str(g).strip().casefold() for g in gold)
        text = str(answer).strip().casefold()
        if len(str(gold)) == 5 and str(gold)[2] == ":" and len(text) == 8:   # HH:MM given as HH:MM:SS
            text = text[:5]
        return text == str(gold).strip().casefold()
    except (TypeError, ValueError):
        return False


def grade(answer, gold: dict) -> tuple[bool, dict]:
    if not isinstance(answer, dict):
        return False, {k: False for k in gold}
    fields = {k: (k in answer and same(answer[k], g)) for k, g in gold.items()}
    return all(fields.values()), fields


def load_key(path: str) -> dict:
    """Read the answer key, refusing one that is not this task's.

    The key is named gold.<first 12 hex of its sha256>.json. A wrong or stale
    key (for example one a Docker build served from another task's context)
    stops the verifier with an error, so no reward is written and the harness
    reports a failed verification, never a score.
    """
    p = Path(path)
    if p.is_dir():
        found = sorted(p.glob("gold.*.json"))
        if len(found) != 1:
            raise SystemExit(f"verify: expected exactly one gold.<hash>.json in {p}, found {len(found)}")
        p = found[0]
    data = p.read_bytes()
    parts = p.name.split(".")
    if len(parts) == 3 and parts[1] != hashlib.sha256(data).hexdigest()[:12]:
        raise SystemExit(f"verify: {p.name} does not match its content hash, so this is not this task's key")
    return json.loads(data)


def main(answer_path: str = "/workspace/answer.json", gold_path: str = "/tests",
         out_dir: str = "/logs/verifier") -> int:
    gold = load_key(gold_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ok, fields, error = False, {}, None
    try:
        ok, fields = grade(json.loads(Path(answer_path).read_text()), gold)
    except Exception as exc:                      # a missing or malformed answer scores zero
        error = repr(exc)
    (out / "details.json").write_text(json.dumps({"fields": fields, "error": error}, indent=1))
    (out / "reward.txt").write_text("1" if ok else "0")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
