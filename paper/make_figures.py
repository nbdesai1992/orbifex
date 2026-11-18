"""Draw the paper's two data figures from the pilot results.

    python paper/make_figures.py            # needs matplotlib

Reads experiments/results/cpa-solo-seed7-v2/ and writes paper/figures/*.pdf.
One accent hue plus neutrals, thin marks, direct labels at line ends.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results" / "cpa-solo-seed7-v2"
OUT = Path(__file__).parent / "figures"
ACCENT, INK, GREY, GRID = "#b4532f", "#1b1b1a", "#8b8882", "#e7e4df"
TIERS = [1, 2, 3, 4]

plt.rcParams.update({"font.size": 8, "font.family": "sans-serif", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": GREY, "axes.linewidth": 0.6, "xtick.color": GREY, "ytick.color": GREY,
                     "xtick.labelcolor": INK, "ytick.labelcolor": INK, "pdf.fonttype": 42})


def rows(name):
    return [json.loads(line) for line in (RES / name).read_text().splitlines()]


def by_tier(rs):
    out = defaultdict(list)
    for r in rs:
        out[r["tier"]].append(r)
    return [out[t] for t in TIERS]


def probes(key):
    vals = []
    for t in TIERS:
        tasks = json.loads((RES / f"report-t{t}.json").read_text())["measure"]["tasks"].values()
        core = [m[key] for m in tasks if m["scope"] == "core"]
        vals.append(sum(core) / len(core))
    return vals


def main():
    needle, sweep = by_tier(rows("pilot-needle-haiku.jsonl")), by_tier(rows("pilot-sweep-haiku.jsonl"))
    acc = lambda groups: [100 * sum(bool(r["correct"]) for r in g) / len(g) for g in groups]
    cost = lambda groups: [100 * sum(r["cost_usd"] for r in g) / len(g) for g in groups]
    series = [("Needle", acc(needle), ACCENT, "-", 3.0), ("Sweep", acc(sweep), INK, "-", -7.5),
              ("Latest-wins", [100 * v for v in probes("probe_latest_wins")], GREY, (0, (4, 2)), 0.0),
              ("First-hit", [100 * v for v in probes("probe_first_hit")], GREY, "-", 0.0)]

    fig, (a, gap, b) = plt.subplots(1, 3, figsize=(5.5, 2.2), gridspec_kw={"width_ratios": [1.3, 0.62, 1.0], "wspace": 0.1})
    gap.axis("off")                                     # room for the direct labels at the line ends
    for name, vals, color, style, nudge in series:
        a.plot(TIERS, vals, color=color, linestyle=style, linewidth=1.3, marker="o", markersize=4.2,
               markeredgecolor="white", markeredgewidth=0.9, clip_on=False, zorder=3)
        a.annotate(f"{name} · {vals[-1]:.0f}%", (4, vals[-1]), xytext=(7, nudge), textcoords="offset points",
                   va="center", fontsize=7, color=INK)
    a.set_ylim(0, 104)
    a.set_xlim(0.8, 4.05)
    a.set_xticks(TIERS, [f"tier {t}" for t in TIERS])
    a.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    a.grid(axis="y", color=GRID, linewidth=0.6)
    a.set_axisbelow(True)
    a.set_title("(a) Tasks answered correctly", fontsize=8, loc="left", color=INK)
    a.tick_params(length=0)

    nd, sw = cost(needle), cost(sweep)
    w = 0.3
    b.bar([t - w / 2 - 0.02 for t in TIERS], nd, w, color=ACCENT, label="Needle", zorder=3)
    b.bar([t + w / 2 + 0.02 for t in TIERS], sw, w, color=INK, label="Sweep", zorder=3)
    for t in (1, 4):
        b.annotate(f"{nd[t - 1]:.1f}", (t - 0.02, nd[t - 1]), xytext=(-1, 2), textcoords="offset points", ha="right", fontsize=7)
        b.annotate(f"{sw[t - 1]:.1f}", (t + 0.02, sw[t - 1]), xytext=(1, 2), textcoords="offset points", ha="left", fontsize=7)
    b.set_xticks(TIERS, [str(t) for t in TIERS])
    b.set_xlabel("tier", fontsize=8, color=INK, labelpad=1)
    b.set_ylim(0, 8)
    b.set_xlim(0.25, 4.6)
    b.set_yticks([0, 2, 4, 6, 8])
    b.grid(axis="y", color=GRID, linewidth=0.6)
    b.set_axisbelow(True)
    b.set_title("(b) Mean cost per run (US cents)", fontsize=8, loc="left", color=INK)
    b.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(0.06, 0.9), handlelength=1, borderaxespad=0)
    b.tick_params(length=0)

    OUT.mkdir(exist_ok=True)
    fig.savefig(OUT / "results.pdf", bbox_inches="tight", pad_inches=0.02)

    # Workspace size and facts needed, by tier.
    env = [json.loads((RES / f"report-t{t}.json").read_text())["measure"]["environment"] for t in TIERS]
    need = {"core": [], "all": []}
    for t in TIERS:
        tasks = list(json.loads((RES / f"report-t{t}.json").read_text())["measure"]["tasks"].values())
        for scope in need:
            vals = [m["needed_facts"] for m in tasks if m["scope"] == scope]
            need[scope].append(sum(vals) / len(vals))
    fig, (a, b) = plt.subplots(1, 2, figsize=(5.5, 1.9), gridspec_kw={"wspace": 0.55})
    tokens = [e["approx_tokens"] for e in env]
    a.barh([f"tier {t}" for t in TIERS][::-1], tokens[::-1], height=0.42, color=ACCENT, zorder=3)
    a.set_xscale("log")
    a.set_xlim(8e3, 4e6)
    for y, v in zip(range(3, -1, -1), tokens):
        label = f"{v / 1e6:.1f}M" if v >= 1e6 else f"{v / 1e3:.0f}K"
        a.annotate(label, (v, y), xytext=(4, 0), textcoords="offset points", va="center", fontsize=7,
                   bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8}, zorder=4)
    for ref, name in ((2e5, "200K"), (1e6, "1M")):
        a.axvline(ref, color=GREY, linewidth=0.7, linestyle=(0, (3, 2)), zorder=1)
        a.annotate(name, (ref, 3.42), ha="center", fontsize=6.5, color=GREY, annotation_clip=False)
    a.set_title("(a) Workspace size, tokens (log scale)", fontsize=8, loc="left", color=INK, pad=11)
    a.tick_params(length=0)
    a.set_xticks([1e4, 1e5, 1e6], ["10K", "100K", "1M"])
    a.minorticks_off()

    b.plot(TIERS, need["all"], color=INK, linewidth=1.3, marker="o", markersize=4.2, markeredgecolor="white", markeredgewidth=0.9, zorder=3)
    b.plot(TIERS, need["core"], color=ACCENT, linewidth=1.3, marker="o", markersize=4.2, markeredgecolor="white", markeredgewidth=0.9, zorder=3)
    b.annotate(f"Sweep · {need['all'][-1]:.0f}", (4, need["all"][-1]), xytext=(6, 0), textcoords="offset points", va="center", fontsize=7)
    b.annotate(f"Needle · {need['core'][-1]:.1f}", (4, need["core"][-1]), xytext=(6, 4), textcoords="offset points", va="center", fontsize=7)
    b.set_xticks(TIERS, [f"tier {t}" for t in TIERS])
    b.set_xlim(0.8, 4.05)
    b.set_ylim(0, 36)
    b.set_yticks([0, 10, 20, 30])
    b.grid(axis="y", color=GRID, linewidth=0.6)
    b.set_axisbelow(True)
    b.set_title("(b) Facts one task needs (mean)", fontsize=8, loc="left", color=INK, pad=11)
    b.tick_params(length=0)
    fig.savefig(OUT / "tiers.pdf", bbox_inches="tight", pad_inches=0.02)
    print("wrote", *(p.name for p in sorted(OUT.glob("*.pdf"))))


if __name__ == "__main__":
    main()
