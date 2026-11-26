"""Tier calibration pilot: run a headless Claude Code agent on the same tasks at each tier.

The agent gets a private copy of the tier's workspace as its working directory
and four tools: Read, Grep, Glob and Write. No shell, no network tools, no MCP
servers. Its answer.json is graded by the same verify.py that ships in the
Harbor task. Results append to a JSONL file, one line per run, and finished
runs are skipped on restart.

    python experiments/claude_pilot.py BUILD_DIR --tiers 1 2 3 4

BUILD_DIR is the --out folder of `orbifex ladder ... --workspace`.

The model defaults to claude-haiku-5-5, the model behind every record under
experiments/results/. Those runs passed the alias `haiku` (the "model" field
of each record), and Claude Code resolved it to claude-haiku-5-5 (the
"model_ids" field, read from the run's own usage report). An alias can move to
a newer model, so the default here is the full ID. Every run calls the model
through the local Claude Code login and is billed to it.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from orbifex import verify  # noqa: E402

MODEL = "claude-haiku-5-5"
TOOLS = "Read,Grep,Glob,Write"
BLOCKED = "Bash,Edit,NotebookEdit,WebFetch,WebSearch,Task,Agent"


def prompt_for(question_md: str) -> str:
    text = question_md.replace("Everything you have access to is under `/workspace`.",
                               "Everything you have access to is in the current working directory.")
    text = text.replace("`/workspace/answer.json`", "`answer.json` in the current working directory")
    return text + "\nUse only the files in this directory. Stop once answer.json is written.\n"


def run_one(build: Path, tier: int, task: dict, model: str, trial: int, timeout: int) -> dict:
    src = build / f"t{tier}" / "workspace"
    rec = {"tier": tier, "task": task["id"], "family": task["family"], "model": model, "trial": trial}
    with tempfile.TemporaryDirectory(prefix="pilot-") as tmp:
        work = Path(tmp) / "workspace"
        shutil.copytree(src, work)
        cmd = ["claude", "-p", prompt_for(task["instruction"]), "--model", model, "--output-format", "json",
               "--max-turns", "80", "--allowedTools", TOOLS, "--disallowedTools", BLOCKED,
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        started = time.time()
        try:
            proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
            out = json.loads(proc.stdout)
            usage = out.get("usage", {})
            rec.update(turns=out.get("num_turns"), cost_usd=out.get("total_cost_usd"), agent_error=out.get("is_error"),
                       input_tokens=usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0),
                       output_tokens=usage.get("output_tokens"), model_ids=sorted((out.get("modelUsage") or {}).keys()))
        except subprocess.TimeoutExpired:
            rec["error"] = "timeout"
        except Exception as exc:
            rec["error"] = repr(exc)[:200]
        rec["seconds"] = round(time.time() - started, 1)
        answer_path = work / "answer.json"
        try:
            answer = json.loads(answer_path.read_text())
            ok, fields = verify.grade(answer, task["gold"])
            rec.update(correct=ok, fields=fields, answer=answer)
        except Exception as exc:
            rec.update(correct=False, fields={}, answer=None, answer_error=repr(exc)[:120])
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("build", type=Path)
    ap.add_argument("--model", default=MODEL,
                    help=f"model ID or alias passed to `claude --model` (default: {MODEL}, the model in the committed records)")
    ap.add_argument("--tiers", type=int, nargs="+", default=[1, 2, 3, 4])
    ap.add_argument("--tasks", nargs="*", help="task ids to run (default: all)")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or args.build / f"pilot-{args.model}.jsonl"
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if "error" not in r:
                done.add((r["tier"], r["task"], r["trial"]))
    jobs = []
    for tier in args.tiers:
        tasks = json.loads((args.build / f"t{tier}" / "tasks.json").read_text())
        for t in tasks:
            if args.tasks and t["id"] not in args.tasks:
                continue
            for trial in range(args.trials):
                if (tier, t["id"], trial) not in done:
                    jobs.append((tier, t, trial))
    print(f"{len(jobs)} runs to do, {len(done)} already recorded in {out}")
    with cf.ThreadPoolExecutor(args.workers) as pool, out.open("a") as fh:
        futures = [pool.submit(run_one, args.build, tier, t, args.model, trial, args.timeout) for tier, t, trial in jobs]
        for f in cf.as_completed(futures):
            r = f.result()
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"t{r['tier']} {r['task']:38s} {'ok ' if r['correct'] else 'MISS'} turns={r.get('turns')} "
                  f"cost={r.get('cost_usd')} {r.get('seconds')}s {r.get('error', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
