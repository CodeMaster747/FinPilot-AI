"""Dashboard aggregate, insights feed, anomalies and the coach."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import Anomaly, ChatMessage, Insight, Job, Transaction, UpcomingPayment
from app.schemas.common import iso, num
from app.schemas.serialize import Lookups, txn_out
from app.services import consent, metrics
from app.services.accounts import account_balances
from app.services.affordability import affordability
from app.services.coach import Coach, suggestions_for
from app.services.forecasting.engine import lowest_point
from app.services.forecasting.service import latest as latest_forecast

router = APIRouter(tags=["dashboard"])


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class StatusBody(BaseModel):
    status: str = Field(pattern="^(open|dismissed|confirmed)$")


ANALYTICS_KINDS = ("user_analytics", "ingest_sample", "ingest_file", "ingest_device", "imap_sync", "bootstrap_demo")


def _analytics_running(db, user_id: int) -> bool:  # noqa: ANN001
    return db.scalar(select(Job.id).where(Job.user_id == user_id, Job.kind.in_(ANALYTICS_KINDS),
                                          Job.status.in_(("queued", "running"))).limit(1)) is not None


def anomalies_grouped(db, user_id: int, status: str = "open", limit: int = 20) -> list[dict[str, Any]]:  # noqa: ANN001
    rows = db.execute(select(Anomaly, Transaction).join(Transaction).where(Anomaly.user_id == user_id, Anomaly.status == status)
                      .order_by(Transaction.txn_date.desc())).all()
    lk = Lookups(db, user_id)
    grouped: dict[int, dict[str, Any]] = {}
    sev_rank = {"high": 3, "medium": 2, "low": 1}
    for a, t in rows:
        g = grouped.setdefault(t.id, {"transaction": txn_out(t, lk), "detectors": [], "explanations": [], "severity": "low", "ids": []})
        g["detectors"].append(a.detector)
        g["explanations"].append(a.explanation)
        g["ids"].append(a.id)
        if sev_rank[a.severity] > sev_rank[g["severity"]]:
            g["severity"] = a.severity
    return list(grouped.values())[:limit]


@router.get("/dashboard")
def dashboard(db: DB, user: CurrentUser) -> dict[str, Any]:
    today = date.today()
    month = metrics.month_summary(db, user.id, today)
    last = metrics.month_summary(db, user.id, metrics.add_months(today.replace(day=1), -1))
    balances = account_balances(db, user.id)
    liquid = sum((b["balance"] for b in balances if b["known"] or b["account"].kind == "credit_card"), Decimal(0))
    balance_known = any(b["known"] and b["account"].kind != "credit_card" for b in balances)
    fc = latest_forecast(db, user.id)
    running = _analytics_running(db, user.id)
    if fc is None and not running:
        # a new account (or one whose analytics never ran): compute them now instead of waiting for the nightly run
        runner.enqueue("user_analytics", user_id=user.id, db=db)
        running = True
    cats = metrics.by_category(metrics.rows(db, user.id, today.replace(day=1), today))
    cat_items = list(cats.items())
    top = [{"category": k, "amount": num(v)} for k, v in cat_items[:7]]
    if len(cat_items) > 7:
        top.append({"category": "Other", "amount": num(sum((v for _, v in cat_items[7:]), Decimal(0)))})
    snap = affordability(db, user) if fc is not None else None
    upcoming: list[dict[str, Any]] = []
    if fc is not None:
        horizon = (today + timedelta(days=14)).isoformat()
        upcoming = [e for e in fc.payload.get("events", []) if e["date"] <= horizon][:10]
    from app.services.wishlist import evaluate as evaluate_wishlist

    wishlist = evaluate_wishlist(db, user, today)["items"][:3] if fc is not None else []
    insights = db.scalars(select(Insight).where(Insight.user_id == user.id, Insight.dismissed.is_(False)).order_by(Insight.severity.desc()).limit(5)).all()
    sources = []
    for kind in consent.KINDS:
        src = consent.get_source(db, user, kind)
        sources.append({"kind": kind, "title": consent.NOTICES[kind]["title"], "status": src.status if src else "not_connected",
                        "last_ingest_at": iso(src.last_ingest_at) if src else None})
    proj = fc.payload["projection"] if fc else []
    low = lowest_point(proj, 30) if proj else (None, None)
    return {
        "preparing": running or fc is None,
        "has_data": db.scalar(select(Transaction.id).where(Transaction.user_id == user.id).limit(1)) is not None,
        "months_of_data": metrics.complete_months(db, user.id, today),
        "kpis": {
            "balance": num(liquid) if balance_known else None,
            "balance_known": balance_known, "income_month": num(month["income"]), "spend_month": num(month["spend"]),
            "spend_last_month": num(last["spend"]), "savings_rate_last_month": last["savings_rate"],
            # balance: from account balances (capped by the wants budget when income is known); wants: no balance yet, so
            # only the monthly wants budget; none: neither a balance nor an income to work from
            "safe_basis": None if snap is None else "balance" if snap.balance_known else "wants" if snap.wants_known else "none",
            "safe_to_spend": num(snap.spendable) if snap and (snap.balance_known or snap.wants_known) else None,
            "safe_to_spend_total": num(snap.safe_to_spend) if snap else None,
            "wants_left": num(snap.wants_left) if snap and snap.wants_known else None, "buffer": num(snap.buffer) if snap else None,
            "net_next_30": fc.payload.get("net_next_30") if fc else None,
            "lowest_30": {"amount": low[0], "date": low[1]} if fc else None,
        },
        "accounts": [{"id": b["account"].id, "name": b["account"].name, "kind": b["account"].kind,
                      "balance": num(b["balance"]) if b["known"] else None, "balance_source": b["source"]} for b in balances],
        "cashflow": [{**m, "income": num(m["income"]), "spend": num(m["spend"]), "invested": num(m["invested"])}
                     for m in metrics.monthly_series(db, user.id, 12, today)],
        "balance": {"history": fc.payload["history"][-90:] if fc else [], "projection": proj[:60]},
        "categories": top,
        "anomalies": anomalies_grouped(db, user.id, limit=4),
        "insights": [{"id": i.id, "kind": i.kind, "severity": i.severity, "title": i.title, "body": i.body, "link": i.link} for i in insights],
        "upcoming": upcoming,
        "wishlist": [{"id": w["id"], "tier": w["tier"], "title": w["text"], "price": w["price"],
                      "reason": w["reasons"][0] if w["reasons"] else ""} for w in wishlist],
        "sources": sources,
        "budgets": [{**b, "budget": num(b["budget"]), "spent": num(b["spent"])} for b in metrics.budgets_status(db, user.id, today)[:4]],
    }


@router.get("/insights")
def list_insights(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Insight).where(Insight.user_id == user.id, Insight.dismissed.is_(False)).order_by(Insight.severity.desc())).all()
    return [{"id": i.id, "kind": i.kind, "severity": i.severity, "title": i.title, "body": i.body, "link": i.link, "data": i.data,
             "created_at": iso(i.created_at)} for i in rows]


@router.post("/insights/{insight_id}/dismiss")
def dismiss_insight(insight_id: int, db: DB, user: CurrentUser) -> dict:
    i = db.get(Insight, insight_id)
    if i is None or i.user_id != user.id:
        raise HTTPException(404, "Insight not found")
    i.dismissed = True
    return {"ok": True}


@router.get("/anomalies")
def list_anomalies(db: DB, user: CurrentUser, status: str = "open") -> list[dict]:
    return anomalies_grouped(db, user.id, status, limit=100)


@router.post("/anomalies/{txn_id}")
def set_anomaly(txn_id: int, body: StatusBody, db: DB, user: CurrentUser) -> dict:
    rows = db.scalars(select(Anomaly).where(Anomaly.user_id == user.id, Anomaly.transaction_id == txn_id)).all()
    if not rows:
        raise HTTPException(404, "Anomaly not found")
    for a in rows:
        a.status = body.status
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True}


@router.get("/coach/suggestions")
def coach_suggestions(db: DB, user: CurrentUser) -> list[str]:
    return suggestions_for(db, user)


@router.get("/coach/history")
def coach_history(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(40)).all()
    return [{"id": m.id, "role": m.role, "text": m.text, "intent": m.intent, "data": m.data, "at": iso(m.created_at)} for m in reversed(rows)]


@router.post("/coach/ask")
def coach_ask(body: AskBody, db: DB, user: CurrentUser) -> dict:
    db.add(ChatMessage(user_id=user.id, role="user", text=body.question.strip()))
    ans = Coach(db, user).ask(body.question)
    data = ans.as_dict()
    msg = ChatMessage(user_id=user.id, role="assistant", text=ans.text, intent=ans.intent,
                      data={k: v for k, v in data.items() if k not in ("text", "intent")})
    db.add(msg)
    db.flush()
    return {"id": msg.id, **data}


@router.delete("/coach/history")
def clear_history(db: DB, user: CurrentUser) -> dict:
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    return {"ok": True}


@router.get("/upcoming")
def upcoming(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(UpcomingPayment).where(UpcomingPayment.user_id == user.id, UpcomingPayment.due_date >= date.today() - timedelta(days=7))
                      .order_by(UpcomingPayment.due_date)).all()
    return [{"id": u.id, "payee": u.payee, "kind": u.kind, "amount": num(u.amount), "due_date": u.due_date.isoformat(), "status": u.status}
            for u in rows]
