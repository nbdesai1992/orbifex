"""World model: who exists, what happened, and the history of every fact.

The design rule that everything else depends on: a fact's FINAL value is drawn
from a random stream keyed only by (seed, entity, month). The tier never touches
that stream. Tiers add history (earlier, superseded values), look-alike entities
and volume around the same final truth, so one question has one answer at every
tier.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "0.2.0"


def rng(*keys) -> random.Random:
    digest = hashlib.sha256("|".join(str(k) for k in keys).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def short_hash(*keys, n: int = 10) -> str:
    return hashlib.sha256("|".join(str(k) for k in keys).encode()).hexdigest()[:n]


# ---------------------------------------------------------------- tiers


@dataclass(frozen=True)
class Tier:
    level: int
    plain_extras: int          # ordinary extra counterparties
    collisions: bool           # look-alike counterparties present
    history_months: int        # months of history before the core months
    sources: tuple[str, ...]
    noise_per_week: float      # unrelated mail per week
    reschedule_share: float    # share of core meetings with a reschedule history
    max_reschedules: int
    correction_share: float    # share of core invoices with a correction history
    max_corrections: int
    extension_share: float     # share of core invoices whose due date was extended
    stale_ledger: bool         # tracker rows left at the superseded value
    declined_proposals: bool   # reschedule proposals that were turned down
    late_forwards: bool        # an old invoice forwarded again after its correction
    cancelled_leftovers: bool  # rescheduled meetings leave a cancelled event behind
    duplicate_share: float     # share of drive files duplicated or misfiled
    statement_rows: tuple[int, int]
    extra_orders: int = 0      # unrelated retailer orders per month
    refund_estimates: bool = False   # a refund is preceded by an estimate that turns out too high


TIERS: dict[int, Tier] = {
    1: Tier(1, 0, False, 0, ("mail", "calendar"), 2, 0.0, 0, 0.0, 0, 0.0,
            False, False, False, False, 0.0, (8, 14), 0, False),
    2: Tier(2, 3, False, 1, ("mail", "calendar", "drive", "bank"), 6, 0.0, 0, 0.0, 0, 0.0,
            False, False, False, False, 0.0, (25, 45), 1, False),
    3: Tier(3, 5, True, 4, ("mail", "calendar", "drive", "bank", "slack", "invoicing", "timesheets"),
            14, 0.5, 2, 0.5, 1, 0.5, True, False, False, False, 0.05, (40, 80), 3, True),
    4: Tier(4, 14, True, 7, ("mail", "calendar", "drive", "bank", "slack", "invoicing", "timesheets", "orders"),
            28, 0.85, 3, 0.85, 2, 0.7, True, True, True, True, 0.12, (70, 150), 6, True),
}

# First-party sources are the persona's own mail, calendar and files. The rest are
# exports from third-party apps, each of which keeps its own copy of some facts.
THIRD_PARTY = ("bank", "slack", "invoicing", "timesheets", "orders")


# ---------------------------------------------------------------- entities


@dataclass
class Org:
    key: str
    name: str
    payer: str
    domain: str
    contact: str
    core: bool = False
    collides: str | None = None
    rate: int = 0

    @property
    def contact_first(self) -> str:
        parts = [p for p in self.contact.split() if not p.endswith(".")]
        return parts[0]

    @property
    def contact_email(self) -> str:
        return f"{self.contact_first.lower()}@{self.domain}"


@dataclass
class Version:
    """One value a fact held, and when it started being true."""
    value: object
    at: dt.datetime
    by: str = "focal"          # who set it: "focal" or "contact"
    note: str = ""


@dataclass
class Cycle:
    """One counterparty's engagement cycle for one month."""
    org: Org
    ym: str                    # the month the work is for, "2026-04"
    core: bool
    role: str                  # normal | docs_late | pay_late | pay_short | unpaid
    request_at: dt.datetime
    ask_by: dt.date
    docs_at: dt.datetime
    deliverables: list[str]
    meeting: list[Version]     # last entry is the final time
    meeting_minutes: int
    meeting_mode: str
    declined: list[tuple[dt.datetime, dt.datetime]]   # (proposed time, when proposed)
    invoice_no: str
    hours: list[Version]
    amount: list[Version]
    rate: int
    issued_at: dt.datetime
    due: list[Version]
    paid_at: dt.datetime | None
    paid_amount: float | None
    late_forward_at: dt.datetime | None = None

    @property
    def fid(self) -> str:
        return f"{self.org.key}/{self.ym}"

    def final(self, name: str):
        return getattr(self, name)[-1].value


