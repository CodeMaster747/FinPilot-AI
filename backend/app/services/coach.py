"""Coach & purchase advisor: intent classifier + slot extraction + templated answers built on the same
metric functions as the dashboard. It answers a fixed set of question types — and says so honestly when a
question is outside them. Responses go through a provider interface so a local LLM could replace the
templates later without changing callers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.money import D, fmt_inr
from app.ml import coach_intents, registry
from app.models import Category, DataSource, Product, Subscription, Transaction, User
from app.services import consent, metrics
from app.services.categorization import Categorizer
from app.services.forecasting.engine import lowest_point
from app.services.forecasting.service import latest as latest_forecast
from app.services.picks import affordability, evaluate_price

SUGGESTIONS = [
    "How much did I spend on food delivery last month?",
    "Can I afford a ₹60,000 laptop?",
    "Which subscriptions should I cancel?",
    "What will my balance be at the end of the month?",
    "Am I on track for my laptop goal?",
    "Which tax regime is better for me?",
    "Recommend headphones within my budget",
    "What data can you see?",
]
CATEGORY_WORDS = {
    "dining": "Dining Out", "eating out": "Dining Out", "restaurant": "Dining Out", "restaurants": "Dining Out", "cafe": "Dining Out",
    "food delivery": "Food Delivery", "delivery": "Food Delivery", "takeout": "Food Delivery", "food": "Food Delivery",
    "groceries": "Groceries", "grocery": "Groceries", "shopping": "Shopping", "transport": "Transport", "cab": "Transport",
    "cabs": "Transport", "taxi": "Transport", "commute": "Transport", "fuel": "Fuel", "petrol": "Fuel", "rent": "Rent",
    "subscription": "Subscriptions", "subscriptions": "Subscriptions", "entertainment": "Entertainment", "movies": "Entertainment",
    "travel": "Travel", "electronics": "Electronics", "gadgets": "Electronics", "fashion": "Fashion", "clothes": "Fashion",
    "utilities": "Utilities", "electricity": "Utilities", "bills": "Utilities", "health": "Healthcare", "medicine": "Healthcare",
    "fitness": "Sports & Fitness", "gym": "Sports & Fitness", "emi": "Loan EMI", "loan": "Loan EMI", "insurance": "Insurance",
    "personal care": "Personal Care", "salon": "Personal Care", "education": "Education", "phone": "Phone & Internet",
    "internet": "Phone & Internet",
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
STOP = set("a an the for my me i can could should afford buy under within below around about is it ok okay to spend on of with "
           "budget cheap best good find show suggest recommend what which do have enough money any deals that fits fit rs inr "
           "under lakh k thousand please some a".split())


class ResponseProvider(Protocol):
    def render(self, intent: str, facts: dict[str, Any]) -> str: ...


class TemplateProvider:
    """Default provider: deterministic templates. A local LLM provider could implement the same protocol."""

    def render(self, intent: str, facts: dict[str, Any]) -> str:
        return facts.get("text", "")


provider: ResponseProvider = TemplateProvider()


@dataclass
class Answer:
    text: str
    intent: str
    confidence: float
    chart: dict[str, Any] | None = None
    table: list[dict[str, Any]] | None = None
    links: list[dict[str, str]] = field(default_factory=list)
    slots: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "intent": self.intent, "confidence": round(self.confidence, 2), "chart": self.chart,
                "table": self.table, "links": self.links, "slots": self.slots}


# -- slots ------------------------------------------------------------------------------------------
def parse_period(text: str, today: date) -> tuple[date, date, str]:
    t = text.lower()
    m0 = today.replace(day=1)
    if "last month" in t or "previous month" in t:
        s = metrics.add_months(m0, -1)
        return s, m0 - timedelta(days=1), f"{s:%B %Y}"
    m = re.search(r"last (\d+|two|three|six|twelve) months", t)
    if m:
        n = {"two": 2, "three": 3, "six": 6, "twelve": 12}.get(m.group(1)) or int(m.group(1))
        return metrics.add_months(m0, -n), m0 - timedelta(days=1), f"the last {n} months"
    if "this year" in t or "year to date" in t:
        return date(today.year, 1, 1), today, f"{today.year} so far"
    if "last year" in t:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), f"{today.year - 1}"
    if "last week" in t:
        start = today - timedelta(days=today.weekday() + 7)
        return start, start + timedelta(days=6), "last week"
    if "this week" in t:
        return today - timedelta(days=today.weekday()), today, "this week"
    if "yesterday" in t:
        d = today - timedelta(days=1)
        return d, d, "yesterday"
    if "today" in t:
        return today, today, "today"
    m = re.search(r"since (" + "|".join(MONTHS) + ")", t)
    if m:
        mi = MONTHS.index(m.group(1)) + 1
        y = today.year if mi <= today.month else today.year - 1
        return date(y, mi, 1), today, f"since {m.group(1).title()}"
    for i, name in enumerate(MONTHS, 1):
        short = name[:3] if name != "may" else name  # "may I buy…" is not the month of May
        if re.search(rf"\bin {name}\b|\b{name}\b|\b{short}\b", t) and not (name == "may" and re.search(r"\bmay i\b", t)):
            y = today.year if i <= today.month else today.year - 1
            s = date(y, i, 1)
            return s, metrics.add_months(s, 1) - timedelta(days=1), f"{s:%B %Y}"
    return m0, today, "this month"


def parse_amount(text: str) -> Decimal | None:
    t = text.lower().replace(",", "")
    best = None
    for m in re.finditer(r"(?:₹|rs\.?\s*|inr\s*)?(\d+(?:\.\d+)?)\s*(k\b|thousand|lakhs?|l\b|cr\b|crore)?", t):
        value = Decimal(m.group(1))
        unit = m.group(2) or ""
        if unit in ("k", "thousand"):
            value *= 1000
        elif unit.startswith("lakh") or unit == "l":
            value *= 100000
        elif unit in ("cr", "crore"):
            value *= 10000000
        elif value < 100 and "₹" not in m.group(0) and "rs" not in m.group(0):
            continue  # "last 3 months", "5 transactions"
        if 1900 <= value <= 2100 and not unit and "₹" not in m.group(0):
            continue  # a year
        best = value if best is None else max(best, value)
    return best


def parse_category(text: str) -> str | None:
    t = f" {text.lower()} "
    for word in sorted(CATEGORY_WORDS, key=len, reverse=True):
        if f" {word} " in t or f" {word}?" in t:
            return CATEGORY_WORDS[word]
    return None


def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z\-]+", text.lower())
    return [w for w in words if w not in STOP and len(w) > 2]


# -- answers ----------------------------------------------------------------------------------------
class Coach:
    def __init__(self, db: Session, user: User, today: date | None = None):
        self.db, self.user, self.today = db, user, today or date.today()
        self.cat = Categorizer(db, user.id)

    def ask(self, question: str) -> Answer:
        q = question.strip()
        intent, p = coach_intents.predict(registry.load("coach_intents"), q)
        if p < 0.35 or intent == "out_of_scope":
            return self.fallback(q, p)
        handler = getattr(self, intent, None)
        if handler is None:
            return self.fallback(q, p)
        ans = handler(q)
        ans.intent, ans.confidence = intent, p
        ans.text = provider.render(intent, {"text": ans.text})
        return ans

    def fallback(self, q: str, p: float) -> Answer:
        return Answer("I can answer questions about your own money — spending by category or period, comparisons, your balance "
                      "forecast, subscriptions, tax, goals, finding transactions, whether you can afford something, product picks "
                      "and what data I can see. Try one of the suggestions below.", "fallback", p,
                      links=[{"label": s, "ask": s} for s in SUGGESTIONS[:4]])

    def _rows(self, start: date, end: date) -> list[metrics.Row]:
        return metrics.rows(self.db, self.user.id, start, end)

    def spend_by_category(self, q: str) -> Answer:
        start, end, label = parse_period(q, self.today)
        cat = parse_category(q)
        merchant = self.cat.match_alias(q)
        rs = self._rows(start, end)
        if merchant and not cat:
            sel = [r for r in rs if r.merchant == merchant.name and r.amount < 0]
            total = -sum((r.amount for r in sel), Decimal(0))
            return Answer(f"You spent {fmt_inr(total)} at {merchant.name} in {label} across {len(sel)} payment(s).", "", 0,
                          slots={"merchant": merchant.name, "period": label})
        if cat:
            sel = [r for r in rs if r.category == cat and r.kind == "expense"]
            total = -sum((r.amount for r in sel), Decimal(0))
            by_m: dict[str, Decimal] = {}
            for r in sel:
                by_m[r.merchant] = by_m.get(r.merchant, Decimal(0)) - r.amount
            top = sorted(by_m.items(), key=lambda kv: -kv[1])[:5]
            text = f"You spent {fmt_inr(total)} on {cat.lower()} in {label} ({len([r for r in sel if r.amount < 0])} payments)."
            if top:
                text += f" Most of it went to {top[0][0]} ({fmt_inr(top[0][1])})."
            return Answer(text, "", 0, chart={"type": "bar", "title": f"{cat} by merchant — {label}",
                                               "data": [{"label": k, "value": float(v)} for k, v in top]},
                          slots={"category": cat, "period": label}, links=[{"label": "See transactions", "href": "/transactions"}])
        cats = metrics.by_category(rs)
        total = sum(cats.values(), Decimal(0))
        top = list(cats.items())[:6]
        text = f"In {label} you spent {fmt_inr(total)} in total."
        if top:
            text += " Biggest: " + ", ".join(f"{k} {fmt_inr(v)}" for k, v in top[:3]) + "."
        return Answer(text, "", 0, chart={"type": "bar", "title": f"Spending by category — {label}",
                                           "data": [{"label": k, "value": float(v)} for k, v in top]}, slots={"period": label})

    def compare_periods(self, q: str) -> Answer:
        cat = parse_category(q)
        m0 = self.today.replace(day=1)
        prev = metrics.add_months(m0, -1)
        prev_end = min(prev + timedelta(days=self.today.day - 1), m0 - timedelta(days=1))

        def total(s: date, e: date) -> Decimal:
            rs = self._rows(s, e)
            return -sum((r.amount for r in rs if r.kind == "expense" and (cat is None or r.category == cat)), Decimal(0))

        cur, last = total(m0, self.today), total(prev, prev_end)
        what = cat.lower() if cat else "spending"
        if last:
            pct = float((cur - last) / last * 100)
            direction = "more" if pct > 0 else "less"
            text = (f"So far this month your {what} is {fmt_inr(cur)}, {abs(pct):.0f}% {direction} than the same days of "
                    f"last month ({fmt_inr(last)}).")
        else:
            text = f"So far this month your {what} is {fmt_inr(cur)}; there's nothing to compare with last month."
        return Answer(text, "", 0, chart={"type": "bar", "title": f"{(cat or 'Total spending')}: first {self.today.day} days",
                                           "data": [{"label": f"{prev:%b}", "value": float(last)}, {"label": f"{m0:%b}", "value": float(cur)}]},
                      slots={"category": cat})

    def forecast_query(self, q: str) -> Answer:
        fc = latest_forecast(self.db, self.user.id)
        if fc is None:
            return Answer("Your forecast is still being computed — ask again in a minute.", "", 0)
        p = fc.payload
        proj = p["projection"]
        month_end = (metrics.add_months(self.today.replace(day=1), 1) - timedelta(days=1)).isoformat()
        at = next((x for x in proj if x["date"] >= month_end), proj[-1])
        low, low_date = lowest_point(proj, 60)
        text = (f"Your balance today is about {fmt_inr(D(p['balance_now']))}. By {date.fromisoformat(at['date']):%d %b} it's projected at "
                f"{fmt_inr(D(at['p50']))} (likely between {fmt_inr(D(at['p10']))} and {fmt_inr(D(at['p90']))}). "
                f"The lowest point in the next 60 days is around {fmt_inr(D(low))} on {date.fromisoformat(low_date):%d %b}.")
        return Answer(text, "", 0, chart={"type": "line", "title": "Projected balance (60 days)",
                                           "data": [{"label": x["date"][5:], "value": x["p50"], "low": x["p10"], "high": x["p90"]} for x in proj[:60]]},
                      links=[{"label": "Open forecast", "href": "/forecast"}])

    def savings_advice(self, q: str) -> Answer:
        ideas: list[tuple[float, str]] = []
        for s in self.db.scalars(select(Subscription).where(Subscription.user_id == self.user.id, Subscription.user_action.is_(None))).all():
            for f in s.findings:
                if f["type"] in ("dormant", "trial_converted", "overlap"):
                    ideas.append((f["saving"], f"{s.merchant_name}: {f['detail']} (up to {fmt_inr(D(f['saving']))}/year)"))
                    break
        for st in metrics.budgets_status(self.db, self.user.id, self.today):
            if st["over_pace"]:
                ideas.append((float(st["spent"]) * 0.2 * 12, f"{st['category']} is ahead of budget ({st['pct']:.0f}% used) — trimming it by a fifth saves about {fmt_inr(st['spent'] * Decimal('0.2'))} a month."))
        rs = self._rows(metrics.add_months(self.today.replace(day=1), -3), self.today.replace(day=1) - timedelta(days=1))
        delivery = -sum((r.amount for r in rs if r.category == "Food Delivery"), Decimal(0)) / 3
        if delivery > 3000:
            ideas.append((float(delivery) * 0.3 * 12, f"Food delivery averages {fmt_inr(delivery)}/month — cooking two more meals a week could save ~{fmt_inr(delivery * Decimal('0.3'))}/month."))
        ideas.sort(key=lambda x: -x[0])
        if not ideas:
            return Answer("You're already doing well — no obvious leaks right now. Keep your SIPs going.", "", 0)
        text = "Here's where you could save the most:\n" + "\n".join(f"• {t}" for _, t in ideas[:4])
        return Answer(text, "", 0, links=[{"label": "Subscriptions", "href": "/subscriptions"}, {"label": "Budgets", "href": "/budgets"}])

    def subscription_query(self, q: str) -> Answer:
        subs = self.db.scalars(select(Subscription).where(Subscription.user_id == self.user.id).order_by(Subscription.annual_cost.desc())).all()
        if not subs:
            return Answer("I haven't found any recurring subscriptions yet.", "", 0)
        active = [s for s in subs if s.status in ("active", "dormant")]
        total = sum((s.annual_cost for s in active), Decimal(0))
        flagged = [s for s in active if s.findings]
        text = f"You have {len(active)} active subscriptions costing about {fmt_inr(total / 12)}/month ({fmt_inr(total)} a year)."
        if flagged:
            text += " Worth a look: " + "; ".join(f"{s.merchant_name} — {s.findings[0]['title'].lower()}" for s in flagged[:3]) + "."
        return Answer(text, "", 0, table=[{"name": s.merchant_name, "cadence": s.cadence, "amount": float(s.amount),
                                            "status": s.status, "flag": s.findings[0]["title"] if s.findings else ""} for s in active],
                      links=[{"label": "Open subscriptions", "href": "/subscriptions"}])

    def tax_query(self, q: str) -> Answer:
        from app.services.tax import tax_summary

        year = "2025-26" if "2025" in q or "last year" in q.lower() else "2026-27"
        s = tax_summary(self.db, self.user, year)
        old, new = s["regimes"]["old"]["total"], s["regimes"]["new"]["total"]
        text = (f"For {s['label']}, estimated tax is {fmt_inr(D(new))} under the new regime and {fmt_inr(D(old))} under the old one — "
                f"{s['recommendation']['text']} " + (
                    f"Your 80C limit of {fmt_inr(D(s['section_80c']['limit']))} is fully used ({fmt_inr(D(s['section_80c']['total']))} invested)."
                    if s['section_80c']['total'] >= s['section_80c']['limit'] else
                    f"You've used {fmt_inr(D(s['section_80c']['total']))} of the {fmt_inr(D(s['section_80c']['limit']))} 80C limit.")
                + " (Estimates for planning, not tax advice.)")
        return Answer(text, "", 0, chart={"type": "bar", "title": f"Tax estimate — {s['label']}",
                                           "data": [{"label": "Old regime", "value": old}, {"label": "New regime", "value": new}]},
                      links=[{"label": "Open tax", "href": "/tax"}])

    def goal_query(self, q: str) -> Answer:
        goals = metrics.goals_status(self.db, self.user.id, self.today)
        if not goals:
            return Answer("You don't have any active goals yet — add one on the Budgets & goals page.", "", 0,
                          links=[{"label": "Add a goal", "href": "/budgets"}])
        words = set(keywords(q))
        chosen = [g for g in goals if words & set(g["name"].lower().split())] or goals
        parts = []
        for g in chosen[:3]:
            parts.append(f"“{g['name']}”: {fmt_inr(g['saved'])} of {fmt_inr(g['target'])} ({g['pct']:.0f}%). "
                         f"Save {fmt_inr(g['monthly_needed'])}/month to finish by {g['target_date']:%b %Y}.")
        return Answer(" ".join(parts), "", 0, chart={"type": "progress", "title": "Goals",
                                                      "data": [{"label": g["name"], "value": g["pct"]} for g in chosen[:4]]},
                      links=[{"label": "Budgets & goals", "href": "/budgets"}])

    def transaction_search(self, q: str) -> Answer:
        start, end, label = parse_period(q, self.today)
        explicit_period = label != "this month" or "this month" in q.lower()
        merchant = self.cat.match_alias(q)
        cat = parse_category(q)
        amount = parse_amount(q)
        stmt = select(Transaction).where(Transaction.user_id == self.user.id, Transaction.is_transfer.is_(False))
        desc = []
        if merchant:
            stmt = stmt.where(Transaction.merchant_name == merchant.name)
            desc.append(merchant.name)
        elif cat:
            cid = self.cat.by_name[cat].id
            stmt = stmt.where(Transaction.category_id == cid)
            desc.append(cat)
        if amount and "above" in q.lower() or amount and "over" in q.lower():
            stmt = stmt.where(Transaction.amount >= amount)
            desc.append(f"above {fmt_inr(amount)}")
        if explicit_period:
            stmt = stmt.where(Transaction.txn_date >= start, Transaction.txn_date <= end)
            desc.append(label)
        rows = self.db.scalars(stmt.order_by(Transaction.txn_date.desc(), Transaction.id.desc()).limit(8)).all()
        if not rows:
            return Answer("I couldn't find matching transactions.", "", 0)
        what = " · ".join(desc) or "your latest transactions"
        text = f"Here are the most recent matches for {what}. The latest was {fmt_inr(rows[0].amount)} on {rows[0].txn_date:%d %b %Y}."
        return Answer(text, "", 0, table=[{"date": t.txn_date.isoformat(), "merchant": t.merchant_name, "amount": float(t.amount),
                                            "direction": t.direction} for t in rows],
                      links=[{"label": "Open transactions", "href": "/transactions"}])

    def _find_products(self, q: str, limit: int = 5) -> list[Product]:
        words = keywords(q)
        if not words:
            return []
        conds = [Product.title.ilike(f"%{w}%") for w in words if len(w) > 3]
        if not conds:
            return []
        return list(self.db.scalars(select(Product).where(Product.stale.is_(False), or_(*conds)).order_by(Product.rating.desc()).limit(40)).all())[:limit * 4]

    def affordability_check(self, q: str) -> Answer:
        snap = affordability(self.db, self.user, self.today, for_picks=False)
        fc = latest_forecast(self.db, self.user.id)
        proj = fc.payload["projection"] if fc else None
        amount = parse_amount(q)
        product = None
        if amount is None:
            prods = self._find_products(q, 1)
            product = prods[0] if prods else None
            amount = product.price if product else None
        if amount is None:
            return Answer(f"Tell me a price and I'll check it — right now you can safely spend about {fmt_inr(min(snap.safe_to_spend, snap.wants_left))} "
                          "this month without touching bills, goals or your safety buffer.", "", 0)
        v = evaluate_price(amount, snap, proj)
        what = product.title if product else f"something for {fmt_inr(amount)}"
        if v["tier"] == "buy_now":
            text = f"Yes — {what} fits. It's within your safe-to-spend ({fmt_inr(snap.safe_to_spend)}) and this month's wants budget ({fmt_inr(snap.wants_left)} left)."
        elif v["tier"] == "save_up":
            text = (f"Not today without stretching. If you save {fmt_inr(D(v['monthly']))}/month for {v['months']} month(s), you can buy "
                    f"{what} without touching your {fmt_inr(snap.buffer)} buffer or your goals.")
        else:
            text = f"I'd hold off on {what} — it would cut into money set aside for bills, goals or your safety buffer."
        if v["impact"]:
            imp = v["impact"]
            text += f" Your lowest projected balance would be {fmt_inr(D(imp['lowest_after']))} (vs {fmt_inr(D(imp['lowest_before']))})."
        return Answer(text, "", 0, slots={"amount": float(amount), "tier": v["tier"]},
                      chart={"type": "line", "title": "Projected balance if you buy it today",
                             "data": [{"label": x["date"][5:], "value": x["p50"] - float(amount), "low": x["p10"] - float(amount),
                                       "high": x["p90"] - float(amount)} for x in proj[:60]]} if proj else None,
                      links=[{"label": "Open Smart Picks", "href": "/picks"}])

    def recommendation_query(self, q: str) -> Answer:
        snap = affordability(self.db, self.user, self.today, for_picks=False)
        fc = latest_forecast(self.db, self.user.id)
        proj = fc.payload["projection"] if fc else None
        cap = parse_amount(q)
        prods = self._find_products(q, 8)
        if not prods:
            return Answer("Your Smart Picks page has products matched to your wishlist, goals and regular purchases — each checked "
                          "against your budget.", "", 0, links=[{"label": "Open Smart Picks", "href": "/picks"}])
        rows = []
        for p in prods:
            if cap and p.price > cap:
                continue
            v = evaluate_price(p.price, snap, proj)
            if v["tier"] == "not_now":
                continue
            rows.append((0 if v["tier"] == "buy_now" else 1, -p.rating, p, v))
        rows.sort(key=lambda x: (x[0], x[1]))
        if not rows:
            return Answer("Nothing in the stores fits that budget right now without touching your buffer.", "", 0)
        top = rows[:3]

        def verdict(v: dict) -> str:
            return "buy now" if v["tier"] == "buy_now" else "save for {} month(s)".format(v["months"])

        text = "Here's what fits: " + "; ".join(f"{p.title} at {fmt_inr(p.price)} ({verdict(v)})" for _, _, p, v in top) + "."
        return Answer(text, "", 0, table=[{"product": p.title, "price": float(p.price), "rating": p.rating,
                                            "verdict": "Buy now" if v["tier"] == "buy_now" else f"Save {v['months']} mo"} for _, _, p, v in top],
                      links=[{"label": "Open Smart Picks", "href": "/picks"}])

    def privacy_query(self, q: str) -> Answer:
        parts = []
        for kind in consent.KINDS:
            src = self.db.scalar(select(DataSource).where(DataSource.user_id == self.user.id, DataSource.kind == kind))
            title = consent.NOTICES[kind]["title"]
            if src is None:
                parts.append(f"{title}: not connected")
            else:
                uses = " and Smart Picks" if "picks" in (src.purposes or []) else ""
                parts.append(f"{title}: {src.status} — used for transactions{uses}")
        text = ("I only read sources you've explicitly connected. " + "; ".join(parts) + ". Personal chats, OTPs, promotional "
                "messages and non-financial email are never stored. Original message text is encrypted and deleted after "
                f"{(self.user.preferences or {}).get('retention_days', 90)} days; you can pause, revoke or delete each source's data any time.")
        return Answer(text, "", 0, links=[{"label": "Manage connections", "href": "/connections"}])

    def summary_query(self, q: str) -> Answer:
        start, end, label = parse_period(q, self.today)
        rs = self._rows(start, end)
        inc, out, inv = metrics.income(rs), metrics.spend(rs), metrics.savings(rs)
        rate = float((inc - out) / inc * 100) if inc else 0.0
        cats = metrics.by_category(rs)
        top = next(iter(cats.items()), None)
        snap = affordability(self.db, self.user, self.today, for_picks=False)
        when = "So far this month" if label == "this month" else f"In {label}"
        if inc:
            text = f"{when}: income {fmt_inr(inc)}, spending {fmt_inr(out)}, invested {fmt_inr(inv)} — you kept {rate:.0f}% of your income."
        else:
            text = f"{when}: spending {fmt_inr(out)} and {fmt_inr(inv)} invested; no income has been credited yet in this period."
        text += ((f" Your biggest category was {top[0]} ({fmt_inr(top[1])})." if top else "")
                + f" Safe to spend right now: {fmt_inr(min(snap.safe_to_spend, snap.wants_left))}.")
        return Answer(text, "", 0, chart={"type": "bar", "title": label,
                                           "data": [{"label": "Income", "value": float(inc)}, {"label": "Spending", "value": float(out)},
                                                    {"label": "Invested", "value": float(inv)}]})


def categories_for(db: Session) -> list[str]:
    return [c.name for c in db.scalars(select(Category).where(Category.kind == "expense")).all()]
