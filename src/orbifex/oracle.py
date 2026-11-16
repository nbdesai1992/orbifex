"""Reference solver. It answers a task by reading the workspace files only.

This file has no access to the world model or the answer key. It ships inside
each Harbor task as solution/oracle.py, and the generator runs the same code
against the rendered files to confirm that every answer can be derived from
what the agent is given.

Usage: python3 oracle.py <workspace-dir> <spec.json> [<out.json>]
"""
from __future__ import annotations

import datetime as dt
import email
import json
import re
import sys
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

MONEY = r"\$([\d,]+\.\d\d)"
DAY = r"([A-Z][a-z]+ \d{1,2}, \d{4})"


def to_money(s: str) -> float:
    return float(s.replace(",", ""))


def to_day(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%B %d, %Y").date()


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.mail = []
        for path in sorted((self.root / "mail").rglob("*.eml")):
            msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
            body = msg.get_body(preferencelist=("plain",))
            self.mail.append({
                "from": parseaddr(msg["From"])[1].lower(), "to": parseaddr(msg["To"])[1].lower(),
                "subject": str(msg["Subject"]), "date": parsedate_to_datetime(msg["Date"]),
                "body": body.get_content() if body else "",
            })
        self.mail.sort(key=lambda m: m["date"])
        self.events = self._events(self.root / "calendar" / "calendar.ics")
        organizers = [e["organizer"] for e in self.events if e.get("organizer")]
        self.me = max(set(organizers), key=organizers.count)

    @staticmethod
    def _events(path: Path) -> list[dict]:
        events, cur = [], None
        for line in path.read_text().splitlines():
            if line == "BEGIN:VEVENT":
                cur = {"status": "CONFIRMED", "sequence": 0}
            elif line == "END:VEVENT":
                events.append(cur)
                cur = None
            elif cur is not None and ":" in line:
                key, _, value = line.partition(":")
                name = key.split(";")[0]
                if name == "SUMMARY":
                    cur["summary"] = value
                elif name == "DTSTART" and "VALUE=DATE" not in key:
                    cur["start"] = dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
                elif name == "DTEND" and "VALUE=DATE" not in key:
                    cur["end"] = dt.datetime.strptime(value, "%Y%m%dT%H%M%S")
                elif name == "LOCATION":
                    cur["location"] = value.replace("\\,", ",")
                elif name == "SEQUENCE":
                    cur["sequence"] = int(value)
                elif name == "STATUS":
                    cur["status"] = value
                elif name == "ORGANIZER":
                    cur["organizer"] = value.replace("mailto:", "").lower()
                elif name == "ATTENDEE":
                    cur["attendee"] = value.replace("mailto:", "").lower()
        return events

    # ---- facts, each read from the place a careful person would trust

    def meeting(self, org: str, month: str) -> dict:
        """The live calendar entry is the authority for when a meeting is."""
        hits = [e for e in self.events if e.get("summary", "").startswith(month + " ")
                and e["summary"].endswith(" - " + org) and e["status"] != "CANCELLED" and "start" in e]
        return max(hits, key=lambda e: e["sequence"])

    def orgs(self, month: str) -> list[str]:
        """Everyone who has a review on the calendar for this month."""
        return sorted({e["summary"].split(" - ", 1)[1] for e in self.events
                       if e.get("summary", "").startswith(month + " ") and " - " in e["summary"] and "attendee" in e})

    def domain(self, org: str, month: str) -> str:
        return self.meeting(org, month)["attendee"].split("@")[1]

    def invoice(self, org: str, month: str) -> dict:
        """The latest invoice the persona sent wins; forwards of old copies do not count."""
        dom = self.domain(org, month)
        best = None
        for m in self.mail:
            if m["from"] != self.me or not m["to"].endswith("@" + dom):
                continue
            block = re.search(r"Invoice: (INV-\d+)\nFor: ([^\n]*)\n[^\n]*: ([\d.]+) at [^\n]*\nTotal due: "
                              + MONEY + r"\nDue date: " + DAY, m["body"])
            if block and block.group(2).endswith(month):
                best = {"number": block.group(1), "hours": float(block.group(3)),
                        "amount": to_money(block.group(4)), "due": to_day(block.group(5)), "sent": m["date"]}
        if best is None:
            raise LookupError(f"no invoice for {org} {month}")
        for m in self.mail:                       # a later extension moves the due date
            if m["from"] == self.me and m["date"] > best["sent"]:
                ext = re.search(r"New due date for " + re.escape(best["number"]) + ": " + DAY, m["body"])
                if ext:
                    best["due"] = to_day(ext.group(1))
        return best

    def payment(self, number: str) -> dict | None:
        for m in self.mail:
            if re.search(r"Memo: " + re.escape(number) + r"\b", m["body"]):
                amount = re.search(MONEY, m["body"])
                day = re.search(r"posted on " + DAY, m["body"])
                if amount and day:
                    return {"amount": to_money(amount.group(1)), "on": to_day(day.group(1))}
        return None

    def documents(self, org: str, month: str) -> dt.date:
        dom = self.domain(org, month)
        for m in self.mail:
            if m["from"].endswith("@" + dom) and f"Attached are the {month} " in m["body"]:
                return m["date"].date()
        raise LookupError(f"no documents for {org} {month}")


def solve(ws: Workspace, spec: dict) -> dict:
    fam = spec["family"]
    if fam == "meeting_time":
        start = ws.meeting(spec["org"], spec["month"])["start"]
        return {"date": start.date().isoformat(), "start_time": start.strftime("%H:%M")}
    if fam == "meeting_details":
        ev = ws.meeting(spec["org"], spec["month"])
        return {"duration_minutes": int((ev["end"] - ev["start"]).total_seconds() // 60), "location": ev["location"]}
    if fam == "invoice_total":
        inv = ws.invoice(spec["org"], spec["month"])
        return {"invoice_number": inv["number"], "amount": inv["amount"]}
    if fam == "payment_status":
        inv = ws.invoice(spec["org"], spec["month"])
        pay = ws.payment(inv["number"])
        return {"due_on": inv["due"].isoformat(), "paid_on": pay["on"].isoformat(),
                "days_late": max(0, (pay["on"] - inv["due"]).days)}
    if fam == "docs_before_meeting":
        docs = ws.documents(spec["org"], spec["month"])
        met = ws.meeting(spec["org"], spec["month"])["start"].date()
        return {"docs_received_on": docs.isoformat(), "meeting_on": met.isoformat(), "before_meeting": docs < met}
    if fam.startswith("sweep_"):
        month = spec["month"]
        rows = [(o, ws.invoice(o, month)) for o in ws.orgs(month)]
        pays = {o: ws.payment(inv["number"]) for o, inv in rows}
        if fam == "sweep_total":
            return {"invoices": len(rows), "total": round(sum(inv["amount"] for _, inv in rows), 2)}
        if fam == "sweep_unpaid":
            return {"invoice_numbers": sorted(inv["number"] for o, inv in rows
                                              if pays[o] is None or pays[o]["amount"] < inv["amount"] - 0.005)}
        if fam == "sweep_late":
            return {"names": sorted(o for o, inv in rows if pays[o] and pays[o]["on"] > inv["due"])}
    pairs = [(o, m) for o in spec.get("orgs", []) for m in spec.get("months", [])]
    if fam == "total_invoiced":
        return {"total": round(sum(ws.invoice(o, m)["amount"] for o, m in pairs), 2)}
    if fam == "hours_billed":
        return {"hours": sum(ws.invoice(o, m)["hours"] for o, m in pairs)}
    if fam == "unpaid_invoices":
        out = []
        for o, m in pairs:
            inv = ws.invoice(o, m)
            pay = ws.payment(inv["number"])
            if pay is None or pay["amount"] < inv["amount"] - 0.005:
                out.append(inv["number"])
        return {"invoice_numbers": sorted(out)}
    if fam == "late_payers":
        late = set()
        for o, m in pairs:
            inv = ws.invoice(o, m)
            pay = ws.payment(inv["number"])
            if pay and pay["on"] > inv["due"]:
                late.add(o)
        return {"clients": sorted(late)}
    raise ValueError(f"unknown family {fam}")


if __name__ == "__main__":
    workspace, spec_path = sys.argv[1], sys.argv[2]
    answer = solve(Workspace(workspace), json.loads(Path(spec_path).read_text()))
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(workspace) / "answer.json"
    out.write_text(json.dumps(answer, indent=1) + "\n")
    print(json.dumps(answer))