@dataclass
class Order:
    """One order placed with the retailer. The total and the refund are final facts."""
    id: str
    pm: str                    # the month the order was placed in, "2026-05"
    core: bool
    placed_at: dt.datetime
    lines: list[tuple[str, int, float]]      # (item, quantity, unit price)
    total: float
    refund: float              # 0.0 when nothing went back
    refund_at: dt.datetime | None = None
    returned: str | None = None
    estimate: float | None = None            # a superseded refund estimate, added by higher tiers
    estimate_at: dt.datetime | None = None

    @property
    def fid(self) -> str:
        return f"order-{self.id.lower()}/{self.pm}"

    @property
    def net(self) -> float:
        return round(self.total - self.refund, 2)


@dataclass
class World:
    pack: dict
    seed: int
    tier: Tier
    tz: ZoneInfo
    today: dt.date
    orgs: list[Org]
    months: list[str]
    core_months: list[str]
    cycles: list[Cycle]
    start: dt.date = field(default=None)  # type: ignore[assignment]
    orders: list[Order] = field(default_factory=list)

    @property
    def order_months(self) -> list[str]:
        """Orders are placed in the months the mailbox covers, one after each work month."""
        return [shift_month(m, 1) for m in self.months]

    @property
    def core_order_months(self) -> list[str]:
        return [shift_month(m, 1) for m in self.core_months]

    @property
    def core_orgs(self) -> list[Org]:
        return [o for o in self.orgs if o.core]

    @property
    def core_cycles(self) -> list[Cycle]:
        return [c for c in self.cycles if c.core]

    def cycle(self, org_key: str, ym: str) -> Cycle:
        return next(c for c in self.cycles if c.org.key == org_key and c.ym == ym)


# ---------------------------------------------------------------- calendar helpers

SLOTS = [(h, m) for h in range(9, 17) for m in (0, 30)]


def month_label(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return dt.date(y, m, 1).strftime("%B %Y")


def shift_month(ym: str, k: int) -> str:
    y, m = map(int, ym.split("-"))
    idx = y * 12 + (m - 1) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def business_day(d: dt.date, step: int = 1) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=step)
    return d


