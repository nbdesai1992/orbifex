"""Render a world into the files an agent sees: mail, calendar, drive and chat.

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

from .world import (Cycle, World, add_business_days, fmt_day, fmt_when, money,
                    month_label, rng, short_hash)


@dataclass
class Claim:
    fact: str            # "<org>/<month>/<attribute>"
    value: str           # normalised
    current: bool


@dataclass
class Artifact:
    id: str
    source: str          # mail | calendar | drive | chat
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
        self.chat: dict[str, list[dict]] = {}
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
            if "chat" in w.tier.sources:
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
                if "chat" in w.tier.sources:
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
            if "chat" in w.tier.sources and r.random() < 0.5:
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
        handle = self.p["first"].lower() if who == "focal" else self.w.pack["assistant"]["handle"]
        day = when.date().isoformat()
        self.chat.setdefault(day, []).append({"ts": when.isoformat(), "user": handle, "text": text})
        self.artifacts.append(Artifact(short_hash(self.w.seed, day, handle, text, n=12), "chat", f"chat/ops/{day}.json",
                                       when, "message", text, c.org.key if c else None, c.ym if c else None, list(claims)))

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

        if "chat" in w.tier.sources:
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
        cal = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Calendar Export//EN", "CALSCALE:GREGORIAN",
               f"X-WR-CALNAME:{self.p['name']}", f"X-WR-TIMEZONE:{self.p['timezone']}"] + sorted(self.events) + ["END:VCALENDAR"]
        self.files["calendar/calendar.ics"] = ("\r\n".join(cal) + "\r\n").encode()
        for day, messages in self.chat.items():
            messages.sort(key=lambda m: m["ts"])
            self.files[f"chat/ops/{day}.json"] = (json.dumps(messages, indent=1) + "\n").encode()
        return Rendered(dict(sorted(self.files.items())), self.artifacts)


def render_world(world: World) -> Rendered:
    return Renderer(world).render()
