"""Checks that an environment is correct and as hard as its tier says.

Two kinds of output. Gates are pass or fail and block export: the answer can be
derived from the files, the verifier rejects known wrong answers, nothing leaks.
Measurements describe difficulty: how much evidence a task needs, how many stale
copies surround it, and whether cheap reading policies would get it right.
"""
from __future__ import annotations

import datetime as dt
import itertools
import math
import re
import tempfile
from collections import Counter
from pathlib import Path

from . import oracle, verify
from .render import Artifact, Rendered
from .tasks import Task
from .world import World

FORBIDDEN_IN_WORKSPACE = ["orbifex", "declined_proposal", "late_forward", "cancelled_leftover", "stale_row",
                          "misfiled", "canary", "gold.json", "manifest"]


def write_workspace(rendered: Rendered, root: Path) -> None:
    for rel, data in rendered.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


# ---------------------------------------------------------------- lexical ranking


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(_tokens(d)) for d in docs]
        self.len = [sum(tf.values()) for tf in self.tf]
        self.avg = sum(self.len) / max(1, len(docs))
        df: Counter = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = [t for t in set(_tokens(query)) if t in self.idf]
        out = []
        for tf, length in zip(self.tf, self.len):
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out


# ---------------------------------------------------------------- measurements


def _holds_current(a: Artifact, fact: str) -> bool:
    return any(c.fact == fact and c.current for c in a.claims)


def _mentions(a: Artifact, fact: str) -> bool:
    return any(c.fact == fact for c in a.claims)