def add_business_days(d: dt.date, n: int) -> dt.date:
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def fmt_day(d: dt.date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def fmt_when(t: dt.datetime) -> str:
    hour = t.hour % 12 or 12
    return f"{t.strftime('%A')}, {fmt_day(t.date())} at {hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def money(x: float) -> str:
    return f"${x:,.2f}"


# ---------------------------------------------------------------- simulation


def load_pack(path: str | Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def select_orgs(pack: dict, tier: Tier, seed: int) -> list[Org]:
    raw = pack["orgs"]
    core = [o for o in raw if o.get("core")]
    lookalikes = [o for o in raw if o.get("collides")]
    plain = [o for o in raw if not o.get("core") and not o.get("collides")]
    chosen = core + (lookalikes if tier.collisions else []) + plain[: tier.plain_extras]
    orgs = []
    for o in chosen:
        rate = rng(seed, o["key"], "rate").choice(pack["vocab"]["rate_choices"])
        orgs.append(Org(o["key"], o["name"], o["payer"], o["domain"], o["contact"],
                        bool(o.get("core")), o.get("collides"), rate))
    return orgs


def _final_cycle(seed: int, pack: dict, tz: ZoneInfo, org: Org, ym: str, core: bool, role: str,
                 last_month: bool, taken: set, used_numbers: set) -> Cycle:
    """Draw every final value for one cycle. Never reads the tier."""
    v = pack["vocab"]
    r = rng(seed, org.key, ym, "final")
    work = shift_month(ym, 1)                       # the close happens the month after
    wy, wm = map(int, work.split("-"))

    def at(d: dt.date, h: int, m: int) -> dt.datetime:
        return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=tz)

    request_day = business_day(dt.date(wy, wm, r.randint(1, 3)))
    request_at = at(request_day, r.choice([8, 9, 10]), r.choice([5, 20, 40, 55]))
    ask_by = add_business_days(request_day, r.randint(3, 5))
    docs_day = add_business_days(request_day, r.randint(2, 5))
    docs_at = at(docs_day, r.choice([9, 11, 13, 15, 17]), r.choice([2, 18, 33, 47]))
    deliverables = r.sample(v["deliverables"], r.randint(2, 3))

    day = business_day(dt.date(wy, wm, r.randint(11, 19)))
    if day <= docs_day:                             # the meeting follows the documents
        day = add_business_days(docs_day, 1)
    slot = r.choice(SLOTS)
    while (day, slot) in taken:                     # core cycles are placed first, so
        i = SLOTS.index(slot) + 1                   # extras never move a core meeting
        if i >= len(SLOTS):
            day, i = add_business_days(day, 1), 0
        slot = SLOTS[i]
    taken.add((day, slot))
    meeting_at = at(day, *slot)
    minutes = r.choice([30, 45, 60])
    mode = r.choice(v["modes"])

    if role == "docs_late":                         # documents arrive after the meeting
        docs_at = at(add_business_days(day, 1), 10, 12)

    hours = round(r.uniform(v["qty_min"], v["qty_max"]) * 2) / 2
    amount = round(hours * org.rate, 2)
    issued_day = add_business_days(day, r.randint(2, 3))
    issued_at = at(issued_day, 16, r.choice([5, 25, 45]))
    terms = 15 if last_month else r.choice([15, 30])
    due_day = business_day(issued_day + dt.timedelta(days=terms))

    number = 2000 + int(short_hash(seed, org.key, ym, "inv", n=8), 16) % 7000
    while number in used_numbers:
        number += 1
    used_numbers.add(number)

    # On-time payers settle late in the window, so a stale due date makes them look late.
    paid_day = business_day(due_day - dt.timedelta(days=r.randint(0, 3)), step=-1)
    paid_amount: float | None = amount
    if role == "pay_late":
        paid_day = add_business_days(due_day, r.randint(2, 7))
    elif role == "pay_short":
        paid_amount = round(amount - r.choice([50, 75, 100, 125, 150, 200]), 2)
    paid_at: dt.datetime | None = at(paid_day, r.choice([6, 7]), r.choice([10, 40]))
    if role == "unpaid":
        paid_at, paid_amount = None, None
    return Cycle(org, ym, core, role, request_at, ask_by, docs_at, deliverables,
                 [Version(meeting_at, request_at)], minutes, mode, [],
                 f"INV-{number}", [Version(hours, issued_at)], [Version(amount, issued_at)],
                 org.rate, issued_at, [Version(due_day, issued_at)], paid_at, paid_amount)


def _backstory(seed: int, pack: dict, tz: ZoneInfo, tier: Tier, c: Cycle,
               reschedule: bool, correct: bool, extend: bool) -> None:
    """Prepend superseded values. Final values are left exactly as they were."""
    r = rng(seed, c.org.key, c.ym, "backstory")
    voice = pack["voice"]

    def at(d: dt.date, h: int, m: int) -> dt.datetime:
        return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=tz)

    if reschedule and tier.max_reschedules:
        final = c.meeting[-1].value
        k = r.randint(1, tier.max_reschedules)
        earliest = add_business_days(c.request_at.date(), k + 2)
        priors: list[dt.datetime] = []
        for _ in range(60):
            if len(priors) == k:
                break
            day = business_day(final.date() + dt.timedelta(days=r.choice([-4, -3, -2, -1, 1, 2, 3])))
            cand = at(day, *r.choice(SLOTS))
            if day >= earliest and cand != final and cand not in priors:
                priors.append(cand)
        if priors:
            times = priors + [final]
            versions = [Version(times[0], c.request_at)]
            when = c.request_at
            for t in times[1:]:
                when = at(add_business_days(when.date(), 1), r.choice([9, 11, 14, 16]), r.choice([6, 21, 37, 52]))
                versions.append(Version(t, when, r.choice(["contact", "focal"]),
                                        r.choice(voice["reschedule_reasons"])))
            c.meeting = versions
            if tier.declined_proposals and len(versions) > 1 and r.random() < 0.6:
                last = versions[-1]
                day = business_day(final.date() + dt.timedelta(days=r.choice([-2, -1, 1, 2])))
                prop = at(day, *r.choice(SLOTS))
                if prop not in times:
                    c.declined.append((prop, last.at - dt.timedelta(hours=r.randint(2, 5))))

    if correct and tier.max_corrections:
        final_hours, final_amount = c.hours[-1].value, c.amount[-1].value
        k = r.randint(1, tier.max_corrections)
        stale: list[float] = []
        for _ in range(40):
            if len(stale) == k:
                break
            h = final_hours + r.choice([-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0])
            if h > 1 and h != final_hours and h not in stale:
                stale.append(h)
        if stale:
            hv = [Version(stale[0], c.issued_at)]
            av = [Version(round(stale[0] * c.rate, 2), c.issued_at)]
            when = c.issued_at
            for h in stale[1:] + [final_hours]:
                when = at(add_business_days(when.date(), 1), r.choice([9, 10, 13, 15]), r.choice([12, 28, 44]))
                note = r.choice(voice["correction_reasons"])
                hv.append(Version(h, when, "focal", note))
                av.append(Version(round(h * c.rate, 2), when, "focal", note))
            assert av[-1].value == final_amount
            c.hours, c.amount = hv, av
            if tier.late_forwards and r.random() < 0.7:
                c.late_forward_at = av[-1].at + dt.timedelta(days=r.randint(1, 2), hours=r.randint(1, 5))

    if extend:
        final_due = c.due[-1].value
        old = business_day(final_due - dt.timedelta(days=7), step=-1)
        last_change = c.amount[-1].at.date()
        if old > add_business_days(last_change, 1):
            asked = at(add_business_days(last_change, 1), r.choice([10, 12, 15]), r.choice([8, 31, 49]))
            if asked.date() < old:
                c.due = [Version(old, c.issued_at),
                         Version(final_due, asked + dt.timedelta(hours=r.randint(1, 4)), "contact",
                                 r.choice(voice["extension_reasons"]))]


