"""Verifier. Compares /workspace/answer.json with the answer key and writes the reward.

Standalone on purpose: it ships as tests/verify.py inside each Harbor task and
runs in the verifier sandbox, where only this file and gold.json exist.
"""
from __future__ import annotations

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


def main(answer_path: str = "/workspace/answer.json", gold_path: str = "/tests/gold.json",
         out_dir: str = "/logs/verifier") -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gold = json.loads(Path(gold_path).read_text())
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
