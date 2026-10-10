"""Render persona truth into raw SMS in the alert styles of four Indian banks (plus held-out styles
used only for evaluation). Every message carries a ``truth`` label for measuring the parsers."""

from __future__ import annotations

import bisect
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.seed.persona import Notice, Persona, TruthTxn
from app.services.ingestion.types import RawMessage

ROUTES = ["VM", "VK", "AD", "JD", "BZ", "AX", "JM", "TM"]


def inr(a: Decimal, commas: bool = True) -> str:
    whole, frac = f"{a:.2f}".split(".")
    if commas and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{whole}.{frac}"


def sbi_amt(a: Decimal) -> str:
    return f"{a:.1f}" if a == a.to_integral_value() else f"{a:.2f}"


def MON(d: date) -> str:
    return d.strftime("%d-%b-%y").upper()


def Mon(d: date) -> str:
    return d.strftime("%d-%b-%y")


class SmsRenderer:
    def __init__(self, persona: Persona, seed: int = 11):
        self.p = persona
        self.rng = random.Random(seed + persona.end.toordinal())
        self.masks = {a.key: a.mask for a in persona.accounts}
        self._bal_index: dict[str, tuple[list[datetime], list[Decimal]]] = {}
        for acct in ("hdfc", "sbi", "icici"):
            rows = [(t.ts, t.balance_after) for t in persona.txns if t.account == acct]
            self._bal_index[acct] = ([r[0] for r in rows], [r[1] for r in rows])

    def sender(self, header: str, suffix: str = "S") -> str:
        return f"{self.rng.choice(ROUTES)}-{header}-{suffix}"

    def balance_at(self, account: str, ts: datetime) -> Decimal:
        times, bals = self._bal_index[account]
        i = bisect.bisect_right(times, ts) - 1
        if i < 0:
            return next(a.opening_balance for a in self.p.accounts if a.key == account)
        return bals[i]

    def msg(self, sender: str, ts: datetime, body: str, kind: str, template: str, txn: TruthTxn | None = None,
            expect: dict | None = None) -> RawMessage:
        truth = {"kind": kind, "template": template, "txn_id": txn.id if txn else None, "expect": expect or {}}
        return RawMessage(channel="sms", sender=sender, received_at=ts, body=body, truth=truth)

    # -- transactions ----------------------------------------------------------------------------
    def txn_messages(self, t: TruthTxn) -> list[RawMessage]:
        out: list[RawMessage] = []
        m = self.masks[t.account]
        ts = t.ts + timedelta(seconds=self.rng.randint(4, 75))
        d = t.ts.date()
        amt, bal = t.amount, t.balance_after
        exp = {"amount": str(amt), "direction": t.direction, "mask": m, "date": d.isoformat()}
        if t.otp:
            otp = f"{self.rng.randint(100000, 999999)}"
            ots = t.ts - timedelta(seconds=self.rng.randint(25, 110))
            if t.account == "icici":
                body = (f"{otp} is OTP for txn of INR {inr(amt)} at {t.payee} on ICICI Bank Card XX{m}. "
                        "OTPs are SECRET. DO NOT disclose it to anyone. Bank NEVER asks for OTP.")
                out.append(self.msg(self.sender("ICICIT", "T"), ots, body, "otp", "icici_otp", t))
            else:
                body = (f"{otp} is the OTP for transaction of Rs.{inr(amt)} at {t.payee} on HDFC Bank Card ending {m}. "
                        "Valid for 5 mins. Do not share OTP for security reasons.")
                out.append(self.msg(self.sender("HDFCBK", "T"), ots, body, "otp", "hdfc_otp", t))

        if t.account == "hdfc":
            if t.kind == "reversal":
                body = f"Rs.{inr(amt)} reversed to your HDFC Bank A/c XX{m} on {d:%d-%m-%y} against UPI Ref {t.ref}. Avl bal Rs.{inr(bal)}"
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "failed_or_reversed", "hdfc_reversal", t,
                                    {**exp, "ref": t.ref, "balance": str(bal)}))
            elif t.channel == "upi" and t.direction == "debit":
                body = (f"Sent Rs.{amt:.2f}\nFrom HDFC Bank A/C *{m}\nTo {t.payee}\nOn {d:%d/%m/%y}\nRef {t.ref}\n"
                        "Not You?\nCall 1800XXXXXXX/SMS BLOCK UPI to 7308XXXXXX")
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_upi_debit", t,
                                    {**exp, "ref": t.ref, "payee": t.payee}))
            elif t.channel == "dcard":
                body = (f"Spent Rs.{amt:.2f} On HDFC Bank Card {m} At {t.payee} On {t.ts:%Y-%m-%d:%H:%M:%S}\n"
                        f"Not You? To Block+Reissue Call 1800XXXXXXX/SMS BLOCK DC {m} to 7308XXXXXX")
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_dcard", t, {**exp, "payee": t.payee}))
            elif t.channel == "nach":
                body = f"Rs.{inr(amt)} debited from A/c XX{m} on {MON(d)} towards ACH D- {t.payee} Ref {t.ref}. Avl Bal Rs.{inr(bal)}"
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_nach", t,
                                    {**exp, "ref": t.ref, "payee": t.payee, "balance": str(bal)}))
            elif t.channel == "imps":
                body = (f"Rs.{inr(amt)} debited from HDFC Bank A/c XX{m} on {d:%d-%m-%y} to {t.payee} via IMPS. Ref {t.ref}. "
                        f"Avl bal Rs.{inr(bal)}. Not you? Call 1800XXXXXXX")
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_imps_out", t,
                                    {**exp, "ref": t.ref, "payee": t.payee, "balance": str(bal)}))
            elif t.channel == "neft":
                body = (f"Update! INR {inr(amt)} deposited in HDFC Bank A/c XX{m} on {MON(d)} for NEFT Cr-HSBC0560002-{t.payee}-"
                        f"{t.ref}.Avl bal INR {inr(bal)}. Cheque deposits in A/C are subject to clearing")
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_neft_credit", t,
                                    {**exp, "ref": t.ref, "balance": str(bal)}))
            elif t.channel == "atm":
                body = f"Rs.{inr(amt)} withdrawn at {t.payee} from A/c XX{m} on {MON(d)}. Avl bal: Rs.{inr(bal)}. Not you? Call 1800XXXXXXX"
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_atm", t, {**exp, "balance": str(bal)}))
            elif t.channel == "interest":
                body = f"Dear Customer, interest of Rs.{inr(amt)} has been credited to your HDFC Bank A/c XX{m} on {MON(d)}. Avl bal Rs.{inr(bal)}"
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_interest", t, {**exp, "balance": str(bal)}))
            elif t.channel == "upi" and t.direction == "credit":
                body = (f"Received Rs.{inr(amt)} in your HDFC Bank A/c XX{m} from {t.payee} on {d:%d-%m-%y}. "
                        f"UPI Ref No. {t.ref}. Avl bal: Rs.{inr(bal)}")
                out.append(self.msg(self.sender("HDFCBK"), ts, body, "transaction", "hdfc_upi_credit", t, {**exp, "ref": t.ref}))
        elif t.account == "icici":
            if t.kind == "card_payment_in":
                body = (f"Dear Customer, Payment of INR {inr(amt)} has been received towards your ICICI Bank Credit Card "
                        f"Account XX{m} on {Mon(d)}. Thank you.")
                out.append(self.msg(self.sender("ICICIT"), ts, body, "transaction", "icici_payment", t, exp))
            elif t.kind == "refund":
                body = (f"Dear Customer, a refund of INR {inr(amt)} from {t.payee} has been credited to your ICICI Bank "
                        f"Credit Card XX{m} on {Mon(d)}.")
                out.append(self.msg(self.sender("ICICIT"), ts, body, "refund", "icici_refund", t, {**exp, "payee": t.payee}))
            else:
                body = (f"INR {inr(amt)} spent using ICICI Bank Card XX{m} on {Mon(d)} on {t.payee}. Avl Limit: INR {inr(bal)}. "
                        f"If not you, call 1800XXXXXXX or SMS BLOCK {m} to 9215XXXXXX.")
                out.append(self.msg(self.sender("ICICIT"), ts, body, "transaction", "icici_card_spend", t,
                                    {**exp, "payee": t.payee}))
        elif t.account == "sbi":
            if t.channel == "imps" and t.direction == "credit":
                body = f"Dear Customer, your A/c X{m} is credited by Rs.{inr(amt)} on {d:%d-%m-%y} by IMPS (Ref no {t.ref}) from {t.payee}. -SBI"
                out.append(self.msg(self.sender("SBIINB"), ts, body, "transaction", "sbi_imps_credit", t, {**exp, "ref": t.ref}))
            elif t.channel == "nach":
                body = f"Your a/c no. XXXXXXX{m} is debited for Rs.{inr(amt)} on {d:%d-%m-%y} by NACH towards {t.payee}. Avl Bal Rs.{inr(bal)} -SBI"
                out.append(self.msg(self.sender("SBIINB"), ts, body, "transaction", "sbi_nach", t,
                                    {**exp, "payee": t.payee, "balance": str(bal)}))
            elif t.channel == "interest":
                body = f"Dear Customer, interest of Rs.{inr(amt)} has been credited to your A/c X{m} on {d:%d-%m-%y}. -SBI"
                out.append(self.msg(self.sender("SBIINB"), ts, body, "transaction", "sbi_interest", t, exp))
            elif t.channel == "upi":
                body = (f"Dear UPI user A/C X{m} debited by {sbi_amt(amt)} on date {d:%d%b%y} trf to {t.payee} Refno {t.ref}. "
                        "If not u? call 1800XXXXXXX. -SBI")
                out.append(self.msg(self.sender("SBIUPI"), ts, body, "transaction", "sbi_upi_debit", t, {**exp, "ref": t.ref}))
        return out

    # -- non-transaction messages ----------------------------------------------------------------
    PROMOS = [
        ("HDFCBK", "Pre-approved Personal Loan of Rs.5,00,000 is ready for you! Instant disbursal at attractive rates. Apply now: hdfcbk.io/x T&C"),
        ("ZOMATO", "Craving biryani? Flat 50% OFF up to Rs.100 on your next order. Use code TRYNEW. Order now!"),
        ("MYNTRA", "End of Reason Sale is LIVE! 50-90% OFF on 5000+ brands. Extra Rs.300 off on your first purchase."),
        ("AIRTEL", "Recharge with Rs.349 and get unlimited 5G data + 2GB/day. Offer valid till midnight."),
        ("BAJAJF", "Your EMI Network Card is pre-approved with a limit of Rs.1,00,000. Shop on No Cost EMI now."),
        ("PAYTMB", "Get cashback up to Rs.250 on electricity bill payment above Rs.999 via Paytm UPI. T&C apply."),
        ("SWIGGY", "Your favourite restaurants are now delivering! Get 60% off up to Rs.120 on orders above Rs.199."),
        ("ICICIT", "Upgrade to ICICI Bank Sapphiro Credit Card. Lounge access + 4x rewards. Annual fee Rs.3,500 waived."),
    ]
    PERSONAL = ["Hey, are we still on for dinner at 8?", "Reached home. Call me when free.", "Can you send me the notes from today?",
                "Happy birthday da! Party when?", "Mom: buy milk on the way back", "Meeting moved to 4pm"]

    def notice_messages(self, n: Notice) -> list[RawMessage]:
        r, d = self.rng, n.ts.date()
        if n.kind == "bill_due":
            a, due = n.data["amount"], n.data["due"]
            if n.data["biller"] == "TNPDCL":
                body = f"Dear Consumer, TNPDCL bill for SC No.{n.data['account_no']} is Rs.{inr(a)}. Due date {due:%d-%m-%Y}. Pay online to avoid disconnection. -TNPDCL"
                header = "TNPDCL"
            elif n.data["biller"] == "Airtel":
                body = f"Dear Customer, your Airtel Postpaid bill of Rs.{inr(a)} for {n.data['account_no']} is due on {due:%d-%b-%Y}. Pay now on the Airtel Thanks app."
                header = "AIRTEL"
            else:
                body = f"Your ACT Fibernet bill of Rs.{inr(a)} for A/c {n.data['account_no']} is due on {due:%d-%m-%Y}. Pay now to enjoy uninterrupted service."
                header = "ACTFBR"
            return [self.msg(self.sender(header), n.ts, body, "bill_due", f"{header.lower()}_bill",
                             expect={"amount": str(a), "due": due.isoformat(), "payee": n.data["biller"]})]
        if n.kind == "card_statement":
            body = (f"ICICI Bank Credit Card XX{self.masks['icici']} Statement: Total Amount Due INR {inr(n.data['total'])}; "
                    f"Minimum Amount Due INR {inr(n.data['minimum'])}; Payment Due Date {Mon(n.data['due'])}. Pay via iMobile Pay.")
            return [self.msg(self.sender("ICICIT"), n.ts, body, "statement", "icici_statement",
                             expect={"amount": str(n.data["total"]), "due": n.data["due"].isoformat()})]
        if n.kind == "failed_upi":
            body = (f"Your UPI transaction of Rs.{inr(n.data['amount'])} to {n.data['payee']} has failed. Any amount debited "
                    "will be reversed within 3 working days. -HDFC Bank")
            return [self.msg(self.sender("HDFCBK"), n.ts, body, "failed_or_reversed", "hdfc_failed")]
        if n.kind == "balance_alert":
            acct = n.data["account"]
            bal = self.balance_at(acct, n.ts)
            m = self.masks[acct]
            if acct == "hdfc":
                body = f"Available Bal in HDFC Bank A/c XX{m} as on {MON(d)} is Rs.{inr(bal)}. Cheque deposits in A/C are subject to clearing"
                return [self.msg(self.sender("HDFCBK"), n.ts, body, "balance", "hdfc_balance", expect={"balance": str(bal), "mask": m})]
            body = f"Your A/c X{m} has a balance of Rs.{inr(bal)} as on {d:%d-%m-%y}. -SBI"
            return [self.msg(self.sender("SBIINB"), n.ts, body, "balance", "sbi_balance", expect={"balance": str(bal), "mask": m})]
        if n.kind == "promo_sms":
            header, body = self.PROMOS[n.data["variant"] % len(self.PROMOS)]
            # a few promos arrive on non-promotional headers: the classifier (not the header rule) must catch them
            suffix = "S" if n.data["variant"] % 9 == 0 else "P"
            return [self.msg(self.sender(header, suffix), n.ts, body, "promo", "promo")]
        if n.kind == "personal_sms":
            body = self.PERSONAL[n.data["variant"] % len(self.PERSONAL)]
            return [self.msg(f"+9198{r.randint(10000000, 99999999)}", n.ts, body, "other", "personal")]
        return []

    def render(self) -> list[RawMessage]:
        out: list[RawMessage] = []
        for t in self.p.txns:
            out.extend(self.txn_messages(t))
        for n in self.p.notices:
            out.extend(self.notice_messages(n))
        out.sort(key=lambda m: m.received_at)
        return out


