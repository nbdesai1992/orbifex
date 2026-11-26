#!/usr/bin/env python3
"""Print the README's results from the committed pilot records.

    python3.11 scripts/results_table.py                # the results table, as Markdown
    python3.11 scripts/results_table.py --policies     # the two reading policies, both coverages
    python3.11 scripts/results_table.py --facts        # the headline numbers, one per line
    python3.11 scripts/results_table.py --build DIR    # with --facts: compare each miss with the wrong
                                                       # answers the generator predicted (DIR is the
                                                       # --out folder of `orbifex ladder --seed 7`)

Nothing here is typed in by hand. Runs are counted from the JSONL files under
experiments/results/ (one line per run), and workspace sizes and policy rates
are read from the generator's own report-t<tier>.json files beside them.

The result files call lookup questions "needle" and give them the scope
"core". Sweep questions have the scope "all".
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "experiments" / "results" / "cpa-solo-seed7-v2"     # eight-source version
V1 = ROOT / "experiments" / "results" / "cpa-solo-seed7"        # four-source version
TIERS = (1, 2, 3, 4)
LATE = "sweep_late"                                             # the late-payer sweep family


def runs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def tally(records: list[dict]) -> dict[int, tuple[int, int]]:
    """(correct, total) per tier."""
    out = {}
    for r in records:
        c, n = out.get(r["tier"], (0, 0))
        out[r["tier"]] = (c + bool(r["correct"]), n + 1)
    return dict(sorted(out.items()))


def total(by_tier: dict[int, tuple[int, int]], tiers=None) -> tuple[int, int]:
    picked = [v for k, v in by_tier.items() if tiers is None or k in tiers]
    return sum(c for c, _ in picked), sum(n for _, n in picked)


def mean_by_tier(records: list[dict], key: str) -> dict[int, float]:
    out = {}
    for t in sorted({r["tier"] for r in records}):
        vals = [r[key] for r in records if r["tier"] == t]
        out[t] = sum(vals) / len(vals)
    return out


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for k successes in n trials."""
    p, d = k / n, 1 + z * z / n
    mid, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return mid - half, mid + half


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the table [[a, b], [c, d]]."""
    row, col, n = a + b, a + c, a + b + c + d
    prob = lambda x: math.comb(col, x) * math.comb(n - col, row - x) / math.comb(n, row)
    seen = prob(a)
    return sum(p for x in range(max(0, row - (n - col)), min(row, col) + 1) if (p := prob(x)) <= seen * (1 + 1e-9))


def summarize(v2: Path = V2, v1: Path = V1) -> dict:
    lookup, sweep = runs(v2 / "pilot-needle-haiku.jsonl"), runs(v2 / "pilot-sweep-haiku.jsonl")
    ablation = runs(v2 / "ablation-no-invoicing-sweep-late.jsonl")
    late = [r for r in sweep if r["family"] == LATE]
    reports = {t: json.loads((v2 / f"report-t{t}.json").read_text()) for t in TIERS}
    env = {t: reports[t]["measure"]["environment"] for t in TIERS}

    policies = {}
    for name, key in (("first_hit", "probe_first_hit"), ("latest_wins", "probe_latest_wins")):
        for cover, scopes in (("lookup", ("core",)), ("all", ("core", "all"))):
            policies[name, cover] = {}
            for t in TIERS:
                vals = [m[key] for m in reports[t]["measure"]["tasks"].values() if m["scope"] in scopes]
                policies[name, cover][t] = (sum(vals), len(vals))
    # ladder.json is written by the generator from all tasks of a tier. Check that reading is right.
    ladder = json.loads((v2 / "ladder.json").read_text())
    for name in ("first_hit", "latest_wins"):
        ours = [round(c / n, 3) for c, n in policies[name, "all"].values()]
        if ours != ladder[f"monotone_probe_{name}"]["values"]:
            raise SystemExit(f"ladder.json {name} {ladder[f'monotone_probe_{name}']['values']} is not the all-task rate {ours}")

    needed = {}
    for cover, scope in (("lookup", "core"), ("sweep", "all")):
        needed[cover] = {}
        for t in TIERS:
            vals = [m["needed_facts"] for m in reports[t]["measure"]["tasks"].values() if m["scope"] == scope]
            needed[cover][t] = sum(vals) / len(vals)

    everything = lookup + sweep
    misses = [r for r in everything if not r["correct"]]
    v1_lookup, v1_sweep = runs(v1 / "pilot-needle-haiku.jsonl"), runs(v1 / "pilot-sweep-haiku.jsonl")
    v1_first = runs(v1 / "pilot-needle-haiku-first-build.jsonl")
    all_files = [lookup, sweep, ablation, v1_lookup, v1_sweep, v1_first]
    return {
        "tiers": {t: {"files": env[t]["files"], "tokens": env[t]["approx_tokens"], "clients": env[t]["orgs"],
                      "months": env[t]["months"], "sources": sorted(env[t]["units_by_source"]),
                      "tasks": env[t]["tasks"]} for t in TIERS},
        "task_counts": {t: {"lookup": sum(m["scope"] == "core" for m in reports[t]["measure"]["tasks"].values()),
                            "sweep": sum(m["scope"] == "all" for m in reports[t]["measure"]["tasks"].values())}
                        for t in TIERS},
        "lookup": tally(lookup), "sweep": tally(sweep), "late": tally(late), "ablation": tally(ablation),
        "lookup_cost": mean_by_tier(lookup, "cost_usd"), "sweep_cost": mean_by_tier(sweep, "cost_usd"),
        "lookup_turns": mean_by_tier(lookup, "turns"), "sweep_turns": mean_by_tier(sweep, "turns"),
        "policies": policies,
        "needed_facts": needed,
        "misses": misses,
        "cost": {"pilot": sum(r["cost_usd"] for r in everything), "ablation": sum(r["cost_usd"] for r in ablation),
                 "all": sum(r["cost_usd"] for f in all_files for r in f)},
        "runs": {"pilot": len(everything), "ablation": len(ablation), "all": sum(len(f) for f in all_files)},
        "model_ids": sorted({m for f in all_files for r in f for m in r.get("model_ids", [])}),
        "model_args": sorted({r["model"] for f in all_files for r in f}),
        "v1": {"lookup": tally(v1_lookup), "sweep": tally(v1_sweep), "first_build": tally(v1_first),
               "tasks": sum(json.loads((v1 / f"report-t{t}.json").read_text())["measure"]["environment"]["tasks"]
                            for t in TIERS)},
    }


def of(pair: tuple[int, int]) -> str:
    return f"{pair[0]} of {pair[1]}"


def pct(pair: tuple[int, int]) -> str:
    return f"{100 * pair[0] / pair[1]:.0f}%"


def markdown(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|---|" + "---:|" * (len(header) - 1)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def table(s: dict) -> str:
    n = lambda key: s[key][1][1]                       # runs per size, the same at every size
    cents = lambda key: [f"{100 * s[key][t]:.1f}" for t in TIERS]
    rows = [
        ["Files in the workspace"] + [f"{s['tiers'][t]['files']:,}" for t in TIERS],
        ["Tokens (bytes divided by four)"] + [f"{s['tiers'][t]['tokens']:,}" for t in TIERS],
        ["Sources"] + [str(len(s["tiers"][t]["sources"])) for t in TIERS],
        [f"Lookup questions correct, of {n('lookup')} runs"] + [str(s["lookup"][t][0]) for t in TIERS],
        [f"Sweep questions correct, of {n('sweep')} runs"] + [str(s["sweep"][t][0]) for t in TIERS],
        [f"Late-payer sweep question correct, of {n('late')} runs"] + [str(s["late"][t][0]) for t in TIERS],
        ["The same question with `invoicing/` deleted, of 6 runs"]
        + [str(s["ablation"][t][0]) if t in s["ablation"] else "not run" for t in TIERS],
        ["Mean cost of a lookup run, US cents"] + cents("lookup_cost"),
        ["Mean cost of a sweep run, US cents"] + cents("sweep_cost"),
    ]
    return markdown(["", "Size 1", "Size 2", "Size 3", "Size 4"], rows)


def policy_table(s: dict) -> str:
    p = s["policies"]
    label = {"first_hit": "First-hit", "latest_wins": "Latest-wins"}
    cover = {"lookup": "lookup questions only", "all": "all questions"}
    rows = []
    for c in ("lookup", "all"):
        for name in ("first_hit", "latest_wins"):
            cells = [f"{100 * p[name, c][t][0] / p[name, c][t][1]:.1f}%" for t in TIERS]
            rows.append([f"{label[name]}, {cover[c]} ({p[name, c][4][1]} per size)"] + cells)
    return markdown(["", "Size 1", "Size 2", "Size 3", "Size 4"], rows)


def facts(s: dict) -> dict[str, str]:
    """The numbers the README states in prose, each as the exact words it uses."""
    pilot = total(s["lookup"])[0] + total(s["sweep"])[0], total(s["lookup"])[1] + total(s["sweep"])[1]
    late_big, ablated = total(s["late"], (3, 4)), total(s["ablation"])
    late_misses = sum(r["family"] == LATE for r in s["misses"])
    first, last = s["tiers"][1], s["tiers"][4]
    v1 = total(s["v1"]["lookup"])[0] + total(s["v1"]["sweep"])[0], total(s["v1"]["lookup"])[1] + total(s["v1"]["sweep"])[1]
    lo, hi = wilson(total(s["lookup"])[1] - total(s["lookup"])[0], total(s["lookup"])[1])
    p = fisher_two_sided(late_big[0], late_big[1] - late_big[0], ablated[0], ablated[1] - ablated[0])
    return {
        "model": ", ".join(s["model_ids"]),
        "model argument passed to Claude Code": ", ".join(s["model_args"]),
        "runs correct, eight-source version": of(pilot),
        "lookup runs correct": of(total(s["lookup"])),
        "sweep runs correct": of(total(s["sweep"])),
        "misses": str(len(s["misses"])),
        "misses on the late-payer sweep question": f"{late_misses} of the {len(s['misses'])}",
        "late-payer sweep at the two largest sizes": of(late_big),
        "the same runs with invoicing/ deleted": of(ablated),
        "files, smallest to largest": f"{first['files']:,} to {last['files']:,}",
        "tokens, smallest to largest": f"{first['tokens']:,} to {last['tokens']:,}",
        "growth in tokens": f"{last['tokens'] / first['tokens']:.0f} times",
        "tasks": f"{s['tiers'][1]['tasks']} per size, {sum(s['tiers'][t]['tasks'] for t in TIERS)} in all",
        "lookup and sweep tasks per size": f"{s['task_counts'][1]['lookup']} and {s['task_counts'][1]['sweep']}",
        "mean facts a sweep answer needs, smallest to largest":
            f"{s['needed_facts']['sweep'][1]:.2f} at the smallest size and {s['needed_facts']['sweep'][4]:.2f} at the largest",
        "mean facts a lookup answer needs": f"{s['needed_facts']['lookup'][1]:.2f} facts at every size"
            if len({round(v, 6) for v in s["needed_facts"]["lookup"].values()}) == 1 else "varies by size",
        "recorded cost of the pilot": f"${s['cost']['pilot']:.2f} for {s['runs']['pilot']} runs",
        "recorded cost of the ablation": f"${s['cost']['ablation']:.2f} for {s['runs']['ablation']} runs",
        "every run on file": f"{s['runs']['all']} runs, ${s['cost']['all']:.2f}",
        "four-source version": f"{of(v1)} ({s['v1']['tasks']} tasks)",
        "four-source lookup runs in the first-build file": of(total(s["v1"]["first_build"])),
        "lookup error rate, 95% Wilson interval": f"{100 * lo:.1f}% to {100 * hi:.1f}%",
        "ablation against unablated runs, Fisher exact, two-sided": f"p = {p:.3f}",
    }


def planted(s: dict, build: Path) -> str:
    """How many misses equal a wrong answer the generator wrote down before any run."""
    sys.path.insert(0, str(ROOT / "src"))
    from orbifex import verify
    tasks = {t: {x["id"]: x for x in json.loads((build / f"t{t}" / "tasks.json").read_text())} for t in TIERS}
    late = [r for r in s["misses"] if r["family"] == LATE]
    same = sum(verify.grade(r["answer"], tasks[r["tier"]][r["task"]]["negatives"][0])[0] for r in late)
    return f"{same} of {len(late)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facts", action="store_true", help="print the headline numbers")
    ap.add_argument("--policies", action="store_true", help="print the reading-policy table")
    ap.add_argument("--build", type=Path, help="a regenerated --out folder, to check misses against predicted wrong answers")
    args = ap.parse_args(argv)
    s = summarize()
    if args.facts:
        found = facts(s)
        if args.build:
            found["late-payer misses equal to the answer computed from original due dates"] = planted(s, args.build)
        width = max(map(len, found))
        print("\n".join(f"{k:<{width}}  {v}" for k, v in found.items()))
    elif args.policies:
        print(policy_table(s), end="")
    else:
        print(table(s), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