def _final_order(seed: int, pack: dict, tz: ZoneInfo, pm: str, k: int, core: bool, with_refund: bool,
                 used: set) -> Order:
    """Draw one order. Like a cycle, it never reads the tier."""
    shop = pack["shop"]
    r = rng(seed, "order", pm, k, "core" if core else "extra", "final")
    y, m = map(int, pm.split("-"))
    day = business_day(dt.date(y, m, r.randint(2, 22)))
    placed = dt.datetime(day.year, day.month, day.day, r.choice([8, 12, 19, 21]), r.choice([4, 17, 38, 51]), tzinfo=tz)
    lines = [(name, r.choice([1, 1, 2, 3]), float(price)) for name, price in r.sample(shop["items"], r.randint(2, 4))]
    total = round(sum(q * price for _, q, price in lines), 2)
    number = 100000 + int(short_hash(seed, "order", pm, k, core, n=8), 16) % 900000
    while number in used:
        number += 1
    used.add(number)
    order = Order(f"{shop['prefix']}-{number}", pm, core, placed, lines, total, 0.0)
    if with_refund:                                 # one unit goes back, less a 15% restocking fee
        name, _, price = r.choice(lines)
        back = add_business_days(day, r.randint(5, 9))
        order.refund = round(price - round(price * 0.15, 2), 2)
        order.refund_at = dt.datetime(back.year, back.month, back.day, r.choice([9, 14]), r.choice([12, 41]), tzinfo=tz)
        order.returned = name
    return order


def build_orders(pack: dict, tier: Tier, seed: int, tz: ZoneInfo, months: list[str], core_months: list[str]) -> list[Order]:
    if "shop" not in pack:
        return []
    used: set = set()
    orders: list[Order] = []
    for m in core_months:                           # core first, so extras never take their numbers
        pm = shift_month(m, 1)
        orders.append(_final_order(seed, pack, tz, pm, 0, True, True, used))
        orders.append(_final_order(seed, pack, tz, pm, 1, True, False, used))
    for m in months:
        pm = shift_month(m, 1)
        for k in range(tier.extra_orders):
            refund = rng(seed, "order", pm, k, "extra", "role").random() < 0.35
            orders.append(_final_order(seed, pack, tz, pm, k, False, refund, used))
    if tier.refund_estimates:                       # history only: the final refund is unchanged
        for o in orders:
            if o.refund:
                price = next(p for name, _, p in o.lines if name == o.returned)
                o.estimate = round(price, 2)
                o.estimate_at = o.refund_at - dt.timedelta(days=2, hours=3)
    return orders


def _ranked(seed: int, cycles: list[Cycle], label: str, share: float) -> set[str]:
    """Pick a share of cycles by a fixed per-cycle priority, so tiers nest."""
    order = sorted(cycles, key=lambda c: rng(seed, c.fid, label).random())
    n = round(share * len(order) + 1e-9)
    return {c.fid for c in order[:n]}