def render_sms(persona: Persona) -> list[RawMessage]:
    return SmsRenderer(persona).render()


# -- held-out bank styles: never used by the persona, only to test generalisation ---------------------
def heldout_sms(n: int = 200, seed: int = 99) -> list[RawMessage]:
    r = random.Random(seed)
    payees = ["SWIGGY", "BIGBASKET", "UBER INDIA", "DMART", "APOLLO PHARMACY", "NETFLIX", "DECATHLON", "STARBUCKS"]
    out = []
    for i in range(n):
        ts = datetime(2026, 1, 1, 9) + timedelta(hours=r.randint(0, 6000), minutes=r.randint(0, 59))
        amt = Decimal(r.randint(50, 25000)) + Decimal(r.choice([0, 0, 50])) / 100
        mask = f"{r.randint(1000, 9999)}"
        ref = "".join(r.choice("0123456789") for _ in range(12))
        payee = r.choice(payees)
        style = i % 4
        if style == 0:
            body = (f"INR {inr(amt)} debited from A/c no. XX{mask} on {ts:%d-%m-%Y %H:%M:%S} IST at UPI/{ref}/{payee}. "
                    f"Avl Bal- INR {inr(amt * 7)}. Not you? SMS BLOCKUPI Cust ID to 9199XXXXXXXX - Axis Bank")
            sender, kind, direction = "VM-AXISBK-S", "transaction", "debit"
        elif style == 1:
            body = (f"Spent\nCard no. XX{mask}\nINR {inr(amt)}\n{ts:%d-%m-%y %H:%M:%S}\n{payee}\nAvl Lmt INR {inr(amt * 9)}\n"
                    f"SMS BLOCK {mask} to 9199XXXXXXXX, if not you - Axis Bank")
            sender, kind, direction = "AX-AXISBK-S", "transaction", "debit"
        elif style == 2:
            body = f"Sent Rs.{amt:.2f} from Kotak Bank AC X{mask} to {payee.lower().replace(' ', '')}@ybl on {ts:%d-%m-%y}.UPI Ref {ref}. Not you, kotak.com/fraud"
            sender, kind, direction = "JD-KOTAKB-S", "transaction", "debit"
        else:
            body = (f"INR {inr(amt)} credited to A/c no. XX{mask} on {ts:%d-%m-%Y %H:%M:%S} IST. Info- NEFT/{ref}/ACME CORP. "
                    f"Avl Bal-INR {inr(amt * 3)} - Axis Bank")
            sender, kind, direction = "VM-AXISBK-S", "transaction", "credit"
        out.append(RawMessage("sms", sender, ts, body, truth={
            "kind": kind, "template": f"heldout_{style}", "txn_id": None,
            "expect": {"amount": str(amt.quantize(Decimal('0.01'))), "direction": direction, "mask": mask, "date": ts.date().isoformat()}}))
    return out