def measure(world: World, rendered: Rendered, tasks: list[Task]) -> dict:
    arts = rendered.artifacts
    index = BM25([a.text for a in arts])
    per_task = {}
    for t in tasks:
        scores = index.scores(t.question)
        order = sorted(range(len(arts)), key=lambda i: -scores[i])
        rank = {i: r + 1 for r, i in enumerate(order)}
        first_hit = latest = True
        stale = 0
        worst_rank = 0
        mentions = 0
        sources_per_fact = []
        for fact in t.facts:
            cand = [i for i, a in enumerate(arts) if _mentions(a, fact)]
            good = [i for i in cand if _holds_current(arts[i], fact)]
            mentions += len(cand)
            stale += len(cand) - len(good)
            if not cand:                       # an absence, for example a payment that never came
                continue
            worst_rank = max(worst_rank, min(rank[i] for i in good))
            sources_per_fact.append({arts[i].source for i in good})
            top = min(cand, key=lambda i: rank[i])
            first_hit &= top in good
            newest = max(cand, key=lambda i: (arts[i].when, -rank[i]))
            latest &= newest in good
        all_sources = sorted(set().union(*sources_per_fact)) if sources_per_fact else []
        min_sources = len(all_sources)
        for k in range(1, len(all_sources) + 1):
            if any(all(set(combo) & s for s in sources_per_fact) for combo in itertools.combinations(all_sources, k)):
                min_sources = k
                break
        per_task[t.id] = {
            "family": t.family, "scope": t.scope, "needed_facts": len(t.facts), "min_sources": min_sources,
            "mentions": mentions, "stale_mentions": stale, "worst_rank": worst_rank,
            "probe_first_hit": first_hit, "probe_latest_wins": latest,
        }
    by_source = Counter(a.source for a in arts)
    tags = Counter(tag.split(":")[0] for a in arts for tag in a.tags)
    n = len(tasks)
    env = {
        "tier": world.tier.level, "orgs": len(world.orgs), "months": len(world.months), "cycles": len(world.cycles),
        "files": len(rendered.files), "units": len(arts), "units_by_source": dict(sorted(by_source.items())),
        "bytes": sum(len(b) for b in rendered.files.values()),
        "approx_tokens": sum(len(b) for b in rendered.files.values()) // 4,
        "planted": {k: v for k, v in sorted(tags.items()) if k != "noise"},
        "noise_units": tags.get("noise", 0),
        "tasks": n,
        "mean_stale_mentions": round(sum(m["stale_mentions"] for m in per_task.values()) / n, 2),
        "median_worst_rank": sorted(m["worst_rank"] for m in per_task.values())[n // 2],
        "probe_first_hit": round(sum(m["probe_first_hit"] for m in per_task.values()) / n, 3),
        "probe_latest_wins": round(sum(m["probe_latest_wins"] for m in per_task.values()) / n, 3),
    }
    return {"environment": env, "tasks": per_task}


# ---------------------------------------------------------------- gates

CLAIM_FORMATS = {
    "amount": lambda v: [f"{float(v):,.2f}", f"{float(v):.2f}"],
    "hours": lambda v: [f"{float(v):g}"],
    "invoice_no": lambda v: [v],
    "due": lambda v: [_day(v), v],
    "docs": lambda v: [],                       # carried by the message date, not the text
    "paid": lambda v: [] if v == "none" else [_day(v.split("|")[0]), v.split("|")[0]],
    "meeting": lambda v: [_day(v[:10]), v[:10]],
    "length": lambda v: [v.split("|")[1]],
}


def _day(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _short_day(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day}"


def run_gates(world: World, rendered: Rendered, tasks: list[Task]) -> dict:
    gates: dict[str, dict] = {}

    # 1. every answer can be derived from the agent-visible files alone
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        write_workspace(rendered, Path(tmp))
        ws = oracle.Workspace(tmp)
        for t in tasks:
            try:
                ok, fields = verify.grade(oracle.solve(ws, t.spec), t.gold)
            except Exception as exc:
                ok, fields = False, {"error": repr(exc)}
            if not ok:
                failures.append({"task": t.id, "fields": fields})
    gates["answer_derivable_from_files"] = {"passed": not failures, "checked": len(tasks), "failures": failures}

    # 2. the verifier accepts the key and rejects every known wrong answer
    failures, n = [], 0
    for t in tasks:
        if not verify.grade(t.gold, t.gold)[0]:
            failures.append({"task": t.id, "why": "gold rejected"})
        for wrong in t.negatives + [{}, {k: None for k in t.gold}]:
            n += 1
            if verify.grade(wrong, t.gold)[0]:
                failures.append({"task": t.id, "why": "accepted", "answer": wrong})
    gates["verifier_rejects_wrong_answers"] = {"passed": not failures, "checked": n, "failures": failures}

    # 3. nothing in the workspace names the generator, the tags or the key
    failures = []
    for rel, data in rendered.files.items():
        blob = (rel + "\n" + data.decode("utf-8", "replace")).lower()
        failures += [{"file": rel, "marker": m} for m in FORBIDDEN_IN_WORKSPACE if m in blob]
    gates["no_leak_in_workspace"] = {"passed": not failures, "checked": len(rendered.files), "failures": failures[:20]}

    # 4. every recorded claim is really stated by the unit that is said to state it
    failures, n = [], 0
    for a in rendered.artifacts:
        for c in a.claims:
            attr = c.fact.rsplit("/", 1)[1]
            forms = CLAIM_FORMATS[attr](c.value)
            if attr == "meeting" and a.source == "chat":
                forms = [_short_day(c.value[:10])]
            if attr == "paid" and a.source == "chat" and c.value != "none":
                forms = [f"{float(c.value.split('|')[1]):,.2f}"]
            if not forms:
                continue
            n += 1
            if not any(f in a.text for f in forms):
                failures.append({"unit": a.id, "path": a.path, "fact": c.fact, "value": c.value})
    gates["claims_match_text"] = {"passed": not failures, "checked": n, "failures": failures[:20]}

    # 5. nothing is dated after the environment's present
    end = dt.datetime(world.today.year, world.today.month, world.today.day, 23, 59, tzinfo=world.tz)
    late = [a.id for a in rendered.artifacts if a.when > end and "noise" not in a.tags]
    gates["nothing_dated_after_today"] = {"passed": not late, "checked": len(rendered.artifacts), "failures": late[:20]}

    gates["passed"] = all(g["passed"] for g in gates.values())  # type: ignore[assignment]
    return gates


def ladder_checks(reports: dict[int, dict], tasks_by_tier: dict[int, list[Task]]) -> dict:
    """Checks across tiers of one world: same answers, and difficulty that does not go down."""
    tiers = sorted(reports)
    base = {t.id: (t.question, t.gold) for t in tasks_by_tier[tiers[0]] if t.scope == "core"}
    changed = [f"tier {k}: {t.id}" for k in tiers[1:] for t in tasks_by_tier[k]
               if t.scope == "core" and base.get(t.id) != (t.question, t.gold)]
    worded = {t.id: t.question for t in tasks_by_tier[tiers[0]]}
    changed += [f"tier {k}: {t.id} wording" for k in tiers[1:] for t in tasks_by_tier[k] if worded.get(t.id) != t.question]
    out = {"answers_preserved": {"passed": not changed, "failures": changed}}
    env = [reports[k]["measure"]["environment"] for k in tiers]
    for key, rising in [("approx_tokens", True), ("units", True), ("mean_stale_mentions", True),
                        ("probe_first_hit", False), ("probe_latest_wins", False)]:
        vals = [e[key] for e in env]
        ok = all((b >= a) if rising else (b <= a) for a, b in zip(vals, vals[1:]))
        out[f"monotone_{key}"] = {"passed": ok, "values": vals}
    out["passed"] = all(v["passed"] for v in out.values())  # type: ignore[assignment]
    return out
