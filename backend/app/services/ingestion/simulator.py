"""Live simulator: realistic messages addressed to the user's own accounts, so a demo can show a
payment arriving, an OTP being ignored, or a receipt enriching the payment it belongs to."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Transaction, User
from app.seed.sms import inr


def _mask(db: Session, user: User, institution: str, kind: str, default: str) -> str:
    acct = db.scalar(select(Account).where(Account.user_id == user.id, Account.institution == institution, Account.kind == kind))
    return acct.mask if acct and acct.mask else default


def _last(db: Session, user: User, merchant: str) -> Transaction | None:
    return db.scalar(select(Transaction).where(Transaction.user_id == user.id, Transaction.merchant_name == merchant,
                                               Transaction.direction == "debit").order_by(Transaction.id.desc()).limit(1))


def templates(db: Session, user: User) -> list[dict]:
    r = random.Random(datetime.now().strftime("%Y%m%d%H%M"))
    now = datetime.now()
    hdfc = _mask(db, user, "HDFC Bank", "savings", "4521")
    icici = _mask(db, user, "ICICI Bank", "credit_card", "7788")
    ref = "".join(r.choice("0123456789") for _ in range(12))
    upi_amt = Decimal(r.randint(240, 760))
    card_amt = Decimal(r.choice([799, 1299, 1499, 2499]))
    otp = r.randint(100000, 999999)

    last_swiggy = _last(db, user, "Swiggy")
    swiggy_amt = last_swiggy.amount if last_swiggy else upi_amt
    food = [("Chicken Biryani", 1, swiggy_amt - Decimal("49.00")), ("Delivery fee & taxes", 1, Decimal("49.00"))]
    if swiggy_amt <= 60:
        food = [("Order", 1, swiggy_amt)]
    rows = "".join(f"<tr><td class='item'>{n}</td><td class='qty'>{q}</td><td class='price'>₹{inr(p)}</td></tr>" for n, q, p in food)
    swiggy_html = (f"<h2>Your order from Dindigul Thalappakatti has been delivered</h2><p>Order No: <b>{r.randint(10**11, 10**12 - 1)}</b></p>"
                   f"<table class='items'><tr><th>Item</th><th>Qty</th><th>Price</th></tr>{rows}</table>"
                   f"<p><b>Order Total: ₹{inr(swiggy_amt)}</b></p><p>Paid via UPI</p>")

    last_amazon = _last(db, user, "Amazon")
    amazon_amt = last_amazon.amount if last_amazon else card_amt
    order_no = f"40{r.randint(1, 9)}-{r.randint(10**6, 10**7 - 1)}-{r.randint(10**6, 10**7 - 1)}"
    ld = {"@context": "http://schema.org", "@type": "Order", "merchant": {"@type": "Organization", "name": "Amazon.in"},
          "orderNumber": order_no, "priceCurrency": "INR", "price": f"{amazon_amt:.2f}",
          "acceptedOffer": [{"@type": "Offer", "itemOffered": {"@type": "Product", "name": "Wireless Earbuds"},
                             "price": f"{amazon_amt:.2f}", "priceCurrency": "INR", "eligibleQuantity": {"@type": "QuantitativeValue", "value": 1}}]}
    amazon_html = (f"<script type='application/ld+json'>{json.dumps(ld)}</script><p>Hello,</p><p>Thank you for your order.</p>"
                   f"<p>Order #{order_no}</p><p>Wireless Earbuds — Qty 1 — ₹{inr(amazon_amt)}</p><p><b>Order Total: ₹{inr(amazon_amt)}</b></p>")

    return [
        {"id": "upi_swiggy", "channel": "sms", "group": "Payments", "label": "UPI payment to Swiggy", "sender": "VM-HDFCBK-S",
         "body": f"Sent Rs.{upi_amt:.2f}\nFrom HDFC Bank A/C *{hdfc}\nTo BUNDL TECHNOLOGIES\nOn {now:%d/%m/%y}\nRef {ref}\nNot You?\nCall 1800XXXXXXX/SMS BLOCK UPI to 7308XXXXXX"},
        {"id": "card_amazon", "channel": "sms", "group": "Payments", "label": "Card spend at Amazon", "sender": "JD-ICICIT-S",
         "body": f"INR {inr(card_amt)} spent using ICICI Bank Card XX{icici} on {now:%d-%b-%y} on AMAZON PAY INDIA. Avl Limit: INR 1,52,410.00. If not you, call 1800XXXXXXX or SMS BLOCK {icici} to 9215XXXXXX."},
        {"id": "salary", "channel": "sms", "group": "Payments", "label": "Salary credited", "sender": "AD-HDFCBK-S",
         "body": f"Update! INR 1,33,000.00 deposited in HDFC Bank A/c XX{hdfc} on {now.strftime('%d-%b-%y').upper()} for NEFT "
                 f"Cr-HSBC0560002-ZENTRIX TECHNOLOGIES PVT LTD-SALARY-{ref}.Avl bal INR 4,12,500.00. Cheque deposits in A/C are subject to clearing"},
        {"id": "refund", "channel": "sms", "group": "Payments", "label": "Card refund from Amazon", "sender": "VM-ICICIT-S",
         "body": f"Dear Customer, a refund of INR {inr(amazon_amt)} from AMAZON PAY INDIA has been credited to your ICICI Bank Credit Card XX{icici} on {now:%d-%b-%y}."},
        {"id": "otp", "channel": "sms", "group": "Should be ignored", "label": "OTP for a card payment", "sender": "VM-ICICIT-T",
         "body": f"{otp} is OTP for txn of INR {inr(card_amt)} at AMAZON PAY INDIA on ICICI Bank Card XX{icici}. OTPs are SECRET. DO NOT disclose it to anyone."},
        {"id": "promo", "channel": "sms", "group": "Should be ignored", "label": "Promotional loan offer (-P)", "sender": "VK-HDFCBK-P",
         "body": "Pre-approved Personal Loan of Rs.5,00,000 is ready for you! Instant disbursal at attractive rates. Apply now: hdfcbk.io/x T&C"},
        {"id": "personal", "channel": "sms", "group": "Should be ignored", "label": "Personal chat", "sender": "+919840012345",
         "body": "Hey, are we still on for dinner at 8? I'll book a table."},
        {"id": "failed", "channel": "sms", "group": "Payments", "label": "Failed UPI payment", "sender": "VM-HDFCBK-S",
         "body": f"Your UPI transaction of Rs.{inr(upi_amt)} to ZEPTO has failed. Any amount debited will be reversed within 3 working days. -HDFC Bank"},
        {"id": "bill", "channel": "sms", "group": "Bills", "label": "Airtel bill reminder", "sender": "VM-AIRTEL-S",
         "body": f"Dear Customer, your Airtel Postpaid bill of Rs.699.00 for 98840 12345 is due on {now + timedelta(days=7):%d-%b-%Y}. Pay now on the Airtel Thanks app."},
        {"id": "swiggy_receipt", "channel": "email", "group": "Receipts", "label": "Swiggy receipt for your last order",
         "sender": "Swiggy <noreply@swiggy.in>", "subject": "Your Swiggy order from Dindigul Thalappakatti was delivered successfully", "html": swiggy_html},
        {"id": "amazon_order", "channel": "email", "group": "Receipts", "label": "Amazon order confirmation (schema.org markup)",
         "sender": "Amazon.in <auto-confirm@amazon.in>", "subject": f"Your Amazon.in order #{order_no} of 1 item", "html": amazon_html},
        {"id": "bank_email", "channel": "email", "group": "Payments", "label": "ICICI alert email for the same card spend",
         "sender": "ICICI Bank <credit_cards@icicibank.com>", "subject": "Transaction alert for your ICICI Bank Credit Card",
         "html": f"<p>Dear Customer,</p><p>Your ICICI Bank Credit Card XX{icici} has been used for a transaction of <b>INR {inr(card_amt)}</b> on {now:%b %d, %Y} at {now:%H:%M:%S}. Info: AMAZON PAY INDIA.</p>"},
        {"id": "price_change", "channel": "email", "group": "Subscriptions", "label": "Netflix price-change notice",
         "sender": "Netflix <info@account.netflix.com>", "subject": "Your Netflix plan price is changing",
         "html": "<p>Hi,</p><p>The price of your Netflix Standard plan is changing from ₹649/month to <b>₹799/month</b>, starting next month.</p>"},
        {"id": "newsletter", "channel": "email", "group": "Should be ignored", "label": "Newsletter from a non-financial sender",
         "sender": "Medium Daily Digest <noreply@medium.com>", "subject": "Stories for you", "html": "<p>Today's highlights: 10 VS Code tips.</p>"},
    ]
