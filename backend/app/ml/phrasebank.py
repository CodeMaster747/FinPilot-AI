"""Extra training phrasings so the message classifier generalises beyond the persona's bank styles.

Deliberately worded differently from the challenge and sealed evaluation sets (no copying)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.services.ingestion.types import RawMessage

BANKS = [("HDFCBK", "HDFC Bank"), ("ICICIB", "ICICI Bank"), ("SBIINB", "SBI"), ("AXISBK", "Axis Bank"), ("KOTAKB", "Kotak"),
         ("IDFCFB", "IDFC FIRST"), ("YESBNK", "YES Bank"), ("CANBNK", "Canara Bank"), ("PNBSMS", "PNB"), ("INDUSB", "IndusInd")]
MERCHANTS = ["SWIGGY", "ZOMATO", "AMAZON", "FLIPKART", "BIGBASKET", "DMART", "UBER", "OLA", "APOLLO", "MYNTRA", "NYKAA",
             "STARBUCKS", "PVR", "IRCTC", "JIO", "AIRTEL", "DECATHLON", "CROMA", "ZEPTO", "BLINKIT", "MAKEMYTRIP", "LENSKART"]
PEOPLE = ["RAHUL M", "SNEHA R", "KARTHIK V", "DIVYA S", "ARUN K", "MEERA J"]
SERVICES = [("Spotify", "spotify.com"), ("Netflix", "netflix.com"), ("YouTube", "youtube.com"), ("Audible", "audible.in"),
            ("JioHotstar", "jiohotstar.com"), ("Amazon Prime", "amazon.in")]

DEBIT = [
    "Your a/c {acct} is debited with Rs.{amt} on {d} for a payment to {m}. Ref {ref}.",
    "Rs {amt} has been deducted from your account {acct} towards {m} on {d}.",
    "Txn of INR {amt} done on your {bank} card {acct} at {m} on {d}.",
    "Purchase of Rs.{amt} at {m} using card {acct} on {d} is successful.",
    "You paid Rs.{amt} to {m} from {bank} a/c {acct}. UPI ref {ref}.",
    "{bank}: INR {amt} withdrawn from a/c {acct} at ATM on {d}.",
    "A/c {acct} debited by Rs {amt} via NEFT to {p} on {d}. Ref {ref}.",
    "INR {amt} charged on your {bank} credit card {acct} at {m} on {d}. Available limit INR {bal}.",
    "Debit alert: Rs.{amt} paid to {m} from a/c {acct} on {d}. Bal: Rs.{bal}",
    # alert layouts that also quote a balance or arrive on several lines (common in real bank SMS)
    "Dear Customer, A/c {acct} has a debit of Rs {amt} on {d} towards {m}. Available Bal Rs {bal}.",
    "Rs {amt} paid to {m} from your {bank} a/c {acct} on {d}. Balance: Rs {bal}",
    "INR {amt} debited\nAcct {acct}\n{d}\n{m}\nAvl Bal INR {bal}",
    "Your a/c {acct} is debited by INR {amt} for {m} on {d}. Avl Bal: INR {bal}. If not you, call the bank.",
    "{bank}: Payment of Rs.{amt} made to {m} via UPI from a/c {acct}. Ref {ref}. Bal Rs {bal}",
    "Rs.{amt} auto-debited from a/c {acct} on {d} for {m} mandate. Bal Rs.{bal}",
]
CREDIT = [
    "Your a/c {acct} is credited with Rs.{amt} on {d} by {p}. Ref {ref}.",
    "Rs {amt} received in your {bank} account {acct} from {p} on {d}.",
    "INR {amt} deposited to a/c {acct} on {d} - salary credit from {p} ltd.",
    "Credit alert: Rs.{amt} added to your account {acct} via IMPS from {p}. Bal Rs.{bal}",
    "Interest of Rs {amt} credited to your savings a/c {acct} on {d}.",
    "Dear Customer, A/c {acct} has a credit of Rs {amt} on {d} from {p}. Available Bal Rs {bal}.",
    "INR {amt} credited\nAcct {acct}\n{d}\nIMPS from {p}\nAvl Bal INR {bal}",
    "Your a/c {acct} is credited by Rs.{amt} on {d} via NEFT from {p} ltd. Bal Rs {bal}",
]
REFUND = [
    "Refund of Rs.{amt} from {m} has been processed to your a/c {acct} on {d}.",
    "Rs {amt} refunded by {m} to your {bank} card {acct}.",
    "Your refund of INR {amt} for the {m} order has been credited on {d}.",
    "{m} has initiated a refund of Rs.{amt} to your original payment method.",
]
FAILED = [
    "Your transaction of Rs.{amt} at {m} was declined. No amount has been debited.",
    "Payment of Rs {amt} to {m} failed. If debited, it will be reversed in 48 hours.",
    "Rs.{amt} debited earlier for txn {ref} has been reversed to your a/c {acct}.",
    "UPI payment of INR {amt} to {m} could not be processed due to a bank server issue.",
    "Reversal of Rs {amt} credited to a/c {acct} for failed transaction ref {ref}.",
]
OTP = [
    "{code} is your OTP for a payment of Rs.{amt} at {m}. Do not share it with anyone.",
    "Use OTP {code} to authorise txn of INR {amt} on your card {acct}. Never share your OTP.",
    "OTP for login to {bank} NetBanking is {code}. Valid for 5 mins.",
    "{code} is the one time password for your {m} transaction. Bank never asks for OTP.",
    "Your verification code is {code}. It expires in 10 minutes.",
]
PROMO = [
    "Get flat {pct}% off up to Rs.{amt} on your next {m} order. Use code SAVE{pct}.",
    "Pre-approved loan of Rs.{big} at low interest! Apply now in 2 clicks.",
    "Upgrade to our premium credit card with annual fee waiver worth Rs.{amt}. Apply today.",
    "Mega sale! Up to {pct}% off on electronics + Rs.{amt} cashback with {bank} cards.",
    "Recharge now with Rs.{amt} and get unlimited calls and 2GB/day for 28 days.",
    "Invest in mutual funds starting Rs.{amt}/month. Start your SIP today!",
    "You have won a voucher worth Rs.{amt}! Claim before midnight.",
    "Exclusive offer: {pct}% cashback up to Rs.{amt} on bill payments this weekend.",
]
BILL = [
    "Your electricity bill of Rs.{amt} for consumer no {num} is due on {due}.",
    "Gas bill of Rs {amt} generated for account {num}. Pay by {due} to avoid penalty.",
    "Broadband invoice Rs.{amt} for A/c {num} due on {due}. Pay online now.",
    "Your postpaid mobile bill of Rs {amt} is due on {due}.",
    "Water bill for connection {num}: Rs.{amt}, last date {due}.",
    "DTH subscription of Rs.{amt} due on {due} for customer id {num}.",
]
STATEMENT = [
    "Credit card statement for card {acct}: total amount due Rs.{amt}, minimum due Rs.{min}, due date {due}.",
    "Your {bank} card {acct} bill is generated. Amount due INR {amt}. Pay by {due}.",
    "Statement generated: Total Due Rs {amt}; Min Due Rs {min}; Payment Due Date {due}.",
]
BALANCE = [
    "Available balance in a/c {acct} is Rs.{bal} as on {d}.",
    "Your {bank} savings a/c {acct} balance is INR {bal}.",
    "Bal in a/c {acct} on {d}: Rs {bal}.",
    "As requested, the balance in your {bank} account {acct} is Rs {bal} as of {d}.",
    "Closing balance for a/c {acct} on {d}: INR {bal}. Cheques are subject to clearing.",
]
OTHER = [
    "Your {m} order has been shipped and will be delivered tomorrow.",
    "Your {m} delivery partner is on the way. Track your order in the app.",
    "Dear customer, your address has been updated successfully.",
    "Your debit card {acct} has been dispatched and will reach you in 5 days.",
    "Your service request {num} has been closed. Thank you.",
    "New login to your {bank} NetBanking from a Chrome browser.",
    "Your mobile number has been linked to your a/c {acct}.",
    "Rate your recent {m} experience and help us improve!",
    "Your cheque {num} has been cleared.",
]
RECEIPT = [
    "Thanks for your order from {m}!\nOrder ID {num}\nItems: 3\nTotal: ₹{amt}",
    "Payment received. Invoice {num} for ₹{amt} has been paid in full. - {m}",
    "Your booking is confirmed. Booking reference {num}. Amount paid ₹{amt}.",
    "Receipt for your {m} purchase\nSubtotal ₹{amt}\nThank you for shopping with us",
    "Order placed successfully! Grand Total: ₹{amt}. We'll notify you when it ships.",
    "Your premium payment of Rs.{amt} for policy {num} has been received.",
]
NOTICE = [
    "Your {svc} subscription renews on {due} for ₹{amt}/month.",
    "We're updating the price of your {svc} plan to ₹{amt}/month from {due}.",
    "Your free trial of {svc} ends on {due}. You'll be charged ₹{amt}/month after that.",
    "Reminder: your {svc} membership will auto-renew at ₹{amt}/month on {due}.",
]
USAGE = [
    "Your {cls} class at {center} on {due} is booked.",
    "Session confirmed: {cls} at {center}, {due}.",
    "You checked in at {center} today. Keep it up!",
]
SMS_KINDS = {"transaction": DEBIT + CREDIT, "refund": REFUND, "failed_or_reversed": FAILED, "otp": OTP, "promo": PROMO,
             "bill_due": BILL, "statement": STATEMENT, "balance": BALANCE, "other": OTHER}
EMAIL_KINDS = {"order_receipt": RECEIPT, "subscription_notice": NOTICE, "usage": USAGE, "promo": PROMO, "other": OTHER,
               "refund": REFUND, "statement": STATEMENT, "bill_due": BILL}


def generate(n_per_kind: int = 45, seed: int = 17) -> list[RawMessage]:
    r = random.Random(seed)
    base = datetime(2026, 2, 1, 9)
    out = []

    def fill(tpl: str) -> str:
        code, bank = r.choice(BANKS)
        ts = base + timedelta(days=r.randint(0, 200))
        return tpl.format(
            acct=r.choice(["XX", "X", "**", "XXXXXX"]) + str(r.randint(1000, 9999)), amt=f"{r.randint(20, 40000):,}.{r.choice(['00', '50', '99'])}",
            bal=f"{r.randint(1000, 200000):,}.00", big=f"{r.choice([2, 3, 5, 10])},00,000", d=ts.strftime(r.choice(["%d-%m-%y", "%d/%m/%Y", "%d %b %Y"])),
            due=(ts + timedelta(days=12)).strftime(r.choice(["%d-%m-%Y", "%d %b %Y", "%d/%m/%y"])), m=r.choice(MERCHANTS), p=r.choice(PEOPLE),
            ref="".join(r.choice("0123456789") for _ in range(12)), code=r.randint(100000, 999999), pct=r.choice([10, 20, 25, 40, 50]),
            bank=bank, num=r.randint(100000, 9999999), min=f"{r.randint(200, 2000):,}.00", svc=r.choice(SERVICES)[0],
            cls=r.choice(["Yoga", "HIIT", "Zumba", "Spin"]), center=r.choice(["Anna Nagar", "OMR", "Adyar"]),
        )

    for kind, tpls in SMS_KINDS.items():
        for _ in range(n_per_kind):
            code, _ = r.choice(BANKS)
            suffix = "T" if kind == "otp" else "S"
            sender = r.choice([f"{r.choice(['VM', 'AD', 'JD', 'BZ', 'AX'])}-{code}-{suffix}", f"{r.choice(['VK', 'JM'])}-{code}", code])
            out.append(RawMessage("sms", sender, base, fill(r.choice(tpls)),
                                  truth={"kind": kind, "template": f"phrase_{kind}"}))
    for kind, tpls in EMAIL_KINDS.items():
        for _ in range(n_per_kind // 2):
            svc, domain = r.choice(SERVICES)
            body = fill(r.choice(tpls))
            out.append(RawMessage("email", f"{svc} <noreply@{domain}>", base, body, subject=body.split("\n")[0][:60],
                                  truth={"kind": kind, "template": f"phrase_{kind}"}))
    return out
