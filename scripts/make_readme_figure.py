#!/usr/bin/env python3
"""Draw the README figure from the pilot records. Standard library only.

    python3.11 scripts/make_readme_figure.py           # writes docs/accuracy-by-size.svg
    python3.11 scripts/make_readme_figure.py --check   # exit 1 if the committed file is out of date

Three small panels share one y axis: lookup questions, sweep questions, and the
two late-payer sweep questions on their own with the invoicing-export ablation beside them.

GitHub shows a README image on a white or a dark page and drops CSS classes and
variables, so every color is a literal attribute chosen to read on both, the
background is transparent, and no text is smaller than 13 units on a drawing
680 units wide.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from results_table import ROOT, TIERS, summarize  # noqa: E402

OUT = ROOT / "docs" / "accuracy-by-size.svg"

INK = "#6e7b88"        # text and rules: about 4.3 to 1 on white and on GitHub's dark page
BLUE = "#2a78d6"       # the workspace as generated
ORANGE = "#d95926"     # the same workspace with the invoicing export deleted
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"

W, H = 680, 374
LEFT, PANEL_W, GAP, INSET, STEP = 60, 194, 13, 22, 50
TOP, BOTTOM = 118, 268                                  # y of 100% and of 0%


def n(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def short_tokens(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1e6:.2f}M"
    return f"{v / 1e3:.0f}K" if v >= 100_000 else f"{v / 1e3:.1f}K"


def text(x, y, s, size=13, anchor="start", weight=None) -> str:
    extra = f' font-weight="{weight}"' if weight else ""
    return f'<text x="{n(x)}" y="{n(y)}" font-size="{size}" text-anchor="{anchor}"{extra}>{s}</text>'


def y_of(share: float) -> float:
    return BOTTOM - (BOTTOM - TOP) * share


def line(points, color) -> str:
    path = " ".join(f"{n(x)},{n(y)}" for x, y in points)
    return (f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/>')


def dot(x, y, color) -> str:
    return f'<circle cx="{n(x)}" cy="{n(y)}" r="4.5" fill="{color}"/>'


def ring(x, y, color) -> str:
    return f'<circle cx="{n(x)}" cy="{n(y)}" r="4" fill="none" stroke="{color}" stroke-width="2"/>'


def arrow_up(x, y_from, y_to) -> str:
    return (f'<path d="M{n(x)} {n(y_from)} V{n(y_to)} M{n(x - 3.5)} {n(y_to + 5)} L{n(x)} {n(y_to)} L{n(x + 3.5)} {n(y_to + 5)}" '
            f'fill="none" stroke="{INK}" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/>')


def render(s: dict) -> str:
    panels = [("Lookup questions", s["lookup"]), ("Sweep questions", s["sweep"]),
              ("Late-payer sweep questions", s["late"])]
    ablation = s["ablation"]
    tokens = [short_tokens(s["tiers"][t]["tokens"]) for t in TIERS]
    files = [f"{s['tiers'][t]['files']:,}" for t in TIERS]
    late_big = sum(s["late"][t][0] for t in ablation), sum(s["late"][t][1] for t in ablation)
    abl = sum(c for c, _ in ablation.values()), sum(k for _, k in ablation.values())
    title = "Share of runs answered correctly at each workspace size"
    counts = lambda key: ", ".join(str(s[key][t][0]) for t in TIERS)
    desc = (f"Three panels show runs answered correctly at workspace sizes of {', '.join(files)} files. "
            f"Lookup questions were answered correctly in {counts('lookup')} of {s['lookup'][1][1]} runs, and sweep "
            f"questions in {counts('sweep')} of {s['sweep'][1][1]}. The two late-payer sweep questions alone were answered "
            f"correctly in {counts('late')} of {s['late'][1][1]} runs, and {late_big[0]} of {late_big[1]} at the two "
            f"largest sizes became {abl[0]} of {abl[1]} when the invoicing export was deleted.")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           f'aria-labelledby="fig-title fig-desc">',
           f'<title id="fig-title">{title}</title>', f'<desc id="fig-desc">{desc}</desc>',
           f'<g font-family="{FONT}" fill="{INK}">',
           text(LEFT, 20, title, 15, weight=600)]

    # legend: one key per condition, mark beside plain text
    ky = 40
    out += [line([(LEFT, ky), (LEFT + 26, ky)], BLUE), dot(LEFT + 13, ky, BLUE),
            text(LEFT + 34, ky + 4.5, "Workspace as generated"),
            line([(LEFT + 216, ky), (LEFT + 225, ky)], ORANGE), line([(LEFT + 233, ky), (LEFT + 242, ky)], ORANGE),
            ring(LEFT + 229, ky, ORANGE), text(LEFT + 250, ky + 4.5, "Invoicing export deleted")]

    for label, share in ((1.0, "100%"), (0.5, "50%"), (0.0, "0%")):
        out.append(text(LEFT - 8, y_of(label) + 4.5, share, anchor="end"))
    out += [text(LEFT - 8, 290, "files", anchor="end"), text(LEFT - 8, 312, "correct", anchor="end")]

    for i, (name, counts) in enumerate(panels):
        x0 = LEFT + i * (PANEL_W + GAP)
        xs = [x0 + INSET + k * STEP for k in range(len(TIERS))]
        out += [text(x0, 78, name, 14, weight=600), text(x0, 97, f"{counts[1][1]} runs per size")]
        for share in (1.0, 0.5, 0.0):
            out.append(f'<line x1="{n(x0)}" x2="{n(x0 + PANEL_W)}" y1="{n(y_of(share))}" y2="{n(y_of(share))}" '
                       f'stroke="{INK}" stroke-opacity="0.3" stroke-width="1"/>')
        pts = [(x, y_of(counts[t][0] / counts[t][1])) for x, t in zip(xs, TIERS)]
        if counts is s["late"]:
            for x, t in zip(xs, TIERS):
                if t in ablation:
                    out.append(arrow_up(x, y_of(counts[t][0] / counts[t][1]) - 10, y_of(ablation[t][0] / ablation[t][1]) + 9))
        out.append(line(pts, BLUE))
        out += [dot(x, y, BLUE) for x, y in pts]
        for x, t, size in zip(xs, TIERS, files):
            out += [text(x, 290, size, anchor="middle"), text(x, 312, str(counts[t][0]), anchor="middle")]
        if counts is s["late"]:
            apts = [(x, y_of(ablation[t][0] / ablation[t][1])) for x, t in zip(xs, TIERS) if t in ablation]
            out += [line([(a[0] + 4, a[1]), (b[0] - 4, b[1])], ORANGE) for a, b in zip(apts, apts[1:])]
            out += [ring(x, y, ORANGE) for x, y in apts]
            out += [ring(x0 + 5, 327.5, ORANGE), text(x0 + 14, 332, "export deleted")]
            out += [text(x, 332, str(ablation[t][0]), anchor="middle") for x, t in zip(xs, TIERS) if t in ablation]

    out.append(text(LEFT, 360, f"The four sizes hold {', '.join(tokens[:-1])} and {tokens[-1]} tokens, "
                               f"counted as bytes divided by four."))
    out += ["</g>", "</svg>"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare with the committed file and write nothing")
    args = ap.parse_args(argv)
    svg = render(summarize())
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        print("up to date" if current == svg else f"{OUT.relative_to(ROOT)} is out of date")
        return 0 if current == svg else 1
    OUT.write_text(svg)
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
