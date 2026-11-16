"""Tasks, built from their answers.

Every task is asked about the core cycles only, and every gold answer is
computed from final values in the world model. Both are independent of the
tier, so a task keeps its id, wording and answer from tier 1 to tier 4.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .world import Cycle, World, month_label


@dataclass
class Task:
    id: str
    family: str
    question: str
    answer_keys: dict[str, str]        # key -> plain description of the expected value
    gold: dict
    facts: list[str]                   # facts the answer is a function of
    spec: dict                         # what the reference solver is told (never the answer)
    negatives: list[dict] = field(default_factory=list)   # wrong answers the verifier must reject
    scope: str = "core"                # "core": same answer at every tier; "all": every counterparty in this tier


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _per_cycle(c: Cycle, v: dict) -> list[Task]:
    org, month, slug = c.org.name, month_label(c.ym), f"{c.org.key}-{c.ym}"
    noun, cyc = v["meeting_noun"], v["cycle"]
    short = noun.split()[-1]
    spec = {"org": org, "month": month}
    out: list[Task] = []

    final = c.final("meeting")
    negs = [{"date": _iso(v.value.date()), "start_time": v.value.strftime("%H:%M")} for v in c.meeting[:-1]]
    negs += [{"date": _iso(p.date()), "start_time": p.strftime("%H:%M")} for p, _ in c.declined]
    negs.append({"date": _iso(final.date() + dt.timedelta(days=1)), "start_time": final.strftime("%H:%M")})
    out.append(Task(
        f"meeting-{slug}", "meeting_time",
        f"When is the {month} {noun} with {org} scheduled, as it finally stood?",
        {"date": "the meeting date", "start_time": "the start time"},
        {"date": _iso(final.date()), "start_time": final.strftime("%H:%M")},
        [f"{c.fid}/meeting"], {"family": "meeting_time", **spec}, negs))

    modes = ["Zoom", "Phone", "Office"]
    gold = {"duration_minutes": c.meeting_minutes, "location": c.meeting_mode}
    negs = [{**gold, "duration_minutes": c.meeting_minutes + 15}] + [{**gold, "location": m} for m in modes if m != c.meeting_mode]
    out.append(Task(
        f"details-{slug}", "meeting_details",
        f"How long is the {month} {noun} with {org} scheduled to run, and how is it being held?",
        {"duration_minutes": "the scheduled length in minutes", "location": "one of Zoom, Phone or Office"},
        gold, [f"{c.fid}/length"], {"family": "meeting_details", **spec}, negs))

    amount = c.final("amount")
    negs = [{"invoice_number": c.invoice_no, "amount": v.value} for v in c.amount[:-1]]
    negs.append({"invoice_number": c.invoice_no, "amount": round(amount + 10, 2)})
    out.append(Task(
        f"invoice-{slug}", "invoice_total",
        f"What is the invoice number and the final total of the invoice for {org}'s {month} {cyc}?",
        {"invoice_number": "the invoice number, for example INV-1234", "amount": "the final total in dollars"},
        {"invoice_number": c.invoice_no, "amount": amount},
        [f"{c.fid}/invoice_no", f"{c.fid}/amount"], {"family": "invoice_total", **spec}, negs))

    if c.paid_at:
        due, paid = c.final("due"), c.paid_at.date()
        gold = {"due_on": _iso(due), "paid_on": _iso(paid), "days_late": max(0, (paid - due).days)}
        negs = [{"due_on": _iso(v.value), "paid_on": _iso(paid), "days_late": max(0, (paid - v.value).days)}
                for v in c.due[:-1]]
        negs.append({**gold, "days_late": gold["days_late"] + 1})
        out.append(Task(
            f"payment-{slug}", "payment_status",
            f"For {org}'s {month} {cyc} invoice: what was its final due date, when was payment received, "
            f"and how many calendar days late was the payment (0 if it arrived on or before the due date)?",
            {"due_on": "the final due date", "paid_on": "the date payment was received",
             "days_late": "whole calendar days past the final due date, 0 if not late"},
            gold, [f"{c.fid}/due", f"{c.fid}/paid"], {"family": "payment_status", **spec}, negs))

    docs, met = c.docs_at.date(), final.date()
    gold = {"docs_received_on": _iso(docs), "meeting_on": _iso(met), "before_meeting": docs < met}
    negs = [{**gold, "before_meeting": not gold["before_meeting"]}]
    negs += [{"docs_received_on": _iso(docs), "meeting_on": _iso(v.value.date()), "before_meeting": docs < v.value.date()}
             for v in c.meeting[:-1] if v.value.date() != met]
    out.append(Task(
        f"docs-{slug}", "docs_before_meeting",
        f"Did {org} send their {month} {v['materials']} before the day of the {month} {noun} (as finally scheduled)? "
        f"Give the date the {v['materials']} arrived and the date of the {short}.",
        {"docs_received_on": f"the date the {v['materials']} arrived", "meeting_on": f"the date of the {short}",
         "before_meeting": f"true if the {v['materials']} arrived on an earlier date than the {short}, else false"},
        gold, [f"{c.fid}/docs", f"{c.fid}/meeting"], {"family": "docs_before_meeting", **spec}, negs))
    return out


def build_tasks(w: World) -> list[Task]:
    cycles = sorted(w.core_cycles, key=lambda c: c.fid)
    tasks: list[Task] = []
    v = w.pack["vocab"]
    cyc, party = v["cycle"], v["counterparty"]
    for c in cycles:
        tasks += _per_cycle(c, v)

    orgs = [o.name for o in w.core_orgs]
    months = [month_label(m) for m in w.core_months]
    names = ", ".join(orgs[:-1]) + f" and {orgs[-1]}"
    span = " and ".join(months)
    scope = {"orgs": orgs, "months": months}

    total = round(sum(c.final("amount") for c in cycles), 2)
    stale_total = round(sum(c.amount[0].value for c in cycles), 2)
    negs = [{"total": round(total + 100, 2)}] + ([{"total": stale_total}] if stale_total != total else [])
    tasks.append(Task(
        "total-invoiced", "total_invoiced",
        f"What is the total amount invoiced to {names} for their {span} {cyc}s, using each invoice's final total?",
        {"total": "the sum in dollars"}, {"total": total},
        [f"{c.fid}/amount" for c in cycles], {"family": "total_invoiced", **scope}, negs))

    open_ = sorted(c.invoice_no for c in cycles if c.paid_at is None or c.paid_amount < c.final("amount") - 0.005)
    negs = [{"invoice_numbers": sorted(c.invoice_no for c in cycles if c.paid_at is None)},
            {"invoice_numbers": sorted(c.invoice_no for c in cycles)}, {"invoice_numbers": []}]
    tasks.append(Task(
        "unpaid-invoices", "unpaid_invoices",
        f"As of today, which invoices for the {span} {cyc}s of {names} have not been paid in full? "
        f"Count an invoice as not paid in full if no payment arrived or the payment was less than its final total.",
        {"invoice_numbers": "a list of invoice numbers, empty if none"}, {"invoice_numbers": open_},
        [f"{c.fid}/{a}" for c in cycles for a in ("amount", "paid")], {"family": "unpaid_invoices", **scope},
        [n for n in negs if n["invoice_numbers"] != open_]))

    late = sorted({c.org.name for c in cycles if c.paid_at and c.paid_at.date() > c.final("due")})
    stale_late = sorted({c.org.name for c in cycles if c.paid_at and c.paid_at.date() > c.due[0].value})
    negs = [{"clients": stale_late}, {"clients": sorted(orgs)}, {"clients": []}]
    tasks.append(Task(
        "late-payers", "late_payers",
        f"Which of {names} paid at least one of their {span} {cyc} invoices after its final due date?",
        {"clients": f"a list of {party} names exactly as written above, empty if none"}, {"clients": late},
        [f"{c.fid}/{a}" for c in cycles if c.paid_at for a in ("due", "paid")], {"family": "late_payers", **scope},
        [n for n in negs if n["clients"] != late]))

    for org in w.core_orgs:
        mine = [c for c in cycles if c.org.key == org.key]
        hours = sum(c.final("hours") for c in mine)
        stale = sum(c.hours[0].value for c in mine)
        negs = [{"hours": hours + 1}] + ([{"hours": stale}] if stale != hours else [])
        tasks.append(Task(
            f"hours-{org.key}", "hours_billed",
            f"How many hours in total were billed to {org.name} across the {span} {cyc}s, using each invoice's final version?",
            {"hours": "total hours as a number"}, {"hours": hours},
            [f"{c.fid}/hours" for c in mine],
            {"family": "hours_billed", "orgs": [org.name], "months": months}, negs))
    tasks += _sweeps(w)
    return tasks


def _sweeps(w: World) -> list[Task]:
    """Questions over every counterparty. The work, and the answer, grow with the tier."""
    v = w.pack["vocab"]
    cyc, party = v["cycle"], v["counterparty"]
    first = w.pack["persona"]["first"]
    out: list[Task] = []
    for ym in w.core_months:
        month = month_label(ym)
        cycles = sorted((c for c in w.cycles if c.ym == ym), key=lambda c: c.fid)
        spec = {"month": month}

        total = round(sum(c.final("amount") for c in cycles), 2)
        stale = round(sum(c.amount[0].value for c in cycles), 2)
        gold = {"invoices": len(cycles), "total": total}
        negs = [{**gold, "total": round(total - cycles[0].final("amount"), 2)}, {**gold, "invoices": len(cycles) + 1}]
        negs += [{**gold, "total": stale}] if stale != total else []
        out.append(Task(
            f"sweep-total-{ym}", "sweep_total",
            f"Across all of {first}'s {party}s, how many invoices were issued for the {month} {cyc} and what do "
            f"their final totals add up to?",
            {"invoices": "the number of invoices", "total": "the sum of their final totals in dollars"},
            gold, [f"{c.fid}/amount" for c in cycles], {"family": "sweep_total", **spec}, negs, "all"))

        open_ = sorted(c.invoice_no for c in cycles if c.paid_at is None or c.paid_amount < c.final("amount") - 0.005)
        negs = [{"invoice_numbers": sorted(c.invoice_no for c in cycles if c.paid_at is None)},
                {"invoice_numbers": open_[:-1]}, {"invoice_numbers": sorted(c.invoice_no for c in cycles)}]
        out.append(Task(
            f"sweep-unpaid-{ym}", "sweep_unpaid",
            f"Across all of {first}'s {party}s, which {month} {cyc} invoices have not been paid in full as of today? "
            f"Count an invoice as not paid in full if no payment arrived or the payment was less than its final total.",
            {"invoice_numbers": "a list of invoice numbers, empty if none"}, {"invoice_numbers": open_},
            [f"{c.fid}/{a}" for c in cycles for a in ("amount", "paid")], {"family": "sweep_unpaid", **spec},
            [n for n in negs if n["invoice_numbers"] != open_], "all"))

        late = sorted(c.org.name for c in cycles if c.paid_at and c.paid_at.date() > c.final("due"))
        early = sorted(c.org.name for c in cycles if c.paid_at and c.paid_at.date() > c.due[0].value)
        negs = [{"names": early}, {"names": late[:-1]}, {"names": sorted(c.org.name for c in cycles)}]
        out.append(Task(
            f"sweep-late-{ym}", "sweep_late",
            f"Across all of {first}'s {party}s, which ones paid their {month} {cyc} invoice after its final due date?",
            {"names": f"a list of {party} names as they appear in the meeting titles, empty if none"}, {"names": late},
            [f"{c.fid}/{a}" for c in cycles if c.paid_at for a in ("due", "paid")], {"family": "sweep_late", **spec},
            [n for n in negs if n["names"] != late], "all"))
    return out


def instruction(w: World, t: Task) -> str:
    p = w.pack["persona"]
    keys = "\n".join(f'- `{k}`: {desc}' for k, desc in t.answer_keys.items())
    return (f"You are assisting {p['name']}, {p['role'].lower()} at {p['org']}. Today is "
            f"{w.today.strftime('%A')}, {w.today.strftime('%B')} {w.today.day}, {w.today.year}. "
            f"Everything you have access to is under `/workspace`.\n\n"
            f"{t.question}\n\n"
            f"Write your answer to `/workspace/answer.json` as a JSON object with exactly these keys:\n\n{keys}\n\n"
            f"Dates are `YYYY-MM-DD`. Times are 24-hour `HH:MM` in {p['timezone']}. Amounts are plain numbers in dollars.\n")
