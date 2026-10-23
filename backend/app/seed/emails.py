"""Render persona truth into raw emails (HTML + text) with truth labels."""

from __future__ import annotations

import html
import json
import random
import re
from datetime import timedelta
from decimal import Decimal

from app.seed.persona import Notice, Persona, TruthTxn
from app.seed.sms import inr
from app.services.ingestion.html import html_to_text  # noqa: F401  (re-exported for the renderers)
from app.services.ingestion.types import RawMessage

USER_EMAIL = "aarav.sharma@example.com"


def _doc(title: str, inner: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + html.escape(title) + "</title></head>"
        "<body style='font-family:Arial,sans-serif;color:#222'>" + inner + "</body></html>"
    )


def _items_table(items: list[tuple[str, int, Decimal]], money_prefix: str = "₹") -> str:
    rows = "".join(
        f"<tr><td class='item'>{html.escape(name)}</td><td class='qty'>{qty}</td>"
        f"<td class='price'>{money_prefix}{inr(price * qty)}</td></tr>"
        for name, qty, price in items
    )
    return f"<table class='items' cellpadding='4'><tr><th>Item</th><th>Qty</th><th>Price</th></tr>{rows}</table>"


class EmailRenderer:
    def __init__(self, persona: Persona, seed: int = 23):
        self.p = persona
        self.rng = random.Random(seed + persona.end.toordinal())
        self.masks = {a.key: a.mask for a in persona.accounts}

    def msg(self, sender: str, ts, subject: str, markup: str, kind: str, template: str, txn: TruthTxn | None = None,
            expect: dict | None = None) -> RawMessage:
        truth = {"kind": kind, "template": template, "txn_id": txn.id if txn else None, "expect": expect or {}}
        return RawMessage(channel="email", sender=sender, received_at=ts, subject=subject, html=markup,
                          body=html_to_text(markup), truth=truth)

    def paid_with(self, t: TruthTxn) -> str:
        return f"ICICI Bank Credit Card ending {self.masks['icici']}" if t.account == "icici" else "UPI"

    # -- transactions ----------------------------------------------------------------------------
    def txn_emails(self, t: TruthTxn) -> list[RawMessage]:
        out: list[RawMessage] = []
        r = self.rng
        delay = timedelta(minutes=r.randint(1, 25))
        exp = {"amount": str(t.amount), "merchant": t.merchant}
        if t.bank_email and t.account == "icici" and t.direction == "debit":
            inner = (f"<p>Dear Customer,</p><p>Your ICICI Bank Credit Card XX{self.masks['icici']} has been used for a transaction "
                     f"of <b>INR {inr(t.amount)}</b> on {t.ts:%b %d, %Y} at {t.ts:%H:%M:%S}. Info: {html.escape(t.payee)}.</p>"
                     f"<p>The Available Credit Limit on your card is INR {inr(t.balance_after or Decimal(0))}.</p>"
                     "<p>If you have not done this transaction, please call our Customer Care immediately.</p>")
            out.append(self.msg("ICICI Bank <credit_cards@icicibank.com>", t.ts + timedelta(seconds=r.randint(30, 300)),
                                "Transaction alert for your ICICI Bank Credit Card", _doc("Transaction alert", inner),
                                "transaction", "icici_alert_email", t, {**exp, "direction": "debit", "mask": self.masks["icici"]}))
        if t.account == "hdfc" and t.channel == "upi" and t.direction == "debit" and t.amount >= 5000:
            inner = (f"<p>Dear Customer,</p><p>Rs.{inr(t.amount)} has been debited from account **{self.masks['hdfc']} to VPA "
                     f"{html.escape(t.vpa or '')} {html.escape(t.payee)} on {t.ts:%d-%m-%y}.</p>"
                     f"<p>Your UPI transaction reference number is {t.ref}.</p><p>Warm Regards,<br>HDFC Bank</p>")
            out.append(self.msg("HDFC Bank InstaAlerts <alerts@hdfcbank.net>", t.ts + timedelta(seconds=r.randint(30, 240)),
                                "You have done a UPI txn. Check details!", _doc("UPI alert", inner), "transaction",
                                "hdfc_alert_email", t, {**exp, "direction": "debit", "mask": self.masks["hdfc"], "ref": t.ref}))
        key = t.merchant_email
        if key == "swiggy":
            inner = (f"<h2>Your order from {html.escape(t.restaurant or '')} has been delivered</h2>"
                     f"<p>Order No: <b>{t.order_id}</b></p>{_items_table(t.items or [])}"
                     f"<p class='total'><b>Order Total: ₹{inr(t.amount)}</b></p><p>Paid via {self.paid_with(t)}</p>")
            out.append(self.msg("Swiggy <noreply@swiggy.in>", t.ts + delay + timedelta(minutes=35),
                                f"Your Swiggy order from {t.restaurant} was delivered successfully", _doc("Swiggy order", inner),
                                "order_receipt", "swiggy_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        elif key == "zomato":
            inner = (f"<p>Thank you for ordering from <b>{html.escape(t.restaurant or '')}</b></p><p>Order ID: {t.order_id}</p>"
                     f"{_items_table(t.items or [])}<p><b>Total paid ₹{inr(t.amount)}</b></p><p>Payment mode: {self.paid_with(t)}</p>")
            out.append(self.msg("Zomato <noreply@zomato.com>", t.ts + delay + timedelta(minutes=30),
                                f"Your Zomato order from {t.restaurant}", _doc("Zomato order", inner), "order_receipt",
                                "zomato_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        elif key == "amazon":
            ld = {
                "@context": "http://schema.org", "@type": "Order", "merchant": {"@type": "Organization", "name": "Amazon.in"},
                "orderNumber": t.order_id, "priceCurrency": "INR", "price": f"{t.amount:.2f}",
                "acceptedOffer": [
                    {"@type": "Offer", "itemOffered": {"@type": "Product", "name": name}, "price": f"{price:.2f}",
                     "priceCurrency": "INR", "eligibleQuantity": {"@type": "QuantitativeValue", "value": qty}}
                    for name, qty, price in (t.items or [])
                ],
            }
            inner = (f"<script type='application/ld+json'>{json.dumps(ld)}</script>"
                     f"<p>Hello Aarav,</p><p>Thank you for your order. We'll send a confirmation when your item(s) ship.</p>"
                     f"<p>Order #{t.order_id}</p>{_items_table(t.items or [])}<p><b>Order Total: ₹{inr(t.amount)}</b></p>")
            n = sum(q for _, q, _ in (t.items or []))
            out.append(self.msg("Amazon.in <auto-confirm@amazon.in>", t.ts + timedelta(minutes=r.randint(1, 4)),
                                f"Your Amazon.in order #{t.order_id} of {n} item{'s' if n != 1 else ''}", _doc("Amazon order", inner),
                                "order_receipt", "amazon_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        elif key == "amazon_refund":
            inner = (f"<p>Hello Aarav,</p><p>We've processed your refund of <b>₹{inr(t.amount)}</b> for order #{t.order_id}.</p>"
                     f"<p>The amount will be credited to your ICICI Bank Credit Card ending {self.masks['icici']} within 2-4 business days.</p>")
            out.append(self.msg("Amazon.in <return@amazon.in>", t.ts - timedelta(hours=r.randint(2, 20)),
                                f"Refund processed for your Amazon.in order #{t.order_id}", _doc("Refund", inner), "refund",
                                "amazon_refund", t, {**exp, "order_id": t.order_id}))
        elif key == "bigbasket":
            inner = (f"<p>Hi Aarav, your bigbasket order <b>{t.order_id}</b> has been delivered.</p>"
                     f"{_items_table(t.items or [], 'Rs.')}<p><b>Total Paid: Rs.{inr(t.amount)}</b></p>"
                     f"<p>Payment: {self.paid_with(t)}</p>")
            out.append(self.msg("bigbasket <no-reply@bigbasket.com>", t.ts + timedelta(hours=r.randint(2, 6)),
                                f"Your bigbasket order {t.order_id} has been delivered", _doc("bigbasket", inner), "order_receipt",
                                "bigbasket_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        elif key == "uber":
            part = "morning" if t.ts.hour < 12 else "afternoon" if t.ts.hour < 17 else "evening"
            inner = (f"<h2>Thanks for riding, Aarav</h2><p>We hope you enjoyed your ride this {part}.</p>"
                     f"<p class='total'><b>Total ₹{inr(t.amount)}</b></p><p>Trip fare and taxes included. Paid via UPI.</p>"
                     f"<p>{t.ts:%d %B %Y, %I:%M %p}</p>")
            out.append(self.msg("Uber Receipts <noreply@uber.com>", t.ts + timedelta(minutes=r.randint(10, 50)),
                                f"Your {t.ts:%A} {part} trip with Uber", _doc("Uber receipt", inner), "order_receipt",
                                "uber_receipt", t, exp))
        elif key == "flipkart":
            inner = (f"<p>Hi Aarav, your order has been placed.</p><p>Order ID {t.order_id}</p>{_items_table(t.items or [])}"
                     f"<p><b>Amount Paid ₹{inr(t.amount)}</b></p>")
            out.append(self.msg("Flipkart <noreply@flipkart.com>", t.ts + timedelta(minutes=r.randint(1, 5)),
                                "Your Flipkart order has been placed", _doc("Flipkart order", inner), "order_receipt",
                                "flipkart_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        elif key == "myntra":
            inner = (f"<p>Hi Aarav, thank you for shopping with Myntra!</p><p>Order No {t.order_id}</p>"
                     f"{_items_table(t.items or [])}<p><b>Total Amount ₹{inr(t.amount)}</b></p>")
            out.append(self.msg("Myntra <updates@myntra.com>", t.ts + timedelta(minutes=r.randint(1, 5)),
                                "Your Myntra order has been confirmed", _doc("Myntra order", inner), "order_receipt",
                                "myntra_order", t, {**exp, "order_id": t.order_id, "items": len(t.items or [])}))
        return out

    # -- notices ---------------------------------------------------------------------------------
    PROMO = [
        ("Swiggy <offers@swiggy.in>", "Flat ₹125 OFF on your next 3 orders 🍕",
         "<p>Hungry? Get flat ₹125 off on your next 3 orders above ₹299. Use code HUNGRY125. Valid till Sunday.</p>"),
        ("Amazon.in <store-news@amazon.in>", "Great Indian Festival: deals up to 80% off",
         "<p>Up to 80% off on electronics, up to ₹10,000 instant discount with select cards. Shop now before deals end!</p>"),
        ("Myntra <offers@myntra.com>", "Your cart misses you! Extra ₹200 off inside",
         "<p>Complete your purchase in the next 24 hours and get an extra ₹200 off on orders above ₹1,499.</p>"),
        ("Netflix <info@mailer.netflix.com>", "New on Netflix this week",
         "<p>Catch the biggest new releases this week. Plans start at ₹149/month.</p>"),
    ]
    NEWSLETTERS = [
        ("Medium Daily Digest <noreply@medium.com>", "Stories for Aarav", "<p>Today's highlights: 10 VS Code tips you didn't know.</p>"),
        ("LinkedIn <messages-noreply@linkedin.com>", "You appeared in 12 searches this week", "<p>See who's viewing your profile.</p>"),
        ("Priya <priya.k@example.com>", "Trip photos!", "<p>Uploaded the Pondicherry photos to the shared album.</p>"),
        ("GitHub <noreply@github.com>", "[GitHub] A new SSH key was added", "<p>A new public key was added to your account.</p>"),
    ]

    def notice_emails(self, n: Notice) -> list[RawMessage]:
        r, d = self.rng, n.data
        if n.kind == "card_statement":
            inner = (f"<p>Dear Customer,</p><p>Your ICICI Bank Credit Card XX{self.masks['icici']} statement for the period "
                     f"{d['period_start']:%d %b %Y} to {d['period_end']:%d %b %Y} is ready.</p>"
                     f"<table><tr><td>Total Amount Due</td><td>₹{inr(d['total'])}</td></tr>"
                     f"<tr><td>Minimum Amount Due</td><td>₹{inr(d['minimum'])}</td></tr>"
                     f"<tr><td>Payment Due Date</td><td>{d['due']:%d %b %Y}</td></tr></table>")
            return [self.msg("ICICI Bank <cc_statements@icicibank.com>", n.ts + timedelta(hours=1),
                             f"Your ICICI Bank Credit Card XX{self.masks['icici']} statement for {d['period_end']:%B %Y}",
                             _doc("Statement", inner), "statement", "icici_statement_email",
                             expect={"amount": str(d["total"]), "due": d["due"].isoformat()})]
        if n.kind == "bill_due" and d["biller"] in ("Airtel", "ACT Fibernet"):
            if d["biller"] == "Airtel":
                inner = (f"<p>Dear Customer, your Airtel Postpaid bill for {n.ts:%B %Y} is ready.</p><p>Amount due: <b>₹{inr(d['amount'])}</b></p>"
                         f"<p>Due date: {d['due']:%d %b %Y}</p><p>Mobile number: {d['account_no']}</p>")
                sender, subject = "Airtel <ebill@airtel.com>", f"Your Airtel Postpaid bill for {n.ts:%B %Y}"
            else:
                inner = (f"<p>Dear Subscriber, your ACT Fibernet invoice for {n.ts:%B %Y} has been generated.</p>"
                         f"<p>Invoice amount: <b>₹{inr(d['amount'])}</b></p><p>Due date: {d['due']:%d %b %Y}</p>")
                sender, subject = "ACT Fibernet <billing@actcorp.in>", f"ACT Fibernet invoice for {n.ts:%B %Y}"
            return [self.msg(sender, n.ts + timedelta(minutes=r.randint(5, 90)), subject, _doc("Bill", inner), "bill_due",
                             "bill_email", expect={"amount": str(d["amount"]), "due": d["due"].isoformat(), "payee": d["biller"]})]
        if n.kind == "price_change":
            inner = (f"<p>Hi Aarav,</p><p>We're writing to let you know that the price of your Netflix Standard plan is changing "
                     f"from ₹{inr(d['old'])}/month to <b>₹{inr(d['new'])}/month</b>, starting {d['effective']:%d %B %Y}.</p>"
                     "<p>You can change your plan or cancel anytime.</p>")
            return [self.msg("Netflix <info@account.netflix.com>", n.ts, "Your Netflix plan price is changing",
                             _doc("Price change", inner), "subscription_notice", "netflix_price_change",
                             expect={"service": "Netflix", "amount": str(d["new"])})]
        if n.kind in ("trial_started", "trial_ending"):
            what = "has started" if n.kind == "trial_started" else "ends soon"
            inner = (f"<p>Hi Aarav,</p><p>Your Audible free trial {what}. Your trial ends on <b>{d['trial_end']:%d %B %Y}</b>; "
                     f"after that your membership renews automatically at ₹{inr(d['price'])}/month.</p>")
            return [self.msg("Audible <no-reply@audible.in>", n.ts, f"Your Audible free trial {what}", _doc("Audible", inner),
                             "subscription_notice", f"audible_{n.kind}", expect={"service": "Audible", "amount": str(d["price"])})]
        if n.kind == "class_booking":
            inner = (f"<p>Your class is booked!</p><p><b>{d['workout']}</b> at {d['center']}</p>"
                     f"<p>{d['when']:%A, %d %B %Y at %I:%M %p}</p><p>See you there. Team cult.fit</p>")
            return [self.msg("cult.fit <no-reply@cult.fit>", n.ts, f"Class booked: {d['workout']} on {d['when']:%d %b}",
                             _doc("cult.fit", inner), "usage", "cult_booking", expect={"service": "Cult.fit"})]
        if n.kind == "sip_confirmation":
            inner = (f"<p>Dear Investor,</p><p>Your SIP instalment of <b>Rs.{inr(d['amount'])}</b> in "
                     f"<b>Zenith {d['scheme'].replace(' SIP', '')} Fund</b> (Folio {d['folio']}) has been processed. "
                     f"Units allotted: {d['units']}.</p>")
            return [self.msg("CAMS <donotreply@camsonline.com>", n.ts, "SIP instalment processed", _doc("SIP", inner),
                             "order_receipt", "sip_confirmation", expect={"amount": str(d["amount"])})]
        if n.kind == "lic_receipt":
            inner = (f"<p>Dear Policyholder,</p><p>We acknowledge receipt of premium of <b>Rs.{inr(d['amount'])}</b> for policy "
                     f"no. {d['policy']}. This receipt can be used for claiming deduction under Section 80C.</p>")
            return [self.msg("LIC of India <noreply@licindia.in>", n.ts, "Premium paid acknowledgement", _doc("LIC", inner),
                             "order_receipt", "lic_receipt", expect={"amount": str(d["amount"])})]
        if n.kind == "insurance_receipt":
            inner = (f"<p>Dear Customer,</p><p>Your health insurance policy {d['policy']} has been renewed. Premium received: "
                     f"<b>₹{inr(d['amount'])}</b>. Eligible for tax benefit under Section 80D.</p>")
            return [self.msg("Star Health <renewals@starhealth.in>", n.ts, "Policy renewed successfully", _doc("Renewal", inner),
                             "order_receipt", "insurance_receipt", expect={"amount": str(d["amount"])})]
        if n.kind == "refund_initiated":
            inner = (f"<p>Hi Aarav,</p><p>Your return of <b>{d['item']}</b> from order {d['order_id']} has been picked up and your "
                     "refund has been initiated. It will reach your original payment method within 5-7 business days.</p>")
            return [self.msg("Myntra <updates@myntra.com>", n.ts, "Refund initiated for your Myntra return", _doc("Refund", inner),
                             "refund", "myntra_refund_initiated")]
        if n.kind == "promo_email":
            sender, subject, inner = self.PROMO[d["variant"] % len(self.PROMO)]
            return [self.msg(sender, n.ts, subject, _doc(subject, inner), "promo", "promo_email")]
        if n.kind == "newsletter_email":
            sender, subject, inner = self.NEWSLETTERS[d["variant"] % len(self.NEWSLETTERS)]
            return [self.msg(sender, n.ts, subject, _doc(subject, inner), "other", "newsletter")]
        return []

    def render(self) -> list[RawMessage]:
        out: list[RawMessage] = []
        for t in self.p.txns:
            out.extend(self.txn_emails(t))
        for n in self.p.notices:
            out.extend(self.notice_emails(n))
        out = [m for m in out if m.received_at.date() <= self.p.end]
        out.sort(key=lambda m: m.received_at)
        return out


def render_emails(persona: Persona) -> list[RawMessage]:
    return EmailRenderer(persona).render()
