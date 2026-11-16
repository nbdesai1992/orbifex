"""Command line: build one tier, or a whole ladder, and export Harbor tasks."""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import checks, harbor
from .render import render_world
from .tasks import build_tasks, instruction
from .world import build_world, load_pack


def build_tier(pack: dict, tier: int, seed: int):
    world = build_world(pack, tier, seed)
    rendered = render_world(world)
    tasks = build_tasks(world)
    report = {"gates": checks.run_gates(world, rendered, tasks), "measure": checks.measure(world, rendered, tasks)}
    return world, rendered, tasks, report


def cmd_ladder(args) -> int:
    pack = load_pack(args.persona)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    reports, tasks_by_tier, built = {}, {}, {}
    for tier in args.tiers:
        world, rendered, tasks, report = build_tier(pack, tier, args.seed)
        reports[tier], tasks_by_tier[tier], built[tier] = report, tasks, (world, rendered)
        if args.workspace:
            checks.write_workspace(rendered, out / f"t{tier}" / "workspace")
        (out / f"t{tier}").mkdir(exist_ok=True)
        (out / f"t{tier}" / "report.json").write_text(json.dumps(report, indent=1, default=str))
        (out / f"t{tier}" / "manifest.json").write_text(json.dumps(
            [{k: v for k, v in dataclasses.asdict(a).items() if k != "text"} for a in rendered.artifacts],
            indent=1, default=str))
        (out / f"t{tier}" / "tasks.json").write_text(json.dumps(
            [{**dataclasses.asdict(t), "instruction": instruction(world, t)} for t in tasks], indent=1))
    ladder = checks.ladder_checks(reports, tasks_by_tier) if len(args.tiers) > 1 else {"passed": True}
    (out / "ladder.json").write_text(json.dumps(ladder, indent=1))

    cols = ["tier", "orgs", "months", "files", "approx_tokens", "mean_stale_mentions", "median_worst_rank",
            "probe_first_hit", "probe_latest_wins"]
    print("  ".join(f"{c:>12.12}" for c in cols + ["gates"]))
    for tier in args.tiers:
        env = reports[tier]["measure"]["environment"]
        row = [env[c] for c in cols] + ["pass" if reports[tier]["gates"]["passed"] else "FAIL"]
        print("  ".join(f"{str(v):>12.12}" for v in row))
    print("ladder:", "pass" if ladder["passed"] else "FAIL",
          {k: v.get("values") for k, v in ladder.items() if isinstance(v, dict) and not v["passed"]})

    ok = ladder["passed"] and all(r["gates"]["passed"] for r in reports.values())
    if not ok:
        for tier, r in reports.items():
            for name, g in r["gates"].items():
                if isinstance(g, dict) and not g["passed"]:
                    print(f"tier {tier} gate {name} failed:", json.dumps(g["failures"][:3], default=str)[:600])
        return 1
    if args.harbor:
        for tier in args.tiers:
            world, rendered = built[tier]
            dest = harbor.export(world, rendered, tasks_by_tier[tier], reports[tier]["measure"],
                                 Path(args.harbor) / f"{pack['id']}-t{tier}")
            print(f"exported {len(tasks_by_tier[tier])} Harbor tasks to {dest}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="orbifex", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lad = sub.add_parser("ladder", help="build tiers of one world, check them, optionally export Harbor tasks")
    lad.add_argument("persona", help="path to a persona pack (TOML)")
    lad.add_argument("--seed", type=int, default=7)
    lad.add_argument("--tiers", type=int, nargs="+", default=[1, 2, 3, 4])
    lad.add_argument("--out", default="build", help="reports, manifests and (with --workspace) the rendered files")
    lad.add_argument("--workspace", action="store_true", help="also write each tier's workspace to disk")
    lad.add_argument("--harbor", help="directory to export Harbor datasets into, one per tier")
    lad.set_defaults(fn=cmd_ladder)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
