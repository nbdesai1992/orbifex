"""Render a world into the files an agent sees.

First-party sources are the persona's own mail, calendar and drive. Third-party
sources are exports from the apps around them: a Slack workspace, the bank, an
invoicing app, a time tracker and a retailer's order history. Each app keeps
its own copy of some facts, and one of them (the invoicing app) is out of date
by design, because due-date extensions agreed over email never reach it.

Every rendered unit is also recorded as an Artifact with the facts it asserts
(claims), so later stages can tell which artifacts carry the current value of a
fact and which carry a superseded one. Claims never ship to the agent.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
from dataclasses import dataclass, field
from email.utils import format_datetime

from .world import (Cycle, World, add_business_days, business_day, fmt_day, fmt_when, money,
                    month_label, rng, shift_month, short_hash)


@dataclass
class Claim:
    fact: str            # "<org>/<month>/<attribute>"
    value: str           # normalised
    current: bool


@dataclass
class Artifact:
    id: str
    source: str          # mail | calendar | drive | slack | bank | invoicing | timesheets | orders
    path: str            # file the agent would open
    when: dt.datetime
    kind: str
    text: str            # what a search over this unit would see
    org: str | None = None
    ym: str | None = None
    claims: list[Claim] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Rendered:
    files: dict[str, bytes]
    artifacts: list[Artifact]


def norm_time(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M")


def norm_money(x: float) -> str:
    return f"{x:.2f}"


def listing(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def short_when(t: dt.datetime) -> str:
    hour = t.hour % 12 or 12
    return f"{t.strftime('%a')} {t.month}/{t.day} {hour}:{t.minute:02d}{'am' if t.hour < 12 else 'pm'}"


class Renderer:
    def __init__(self, world: World):
        self.w = world
        self.p = world.pack["persona"]
        self.v = world.pack["vocab"]
        self.voice = world.pack["voice"]
        self.files: dict[str, bytes] = {}
        self.artifacts: list[Artifact] = []
        self.events: list[str] = []
        self.slack: dict[str, list[dict]] = {}
        team = "T" + short_hash(world.seed, "slack-team", n=8).upper()
        self.slack_team = team
        self.slack_users = {who: "U" + short_hash(world.seed, "slack-user", who, n=8).upper() for who in ("focal", "assistant")}
        self.uid_host = "calendar." + self.p["email"].split("@")[1]   # nothing agent-visible names the generator

    # ------------------------------------------------------------ helpers

    def claim(self, c: Cycle, attr: str, value: str) -> Claim:
        final = {
            "meeting": norm_time(c.final("meeting")),
            "amount": norm_money(c.final("amount")),
            "hours": f"{c.final('hours'):.1f}",
            "due": c.final("due").isoformat(),
            "invoice_no": c.invoice_no,
            "docs": c.docs_at.date().isoformat(),
            "paid": f"{c.paid_at.date().isoformat()}|{norm_money(c.paid_amount)}" if c.paid_at else "none",
            "length": f"{c.meeting_minutes}|{c.meeting_mode}",
        }[attr]
        return Claim(f"{c.fid}/{attr}", value, value == final)

    def title(self, c: Cycle) -> str:
        return f"{month_label(c.ym)} {self.v['meeting_noun']} - {c.org.name}"

    def due_as_of(self, c: Cycle, when: dt.datetime) -> dt.date:
        known = [d for d in c.due if d.at <= when]
        return (known[-1] if known else c.due[0]).value

    def mail(self, *, sender: tuple[str, str], to: tuple[str, str], subject: str, body: str,
             when: dt.datetime, kind: str, c: Cycle | None = None, claims=(), tags=(),
             reply_to: str | None = None, attachments: list[tuple[str, str]] = ()) -> str:
        key = short_hash(self.w.seed, sender[1], to[1], subject, when.isoformat(), kind, body, n=12)
        msg_id = f"<{key}@{sender[1].split('@')[1]}>"
        head = [f"From: {sender[0]} <{sender[1]}>", f"To: {to[0]} <{to[1]}>", f"Subject: {subject}",
                f"Date: {format_datetime(when)}", f"Message-ID: {msg_id}"]
        if reply_to:
            head += [f"In-Reply-To: {reply_to}", f"References: {reply_to}"]
        head.append("MIME-Version: 1.0")
        text = ['Content-Type: text/plain; charset="utf-8"', "Content-Transfer-Encoding: 8bit", "", body.rstrip("\n")]
        if attachments:                            # written out by hand so the files stay readable as text
            mark = f"=_part_{key}"
            lines = head + [f'Content-Type: multipart/mixed; boundary="{mark}"', "", f"--{mark}"] + text
            for name, content in attachments:
                lines += [f"--{mark}", f'Content-Type: text/csv; charset="utf-8"; name="{name}"',
                          f'Content-Disposition: attachment; filename="{name}"', "Content-Transfer-Encoding: 8bit",
                          "", content.replace("\r\n", "\n").rstrip("\n")]
            lines.append(f"--{mark}--")
        else:
            lines = head + text
        folder = "Sent" if sender[1] == self.p["email"] else "INBOX"
        path = f"mail/{folder}/{key}.eml"
        assert path not in self.files, f"two messages share an id: {subject}"
        self.files[path] = ("\n".join(lines) + "\n").encode()
        names = " ".join(n for n, _ in attachments)
        self.artifacts.append(Artifact(key, "mail", path, when, kind, f"{subject}\n{sender[0]} {to[0]}\n{body}\n{names}",
                                       c.org.key if c else None, c.ym if c else None, list(claims), list(tags)))
        return msg_id

    def me(self) -> tuple[str, str]:
        return (self.p["name"], self.p["email"])

    def them(self, c: Cycle) -> tuple[str, str]:
        return (c.org.contact, c.org.contact_email)

    def hello(self, name: str) -> str:
        return self.p["greeting"].format(first=name)

    def sign(self, c: Cycle) -> str:
        return f"{c.org.contact_first}\n{c.org.name}"

    def invoice_block(self, c: Cycle, i: int, when: dt.datetime) -> tuple[str, list[Claim]]:
        hours, amount = c.hours[i].value, c.amount[i].value
        due = self.due_as_of(c, when)
        block = (f"Invoice: {c.invoice_no}\n"
                 f"For: {self.v['invoice_item'].format(month=month_label(c.ym))}\n"
                 f"{self.v['unit'].capitalize()}: {hours:g} at {money(c.rate)}/{self.v['unit'].rstrip('s')}\n"
                 f"Total due: {money(amount)}\n"
                 f"Due date: {fmt_day(due)}")
        claims = [self.claim(c, "invoice_no", c.invoice_no), self.claim(c, "amount", norm_money(amount)),
                  self.claim(c, "hours", f"{hours:.1f}"), self.claim(c, "due", due.isoformat())]
        return block, claims

    def statement(self, c: Cycle, name: str) -> str:
        r = rng(self.w.seed, c.fid, name, "statement")
        lo, hi = self.w.tier.statement_rows
        y, m = map(int, c.ym.split("-"))
        merchants = self.v["row_labels"]
        out = io.StringIO()
        wr = csv.writer(out)
        wr.writerow(["date", "description", "amount", "balance"])
        balance = round(r.uniform(4000, 60000), 2)
        for _ in range(r.randint(lo, hi)):
            amt = round(r.uniform(-3200, 4200), 2)
            balance = round(balance + amt, 2)
            ref = r.randint(1000, 9999)
            wr.writerow([f"{y}-{m:02d}-{r.randint(1, 28):02d}", f"{r.choice(merchants)} {ref}", f"{amt:.2f}", f"{balance:.2f}"])
        return out.getvalue()

    # ------------------------------------------------------------ one cycle

    def cycle(self, c: Cycle) -> None:
        w, v, voice = self.w, self.v, self.voice
        r = rng(w.seed, c.fid, "render")
        month = month_label(c.ym)
        noun = v["meeting_noun"]
        first = c.org.contact_first
        slug = c.org.key

        # 1. the request, which states the meeting time as first planned
        subject = v["request_subject"].format(month=month, org=c.org.name)
        ask = v["request_ask"].format(month=month, deliverables=listing(c.deliverables), ask_by=fmt_day(c.ask_by))
        m0 = c.meeting[0]
        body = "\n\n".join(x for x in [self.hello(first), r.choice(voice["openers"]), ask,
                                        f"Our {noun} is set for {fmt_when(m0.value)}.",
                                        r.choice(voice["closers"]), self.p["signoff"]] if x)
        req_id = self.mail(sender=self.me(), to=self.them(c), subject=subject, body=body, when=c.request_at,
                           kind="request", c=c, claims=[self.claim(c, "meeting", norm_time(m0.value))])

        # 2. the documents arrive
        names = [f"{slug}-{c.ym}-{d.replace(' ', '-')}.csv" for d in c.deliverables]
        attachments = [(n, self.statement(c, n)) for n in names]
        body = "\n\n".join(x for x in [f"Hi {self.p['first']},", r.choice(voice["contact_openers"]),
                                        f"Attached are the {month} {listing(c.deliverables)}.", self.sign(c)] if x)
        self.mail(sender=self.them(c), to=self.me(), subject=f"Re: {subject}", body=body, when=c.docs_at,
                  kind="documents", c=c, claims=[self.claim(c, "docs", c.docs_at.date().isoformat())],
                  reply_to=req_id, attachments=attachments)
        if "drive" in w.tier.sources:
            for n, content in attachments:
                self.drive(f"Clients/{c.org.name}/{c.ym}/{n}", content, c.docs_at, "statement", c)

        # 3. reschedules, including proposals that were turned down
        thread = f"Rescheduling: {self.title(c)}"
        for prop, when in c.declined:
            self.mail(sender=self.them(c), to=self.me(), subject=thread, when=when, kind="proposal", c=c,
                      body=f"Hi {self.p['first']},\n\nCould we do {fmt_when(prop)} for our {noun} instead?\n\n{self.sign(c)}",
                      claims=[self.claim(c, "meeting", norm_time(prop))], tags=["declined_proposal"])
            self.mail(sender=self.me(), to=self.them(c), subject=f"Re: {thread}", kind="decline", c=c,
                      when=when + dt.timedelta(minutes=r.randint(20, 70)),
                      body=f"{self.hello(first)}\n\nThat one doesn't work on my end. Let me look for another slot.\n\n{self.p['signoff']}")
        for ver in c.meeting[1:]:
            asked = ver.at - dt.timedelta(minutes=r.randint(45, 170))
            claim = [self.claim(c, "meeting", norm_time(ver.value))]
            if ver.by == "contact":
                self.mail(sender=self.them(c), to=self.me(), subject=thread, when=asked, kind="reschedule_ask", c=c,
                          body=f"Hi {self.p['first']},\n\nI need to move our {noun}; {ver.note}. Would {fmt_when(ver.value)} work?\n\n{self.sign(c)}",
                          claims=claim, tags=["proposal"])
                self.mail(sender=self.me(), to=self.them(c), subject=f"Re: {thread}", when=ver.at, kind="reschedule_confirm", c=c,
                          body=f"{self.hello(first)}\n\nThat works. Confirmed: our {noun} is now {fmt_when(ver.value)}. I've updated the invite.\n\n{self.p['signoff']}",
                          claims=claim)
            else:
                self.mail(sender=self.me(), to=self.them(c), subject=thread, when=asked, kind="reschedule_ask", c=c,
                          body=f"{self.hello(first)}\n\nI need to move our {noun}. Could you do {fmt_when(ver.value)} instead?\n\n{self.p['signoff']}",
                          claims=claim, tags=["proposal"])
                self.mail(sender=self.them(c), to=self.me(), subject=f"Re: {thread}", when=ver.at, kind="reschedule_confirm", c=c,
                          body=f"Hi {self.p['first']},\n\nYes, that's fine. Confirmed for {fmt_when(ver.value)}.\n\n{self.sign(c)}",
                          claims=claim)
            if "slack" in w.tier.sources:
                self.say("assistant", asked - dt.timedelta(hours=r.randint(3, 20)), c,
                         f"Reminder: {c.org.name} {noun} is {short_when(c.meeting[c.meeting.index(ver) - 1].value)}. Want the workpapers printed?",
                         [self.claim(c, "meeting", norm_time(c.meeting[c.meeting.index(ver) - 1].value))])
                self.say("focal", ver.at + dt.timedelta(minutes=r.randint(3, 40)), c,
                         f"Moved the {c.org.name} {noun} to {short_when(ver.value)}.", claim)

        # 4. the calendar holds the final time; an old slot may linger as cancelled
        final_meeting = c.final("meeting")
        self.event(uid=f"{short_hash(w.seed, c.fid, 'review')}@{self.uid_host}", summary=self.title(c), start=final_meeting,
                   minutes=c.meeting_minutes, location=c.meeting_mode, attendee=self.them(c),
                   sequence=len(c.meeting) - 1, stamp=c.meeting[-1].at, c=c,
                   claims=[self.claim(c, "meeting", norm_time(final_meeting)),
                           self.claim(c, "length", f"{c.meeting_minutes}|{c.meeting_mode}")])
        if w.tier.cancelled_leftovers and len(c.meeting) > 1 and r.random() < 0.7:
            old = c.meeting[0]
            self.event(uid=f"{short_hash(w.seed, c.fid, 'review-old')}@{self.uid_host}", summary=self.title(c), start=old.value,
                       minutes=c.meeting_minutes, location=c.meeting_mode, attendee=self.them(c), sequence=0,
                       stamp=old.at, status="CANCELLED", c=c, tags=["cancelled_leftover"],
                       claims=[self.claim(c, "meeting", norm_time(old.value)),
                               self.claim(c, "length", f"{c.meeting_minutes}|{c.meeting_mode}")])
        if "drive" in w.tier.sources:
            notes = (f"# {self.title(c)}\n\nHeld: {fmt_when(final_meeting)} ({c.meeting_mode})\n"
                     f"Attendees: {self.p['name']}, {c.org.contact}\n\n"
                     f"- {r.choice(voice['note_lines']).format(month=month, n=r.randint(1, 6))}\n"
                     f"- {c.org.contact_first} to send {r.choice(voice['follow_ups'])}.\n"
                     f"- Next {noun} in about a month.\n")
            self.drive(f"Clients/{c.org.name}/{c.ym}/{noun} notes {final_meeting.date().isoformat()}.md", notes,
                       final_meeting + dt.timedelta(hours=2), "notes", c,
                       [self.claim(c, "meeting", norm_time(final_meeting))])

        # 5. the invoice, then any corrections
        inv_subject = v["invoice_subject"].format(invoice_no=c.invoice_no, month=month)
        first_id = None
        for i, ver in enumerate(c.amount):
            block, claims = self.invoice_block(c, i, ver.at)
            if i == 0:
                body = f"{self.hello(first)}\n\nHere is the invoice for the {month} {v['cycle']}.\n\n{block}\n\n{self.p['signoff']}"
                first_id = self.mail(sender=self.me(), to=self.them(c), subject=inv_subject, body=body, when=ver.at,
                                     kind="invoice", c=c, claims=claims)
                name = f"Invoice {c.invoice_no}.txt"
            else:
                prev = c.amount[i - 1]
                lead = [f"Corrected invoice {c.invoice_no} (revision {i + 1}). {ver.note[0].upper()}{ver.note[1:]}.",
                        f"This replaces the version sent on {fmt_day(prev.at.date())}, which showed {money(prev.value)}."]
                if r.random() < 0.5:
                    lead.reverse()
                body = f"{self.hello(first)}\n\n{' '.join(lead)}\n\n{block}\n\n{self.p['signoff']}"
                self.mail(sender=self.me(), to=self.them(c), subject=f"{inv_subject} (corrected)", body=body, when=ver.at,
                          kind="invoice_correction", c=c, reply_to=first_id,
                          claims=claims + [self.claim(c, "amount", f"{prev.value:.2f}")])
                name = f"Invoice {c.invoice_no} (corrected{'' if i == 1 else ' ' + str(i)}).txt"
                if "slack" in w.tier.sources:
                    self.say("focal", ver.at + dt.timedelta(minutes=r.randint(2, 30)), c,
                             f"Resent {c.invoice_no} to {c.org.name}, corrected total {money(ver.value)}.",
                             [self.claim(c, "amount", f"{ver.value:.2f}")])
            if "drive" in w.tier.sources:
                self.drive(f"Clients/{c.org.name}/{c.ym}/{name}", f"{self.p['org']}\n\n{block}\n", ver.at, "invoice_file", c, claims)

        # 6. a due-date extension
        for ver in c.due[1:]:
            asked = ver.at - dt.timedelta(minutes=r.randint(40, 200))
            claim = [self.claim(c, "due", ver.value.isoformat())]
            self.mail(sender=self.them(c), to=self.me(), subject=f"Re: {inv_subject}", when=asked, kind="extension_ask", c=c,
                      body=f"Hi {self.p['first']},\n\nCould we have until {fmt_day(ver.value)} to pay {c.invoice_no}? {ver.note[0].upper()}{ver.note[1:]}.\n\n{self.sign(c)}",
                      claims=claim, tags=["proposal"], reply_to=first_id)
            self.mail(sender=self.me(), to=self.them(c), subject=f"Re: {inv_subject}", when=ver.at, kind="extension_grant", c=c,
                      body=f"{self.hello(first)}\n\nThat's fine. New due date for {c.invoice_no}: {fmt_day(ver.value)}.\n\n{self.p['signoff']}",
                      claims=claim, reply_to=first_id)

        # 7. someone forwards the superseded invoice after the correction went out
        if c.late_forward_at and len(c.amount) > 1:
            block, claims = self.invoice_block(c, 0, c.amount[0].at)
            self.mail(sender=self.them(c), to=self.me(), subject=f"Fwd: {inv_subject}", when=c.late_forward_at,
                      kind="late_forward", c=c, tags=["late_forward"], claims=claims,
                      body=(f"Hi {self.p['first']},\n\nOur office manager found this in the queue. Is this the one to pay?\n\n"
                            f"---------- Forwarded message ----------\nFrom: {self.p['name']} <{self.p['email']}>\n"
                            f"Date: {fmt_day(c.amount[0].at.date())}\nSubject: {inv_subject}\n\n{block}\n\n{self.sign(c)}"))
            self.mail(sender=self.me(), to=self.them(c), subject=f"Re: Fwd: {inv_subject}", kind="forward_reply", c=c,
                      when=c.late_forward_at + dt.timedelta(minutes=r.randint(25, 140)),
                      body=f"{self.hello(first)}\n\nNo, please ignore that one and use the corrected invoice I sent afterwards.\n\n{self.p['signoff']}")

        # 8. payment, or a reminder when nothing arrived
        bank = (w.pack["bank"]["name"], w.pack["bank"]["email"])
        if c.paid_at:
            line = v["payment_line"].format(amount=money(c.paid_amount), payer=c.org.payer,
                                            date=fmt_day(c.paid_at.date()), invoice_no=c.invoice_no)
            paid = f"{c.paid_at.date().isoformat()}|{norm_money(c.paid_amount)}"
            self.mail(sender=bank, to=self.me(), subject="Payment received", body=f"{line}\n\nThis is an automated notice.",
                      when=c.paid_at, kind="payment_notice", c=c, claims=[self.claim(c, "paid", paid)])
            if "slack" in w.tier.sources and r.random() < 0.5:
                self.say("assistant", c.paid_at + dt.timedelta(hours=r.randint(2, 6)), c,
                         f"{c.org.name} paid {c.invoice_no}: {money(c.paid_amount)}.", [self.claim(c, "paid", paid)])
        else:
            end = dt.datetime(w.today.year, w.today.month, w.today.day, 9, 0, tzinfo=w.tz)
            when = dt.datetime.combine(add_business_days(c.final("due"), 3), dt.time(9, 15), tzinfo=w.tz)
            if when < end:
                self.mail(sender=self.me(), to=self.them(c), subject=f"Reminder: {c.invoice_no} is past due", when=when,
                          kind="reminder", c=c, reply_to=first_id,
                          body=f"{self.hello(first)}\n\nA quick reminder that {c.invoice_no} is past due. I haven't seen a payment come through yet.\n\n{self.p['signoff']}")

    # ------------------------------------------------------------ sources

    def event(self, *, uid: str, summary: str, start: dt.datetime, minutes: int, location: str = "",
              attendee: tuple[str, str] | None = None, sequence: int = 0, stamp: dt.datetime | None = None,
              status: str = "CONFIRMED", rrule: str | None = None, c: Cycle | None = None,
              claims=(), tags=(), all_day: bool = False) -> None:
        tzid = self.p["timezone"]
        stamp = stamp or start
        lines = ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp.astimezone(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"]
        if all_day:
            lines += [f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(start + dt.timedelta(days=1)).strftime('%Y%m%d')}"]
        else:
            end = start + dt.timedelta(minutes=minutes)
            lines += [f"DTSTART;TZID={tzid}:{start.strftime('%Y%m%dT%H%M%S')}",
                      f"DTEND;TZID={tzid}:{end.strftime('%Y%m%dT%H%M%S')}"]
        lines += [f"SUMMARY:{summary}", f"SEQUENCE:{sequence}", f"STATUS:{status}"]
        if rrule:
            lines.append(f"RRULE:{rrule}")
        if location:
            lines.append(f"LOCATION:{location.replace(',', chr(92) + ',')}")
        lines.append(f"ORGANIZER;CN={self.p['name']}:mailto:{self.p['email']}")
        if attendee:
            lines.append(f"ATTENDEE;CN={attendee[0]}:mailto:{attendee[1]}")
        lines.append("END:VEVENT")
        self.events.append("\r\n".join(lines))
        self.artifacts.append(Artifact(uid.split("@")[0], "calendar", "calendar/calendar.ics", stamp, "event",
                                       f"{summary}\n{fmt_when(start)}\n{minutes} minutes\n{location}\n{status}",
                                       c.org.key if c else None, c.ym if c else None, list(claims), list(tags)))

    def drive(self, path: str, content: str, when: dt.datetime, kind: str, c: Cycle | None = None,
              claims=(), tags=()) -> None:
        full = f"drive/{path}"
        self.files[full] = content.encode()
        self.artifacts.append(Artifact(short_hash(self.w.seed, full, n=12), "drive", full, when, kind,
                                       f"{path}\n{content if kind != 'statement' else ''}",
                                       c.org.key if c else None, c.ym if c else None, list(claims), list(tags)))

    def say(self, who: str, when: dt.datetime, c: Cycle | None, text: str, claims=()) -> None:
        """One message in the Slack export, which keeps a file per channel per day."""
        uid = self.slack_users["focal" if who == "focal" else "assistant"]
        day = when.date().isoformat()
        micro = int(short_hash(self.w.seed, day, uid, text, n=6), 16) % 1_000_000
        self.slack.setdefault(day, []).append({"type": "message", "user": uid, "text": text,
                                               "ts": f"{int(when.timestamp())}.{micro:06d}", "team": self.slack_team})
        self.artifacts.append(Artifact(short_hash(self.w.seed, day, uid, text, n=12), "slack", f"slack/ops/{day}.json",
                                       when, "message", text, c.org.key if c else None, c.ym if c else None, list(claims)))

    def unit(self, source: str, path: str, content: str, when: dt.datetime, kind: str, claims=(), tags=()) -> None:
        """A whole file from a third-party export, recorded as one unit."""
        self.files[path] = content.encode()
        self.artifacts.append(Artifact(short_hash(self.w.seed, path, n=12), source, path, when, kind,
                                       f"{path}\n{content}", None, None, list(claims), list(tags)))

    def export_time(self, minute: int) -> dt.datetime:
        t = self.w.today
        return dt.datetime(t.year, t.month, t.day, 7, minute, tzinfo=self.w.tz)

    # ------------------------------------------------------------ third-party apps

    def apps(self) -> None:
        src = self.w.tier.sources
        self.orders_mail()                          # purchases reach the mailbox at every tier
        if "bank" in src:
            self.bank()
        if "invoicing" in src:
            self.invoicing()
        if "timesheets" in src:
            self.timesheets()
        if "orders" in src:
            self.orders_export()

    def orders_mail(self) -> None:
        w = self.w
        if not w.orders:
            return
        shop = (w.pack["shop"]["name"], w.pack["shop"]["email"])
        for o in w.orders:
            items = "\n".join(f"  {q} x {name} at {money(price)}" for name, q, price in o.lines)
            body = (f"Hi {self.p['first']},\n\nThanks for your order.\n\nOrder number: {o.id}\n"
                    f"Placed on: {fmt_day(o.placed_at.date())}\nItems:\n{items}\nOrder total: {money(o.total)}\n\n"
                    f"We'll email you when it ships.\n\n{shop[0]}")
            self.mail(sender=shop, to=self.me(), subject=f"Order {o.id} confirmed", body=body, when=o.placed_at, kind="order",
                      claims=[Claim(f"{o.fid}/total", norm_money(o.total), True)])
            self.mail(sender=shop, to=self.me(), subject=f"Order {o.id} has shipped", kind="order_shipped",
                      when=o.placed_at + dt.timedelta(days=1, hours=5),
                      body=f"Hi {self.p['first']},\n\nYour order {o.id} is on its way.\n\n{shop[0]}")
            if not o.refund:
                continue
            if o.estimate is not None:
                self.mail(sender=shop, to=self.me(), subject=f"Return received for order {o.id}", when=o.estimate_at,
                          kind="refund_estimate", tags=["refund_estimate"],
                          claims=[Claim(f"{o.fid}/refund", norm_money(o.estimate), False)],
                          body=(f"Hi {self.p['first']},\n\nWe have your return of {o.returned} from order {o.id}.\n\n"
                                f"Estimated refund: up to {money(o.estimate)}, depending on inspection.\n\n{shop[0]}"))
            self.mail(sender=shop, to=self.me(), subject=f"Refund issued for order {o.id}", when=o.refund_at, kind="refund",
                      claims=[Claim(f"{o.fid}/refund", norm_money(o.refund), True)],
                      body=(f"Hi {self.p['first']},\n\nRefund issued for order {o.id}: {money(o.refund)}\n"
                            f"Item returned: {o.returned}\nA 15% restocking fee was deducted.\n"
                            f"The refund goes back to your original payment method.\n\n{shop[0]}"))

    def bank(self) -> None:
        """Monthly statement exports. Client payments, card purchases and refunds all post here."""
        w, bank = self.w, self.w.pack["bank"]
        shop = w.pack["shop"]["name"].upper() if w.orders else ""
        rows: list[tuple[dt.date, str, float, list[Claim]]] = []
        for c in w.cycles:
            if c.paid_at:
                paid = f"{c.paid_at.date().isoformat()}|{norm_money(c.paid_amount)}"
                rows.append((c.paid_at.date(), f"ACH DEPOSIT {c.org.payer} {c.invoice_no}", c.paid_amount, [self.claim(c, "paid", paid)]))
        for o in w.orders:
            rows.append((add_business_days(o.placed_at.date(), 1), f"CARD PURCHASE {shop} {o.id}", -o.total,
                         [Claim(f"{o.fid}/total", norm_money(o.total), True)]))
            if o.refund:
                rows.append((add_business_days(o.refund_at.date(), 2), f"CARD REFUND {shop} {o.id}", o.refund,
                             [Claim(f"{o.fid}/refund", norm_money(o.refund), True)]))
        first = w.start.strftime("%Y-%m")
        months = [first]
        while months[-1] < w.today.strftime("%Y-%m"):
            months.append(shift_month(months[-1], 1))
        for ym in months:
            y, m = map(int, ym.split("-"))
            r = rng(w.seed, "bank", ym)
            for desc, amount, day in bank.get("recurring", []):
                rows.append((business_day(dt.date(y, m, min(day, 28))), desc, float(amount), []))
            for _ in range(6 + 4 * w.tier.level):
                rows.append((dt.date(y, m, r.randint(1, 28)), f"CARD PURCHASE {r.choice(bank.get('card_merchants', ['MERCHANT']))} {r.randint(1000, 9999)}",
                             -round(r.uniform(4, 90), 2), []))
        rows = [x for x in rows if x[0] <= w.today]
        for ym in months[:-1]:                      # most of each month's surplus is swept to savings
            net = sum(amount for day, _, amount, _ in rows if day.strftime("%Y-%m") == ym)
            if net > 500:
                y, m = map(int, ym.split("-"))
                rows.append((business_day(dt.date(y, m, 28), step=-1), "TRANSFER TO SAVINGS", -round(net * 0.85, 2), []))
        rows.sort(key=lambda x: (x[0], x[1]))
        balance = round(rng(w.seed, "bank", "opening").uniform(18000, 42000), 2)
        for ym in months:
            out = io.StringIO()
            wr = csv.writer(out)
            wr.writerow(["Account", bank.get("account", "Checking")])
            wr.writerow(["Date", "Description", "Amount", "Balance"])
            claims: list[Claim] = []
            for day, desc, amount, cl in rows:
                if day.strftime("%Y-%m") != ym:
                    continue
                balance = round(balance + amount, 2)
                wr.writerow([day.isoformat(), desc, f"{amount:.2f}", f"{balance:.2f}"])
                claims += cl
            y, m = map(int, ym.split("-"))
            last = dt.date(*map(int, shift_month(ym, 1).split("-")), 1) - dt.timedelta(days=1)
            when = min(dt.datetime(last.year, last.month, last.day, 23, 0, tzinfo=w.tz), self.export_time(0))
            self.unit("bank", f"bank/statements/{ym}.csv", out.getvalue(), when, "statement_export", claims)

    def invoicing(self) -> None:
        """The invoicing app's export. Totals are current. Due dates are as first issued, because
        extensions agreed over email were never entered, so the app is stale for every extended invoice."""
        w = self.w
        inv, pay = io.StringIO(), io.StringIO()
        wi, wp = csv.writer(inv), csv.writer(pay)
        wi.writerow(["invoice_no", "customer", "issue_date", "due_date", "total", "status", "amount_paid", "balance_due"])
        wp.writerow(["payment_date", "invoice_no", "customer", "amount", "method"])
        inv_claims, pay_claims, tags = [], [], []
        for c in sorted(w.cycles, key=lambda c: (c.issued_at, c.invoice_no)):
            total, due0 = c.final("amount"), c.due[0].value
            paid = c.paid_amount if c.paid_at else 0.0
            status = "Paid" if c.paid_at and paid >= total - 0.005 else "Partial" if c.paid_at else \
                "Overdue" if w.today > due0 else "Open"
            wi.writerow([c.invoice_no, c.org.name, c.issued_at.date().isoformat(), due0.isoformat(), f"{total:.2f}", status,
                         f"{paid:.2f}", f"{total - paid:.2f}"])
            inv_claims += [self.claim(c, "invoice_no", c.invoice_no), self.claim(c, "amount", norm_money(total)),
                           self.claim(c, "due", due0.isoformat())]
            if len(c.due) > 1:
                tags.append(f"app_lag:{c.invoice_no}")
            if c.paid_at:
                wp.writerow([c.paid_at.date().isoformat(), c.invoice_no, c.org.name, f"{paid:.2f}", "ACH"])
                pay_claims.append(self.claim(c, "paid", f"{c.paid_at.date().isoformat()}|{norm_money(paid)}"))
        self.unit("invoicing", "invoicing/invoices.csv", inv.getvalue(), self.export_time(30), "invoices_export", inv_claims, tags)
        self.unit("invoicing", "invoicing/payments.csv", pay.getvalue(), self.export_time(30), "payments_export", pay_claims)

    def timesheets(self) -> None:
        """The time tracker. Logged time was right all along, so the totals match each final invoice."""
        w = self.w
        summary, entries = io.StringIO(), io.StringIO()
        ws_, we = csv.writer(summary), csv.writer(entries)
        ws_.writerow(["client", "project", "hours"])
        we.writerow(["date", "client", "project", "task", "hours", "billable"])
        claims = []
        tasks = ["Prep", "Working session", "Review", "Follow-up"]
        for c in sorted(w.cycles, key=lambda c: (c.ym, c.org.name)):
            project = self.v["invoice_item"].format(month=month_label(c.ym))
            hours = c.final("hours")
            ws_.writerow([c.org.name, project, f"{hours:g}"])
            claims.append(self.claim(c, "hours", f"{hours:.1f}"))
            r = rng(w.seed, c.fid, "timesheet")
            left, day = hours, c.docs_at.date()
            while left > 0:
                chunk = min(left, r.choice([1.0, 1.5, 2.0, 2.5, 3.0]))
                we.writerow([day.isoformat(), c.org.name, project, r.choice(tasks), f"{chunk:g}", "yes"])
                left = round(left - chunk, 1)
                nxt = add_business_days(day, 1)
                day = nxt if nxt <= c.issued_at.date() else day
        self.unit("timesheets", "timesheets/summary-by-project.csv", summary.getvalue(), self.export_time(20), "time_summary", claims)
        self.unit("timesheets", "timesheets/entries.csv", entries.getvalue(), self.export_time(20), "time_entries")

    def orders_export(self) -> None:
        """The retailer's order history export, with refunds in a second file."""
        w = self.w
        if not w.orders:
            return
        hist, ref = io.StringIO(), io.StringIO()
        wh, wr = csv.writer(hist), csv.writer(ref)
        wh.writerow(["order_id", "order_date", "item", "quantity", "unit_price", "line_total", "order_total"])
        wr.writerow(["order_id", "refund_date", "item", "amount", "note"])
        hist_claims, ref_claims = [], []
        for o in sorted(w.orders, key=lambda o: (o.placed_at, o.id)):
            for name, q, price in o.lines:
                wh.writerow([o.id, o.placed_at.date().isoformat(), name, q, f"{price:.2f}", f"{q * price:.2f}", f"{o.total:.2f}"])
            hist_claims.append(Claim(f"{o.fid}/total", norm_money(o.total), True))
            if o.refund:
                wr.writerow([o.id, o.refund_at.date().isoformat(), o.returned, f"{o.refund:.2f}", "15% restocking fee deducted"])
                ref_claims.append(Claim(f"{o.fid}/refund", norm_money(o.refund), True))
        self.unit("orders", "orders/order-history.csv", hist.getvalue(), self.export_time(10), "order_history", hist_claims)
        self.unit("orders", "orders/refunds.csv", ref.getvalue(), self.export_time(10), "order_refunds", ref_claims)

    # ------------------------------------------------------------ everything else

    def background(self) -> None:
        w, r = self.w, rng(self.w.seed, "background")
        start = dt.datetime(w.start.year, w.start.month, w.start.day, 8, 0, tzinfo=w.tz)
        end = dt.datetime(w.today.year, w.today.month, w.today.day, 8, 0, tzinfo=w.tz)
        span = (end - start).total_seconds()
        for i in range(int(w.tier.noise_per_week * span / (7 * 86400))):
            n = r.choice(w.pack["noise"])
            when = start + dt.timedelta(seconds=r.uniform(0, span))
            fill = {"date": fmt_day((when + dt.timedelta(days=r.randint(2, 20))).date()),
                    "mon": when.strftime("%B"), "n4": str(r.randint(1000, 9999))}
            name, _, addr = n["sender"].rpartition(" <")
            self.mail(sender=(name, addr.rstrip(">")), to=self.me(), subject=r.choice(n["subjects"]).format(**fill),
                      body=r.choice(n["bodies"]).format(**fill), when=when, kind="noise", tags=["noise"])

        self.event(uid=f"weekly-planning@{self.uid_host}", summary="Weekly planning", minutes=30,
                   start=dt.datetime.combine(w.start + dt.timedelta(days=(7 - w.start.weekday()) % 7), dt.time(8, 30), tzinfo=w.tz),
                   rrule="FREQ=WEEKLY;BYDAY=MO", tags=["noise"])
        personal = self.voice["personal_events"]
        weeks = max(1, int(span / (7 * 86400)))
        for i in range(weeks * (1 + w.tier.level)):
            when = start + dt.timedelta(days=r.randint(0, weeks * 7 + 20), hours=r.choice([0, 4, 9, 10]), minutes=r.choice([0, 30]))
            self.event(uid=f"{short_hash(w.seed, 'personal', i)}@{self.uid_host}", summary=r.choice(personal),
                       start=when, minutes=r.choice([30, 60, 90]), tags=["noise"])

        if "slack" in w.tier.sources:
            chatter = self.voice["chatter"]
            for i in range(weeks * 4):
                when = start + dt.timedelta(seconds=r.uniform(0, span))
                self.say(r.choice(["focal", "assistant"]), when, None, r.choice(chatter))

        if "drive" in w.tier.sources:
            self.tracker()
            self.drive("Personal/packing list.md", "# Lake weekend\n\n- sunscreen\n- board games\n- charger\n", start, "personal", tags=["noise"])
            self.drive("Personal/household budget.csv", "month,groceries,utilities\nApr,612.40,231.18\nMay,655.02,219.77\n",
                       start, "personal", tags=["noise"])
            self.drive("Admin/engagement letter template.md",
                       f"# Engagement letter\n\n{self.p['org']} will provide {self.v['service']}.\n", start, "admin", tags=["noise"])
            self.mess()

    def tracker(self) -> None:
        """The invoice tracker. At higher tiers some rows were never updated."""
        w = self.w
        out = io.StringIO()
        wr = csv.writer(out)
        wr.writerow(["invoice_no", self.v["counterparty"], "period", "hours", "amount", "issued", "due", "paid_on", "paid_amount"])
        claims, tags = [], []
        for c in sorted(w.cycles, key=lambda c: (c.ym, c.org.name)):
            r = rng(w.seed, c.fid, "tracker")
            i = 0 if (w.tier.stale_ledger and len(c.amount) > 1 and r.random() < 0.65) else len(c.amount) - 1
            j = 0 if (w.tier.stale_ledger and len(c.due) > 1 and r.random() < 0.65) else len(c.due) - 1
            if i != len(c.amount) - 1 or j != len(c.due) - 1:
                tags.append(f"stale_row:{c.invoice_no}")
            wr.writerow([c.invoice_no, c.org.name, c.ym, f"{c.hours[i].value:g}", f"{c.amount[i].value:.2f}",
                         c.issued_at.date().isoformat(), c.due[j].value.isoformat(),
                         c.paid_at.date().isoformat() if c.paid_at else "", f"{c.paid_amount:.2f}" if c.paid_at else ""])
            claims += [self.claim(c, "amount", f"{c.amount[i].value:.2f}"), self.claim(c, "hours", f"{c.hours[i].value:.1f}"),
                       self.claim(c, "due", c.due[j].value.isoformat()), self.claim(c, "invoice_no", c.invoice_no)]
            if c.paid_at:
                claims.append(self.claim(c, "paid", f"{c.paid_at.date().isoformat()}|{norm_money(c.paid_amount)}"))
        when = dt.datetime(w.today.year, w.today.month, w.today.day, 8, 0, tzinfo=w.tz)
        self.drive("Billing/invoice tracker.csv", out.getvalue(), when, "tracker", None, claims, tags)

    def mess(self) -> None:
        """Duplicates and misfiled copies, each tagged so nothing mistakes it for an error."""
        w, r = self.w, rng(self.w.seed, "mess")
        if not w.tier.duplicate_share:
            return
        pool = [a for a in self.artifacts if a.source == "drive" and a.kind in ("statement", "invoice_file", "notes")]
        folders = sorted({a.path.rsplit("/", 1)[0] for a in pool})
        for a in r.sample(pool, int(len(pool) * w.tier.duplicate_share)):
            folder, name = a.path.rsplit("/", 1)
            stem, dot, ext = name.rpartition(".")
            if r.random() < 0.5:
                new, tag = f"{folder}/{stem} (1){dot}{ext}", "duplicate"
            else:
                new, tag = f"{r.choice(folders)}/{name}", "misfiled"
            if new in self.files:
                continue
            self.files[new] = self.files[a.path]
            self.artifacts.append(Artifact(short_hash(w.seed, new, n=12), "drive", new, a.when, a.kind, a.text,
                                           a.org, a.ym, list(a.claims), a.tags + [tag]))

    def render(self) -> Rendered:
        for c in self.w.cycles:
            self.cycle(c)
        self.background()
        self.apps()
        cal = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Calendar Export//EN", "CALSCALE:GREGORIAN",
               f"X-WR-CALNAME:{self.p['name']}", f"X-WR-TIMEZONE:{self.p['timezone']}"] + sorted(self.events) + ["END:VCALENDAR"]
        self.files["calendar/calendar.ics"] = ("\r\n".join(cal) + "\r\n").encode()
        if self.slack:                              # the layout of a Slack workspace export
            p, a = self.p, self.w.pack["assistant"]
            created = int(dt.datetime(self.w.start.year, self.w.start.month, self.w.start.day, 9, 0, tzinfo=self.w.tz).timestamp())
            users = [{"id": self.slack_users[who], "team_id": self.slack_team, "name": who_d["first"].lower(),
                      "deleted": False, "real_name": who_d["name"], "tz": p["timezone"],
                      "profile": {"real_name": who_d["name"], "display_name": who_d["first"], "email": who_d["email"]},
                      "is_admin": who == "focal", "is_bot": False}
                     for who, who_d in (("focal", p), ("assistant", a))]
            channel = {"id": "C" + short_hash(self.w.seed, "slack-channel", "ops", n=8).upper(), "name": "ops",
                       "created": created, "creator": self.slack_users["focal"], "is_archived": False, "is_general": True,
                       "members": list(self.slack_users.values()),
                       "topic": {"value": "", "creator": "", "last_set": 0},
                       "purpose": {"value": "Day-to-day operations", "creator": self.slack_users["focal"], "last_set": created}}
            self.files["slack/users.json"] = (json.dumps(users, indent=1) + "\n").encode()
            self.files["slack/channels.json"] = (json.dumps([channel], indent=1) + "\n").encode()
            for day, messages in self.slack.items():
                messages.sort(key=lambda m: m["ts"])
                self.files[f"slack/ops/{day}.json"] = (json.dumps(messages, indent=1) + "\n").encode()
        return Rendered(dict(sorted(self.files.items())), self.artifacts)


def render_world(world: World) -> Rendered:
    return Renderer(world).render()