def build_world(pack: dict, tier_level: int, seed: int) -> World:
    tier = TIERS[tier_level]
    tz = ZoneInfo(pack["persona"]["timezone"])
    today = dt.date.fromisoformat(pack["today"])
    core_months = list(pack["core_months"])
    months = [shift_month(core_months[0], -k) for k in range(tier.history_months, 0, -1)] + core_months
    orgs = select_orgs(pack, tier, seed)

    taken: set = set()
    used_numbers: set = set()
    cycles: list[Cycle] = []
    # Core first, in a fixed order, so nothing a higher tier adds can displace them.
    ordered = [(o, m) for o in orgs if o.core for m in core_months]
    ordered += [(o, m) for m in months for o in orgs if not (o.core and m in core_months)]
    # Roles are part of the final truth, so they are fixed before anything is drawn.
    core_pairs = sorted((o.key, m) for o in orgs if o.core for m in core_months)
    r = rng(seed, "roles")
    unpaid = r.choice([p for p in core_pairs if p[1] == core_months[-1]])
    rest = [p for p in core_pairs if p != unpaid]
    r.shuffle(rest)
    role_of = {unpaid: "unpaid"}
    role_of.update(zip(rest, ["docs_late", "pay_late", "pay_late", "pay_short"] + ["normal"] * len(rest)))

    for org, ym in ordered:
        core = org.core and ym in core_months
        if core:
            role = role_of[(org.key, ym)]
        else:
            u = rng(seed, org.key, ym, "role").random()
            role = "pay_late" if u < 0.15 else "pay_short" if u < 0.20 else \
                "unpaid" if (u < 0.27 and ym == months[-1]) else "normal"
        cycles.append(_final_cycle(seed, pack, tz, org, ym, core, role, ym == months[-1], taken, used_numbers))

    core_cycles = [c for c in cycles if c.core]

    resched = _ranked(seed, core_cycles, "resched", tier.reschedule_share)
    correct = _ranked(seed, core_cycles, "correct", tier.correction_share)
    extend = _ranked(seed, [c for c in core_cycles if c.paid_at], "extend", tier.extension_share)
    for c in cycles:
        if c.core:
            _backstory(seed, pack, tz, tier, c, c.fid in resched, c.fid in correct, c.fid in extend)
        else:
            u = rng(seed, c.fid, "extra-backstory")
            _backstory(seed, pack, tz, tier, c,
                       u.random() < tier.reschedule_share * 0.6,
                       u.random() < tier.correction_share * 0.6,
                       c.paid_at is not None and u.random() < tier.extension_share * 0.4)

    start = dt.date(*map(int, shift_month(months[0], 1).split("-")), 1)
    world = World(pack, seed, tier, tz, today, orgs, months, core_months, cycles, start,
                  build_orders(pack, tier, seed, tz, months, core_months))
    _assert_sane(world)
    return world


def _assert_sane(w: World) -> None:
    end = dt.datetime(w.today.year, w.today.month, w.today.day, 23, 59, tzinfo=w.tz)
    for c in w.cycles:
        stamps = [c.request_at, c.docs_at, c.issued_at] + [v.at for v in c.meeting + c.amount + c.due]
        if c.paid_at:
            stamps.append(c.paid_at)
        assert all(s <= end for s in stamps), f"{c.fid} has an event after today"
        assert c.amount[-1].at <= (c.paid_at or end), f"{c.fid} corrected after payment"
        times = [v.value for v in c.meeting]
        assert len(set(times)) == len(times), f"{c.fid} repeats a meeting time"
        assert all(v.at < min(times) for v in c.meeting), f"{c.fid} rescheduled after the meeting"
        assert c.issued_at > c.docs_at, f"{c.fid} invoiced before documents arrived"
        if c.paid_at:
            assert c.due[-1].at < c.paid_at, f"{c.fid} due date changed after payment"
        if c.role != "docs_late":
            assert c.docs_at < c.meeting[-1].value, f"{c.fid} docs after meeting without the role"
    for o in w.orders:
        assert o.placed_at <= end and (o.refund_at or o.placed_at) <= end, f"{o.id} has an event after today"
        assert 0 <= o.refund < o.total, f"{o.id} refunds more than it charged"
        if o.estimate is not None:
            assert o.estimate > o.refund and o.placed_at < o.estimate_at < o.refund_at, f"{o.id} has a bad estimate"
    assert len({o.id for o in w.orders}) == len(w.orders), "two orders share a number"
