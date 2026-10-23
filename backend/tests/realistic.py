"""Realistic messages for tests, dated relative to today: what a real Indian phone inbox looks like (several banks,
a card, a salary credit, UPI payments both ways, a bill, plus the things that must never be stored)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from xml.sax.saxutils import quoteattr

from app.core.timeutil import app_zone


def _ms(day: datetime) -> int:
    return int(day.replace(tzinfo=app_zone()).timestamp() * 1000)


def inbox(today: datetime | None = None) -> list[dict]:
    """[{address, body, date_ms, expect}] — expect: 'debit' | 'credit' | 'skip' (never stored) | 'info'."""
    now = (today or datetime.now()).replace(microsecond=0)

    def at(days_ago: int, hh: int = 10, mm: int = 15) -> datetime:
        return datetime.combine((now - timedelta(days=days_ago)).date(), time(hh, mm))

    def ddmmyy(d: datetime) -> str:
        return d.strftime("%d-%m-%y")

    msgs = []

    def add(days_ago: int, sender: str, body_fn, expect: str, hh: int = 10, mm: int = 15) -> None:
        d = at(days_ago, hh, mm)
        msgs.append({"address": sender, "body": body_fn(d), "date_ms": _ms(d), "expect": expect})

    add(40, "VM-HDFCBK-S", lambda d: f"Update! INR 85,000.00 deposited in HDFC Bank A/c XX4821 on {d:%d-%b-%y} for NEFT Cr-HDFC0000001-ACME SOFTWARE PVT LTD-SALARY OCT-N1234567. Avl bal INR 1,02,340.50. Cheque deposits in A/C are subject to clearing", "credit", 9, 5)
    add(30, "AD-SBIUPI-S", lambda d: f"Dear UPI user A/C X7731 debited by 349.0 on date {d:%d%b%y} trf to SWIGGY Refno 528511234567. If not u? call 1800111109. -SBI", "debit")
    add(28, "JD-ICICIT-S", lambda d: f"INR 2,499.00 spent using ICICI Bank Card XX9034 on {d:%d-%b-%y} on AMAZON PAY INDIA. Avl Limit: INR 1,47,501.00. If not you, call 1800 2662/SMS BLOCK 9034 to 9215676766", "debit")
    add(25, "VK-AXISBK-S", lambda d: f"INR 1,250.00 debited\nA/c no. XX5512\n{d:%d-%m-%y}, 18:42:10\nUPI/P2M/528512345678/BHARAT PETROLEUM\nNot you? SMS BLOCKUPI Cust ID to 919951860002\nAxis Bank", "debit")
    add(22, "BZ-KOTAKB-S", lambda d: f"Received Rs.1500.00 in your Kotak Bank AC X3301 from rahul.k@okhdfcbank on {ddmmyy(d)}.UPI Ref:528512340001.", "credit")
    add(20, "VM-HDFCBK-S", lambda d: f"Sent Rs.18000.00\nFrom HDFC Bank A/C *4821\nTo RAMESH KUMAR\nOn {d:%d/%m/%y}\nRef 528512349999\nNot You?\nCall 18002586161/SMS BLOCK UPI to 7308080808", "debit")
    add(15, "AX-CANBNK-S", lambda d: f"An amount of INR 560.00 has been DEBITED to your account XXX123 on {d:%d/%m/%Y} towards UPI/528512345001/ZEPTO. Total Avail.bal INR 41,220.00. - Canara Bank", "debit")
    add(12, "JM-AIRTEL-S", lambda d: f"Dear Customer, your Airtel bill of Rs.599.00 for 98XXXXXX21 is due on {(d + timedelta(days=10)):%d-%b-%Y}. Pay now on Airtel Thanks app.", "info")
    add(10, "VM-HDFCBK-S", lambda d: f"Spent Rs.649.00 On HDFC Bank Card 7788 At NETFLIX.COM On {d:%Y-%m-%d}:21:14:03 Not You? Call 18002586161", "debit")
    add(6, "VM-HDFCBK-S", lambda d: f"123456 is the OTP for your transaction of Rs.4,999.00 at FLIPKART on HDFC Bank Card 7788. Valid for 5 mins. Do not share it with anyone.", "skip")
    add(5, "VM-ICICIB-P", lambda d: "Pre-approved Personal Loan of Rs.5,00,000 is waiting for you! Get it credited instantly. T&C apply. Click icici.co/xyz", "skip")
    add(4, "+919876543210", lambda d: "Hey, are we still on for dinner tonight? Paid Rs 500 for the tickets btw", "skip")
    add(2, "VM-SBIINB-S", lambda d: f"Dear Customer, Your A/C XXXXX7731 has a debit by transfer of Rs 2,000.00 on {d:%d/%m/%y}. Avl Bal Rs 36,410.25.-SBI", "debit")
    add(1, "VK-AXISBK-S", lambda d: f"INR 1,250.00 credited to A/c no. XX5512 on {d:%d-%m-%y} 11:05:42 towards refund of UPI/528512345678. Avl Bal INR 22,410.00 - Axis Bank", "credit")
    return msgs


def phone_upload(today: datetime | None = None) -> list[dict]:
    """What the Android app uploads: the phone already dropped OTPs, -P promos and personal numbers."""
    return [{k: m[k] for k in ("address", "body", "date_ms")} for m in inbox(today)
            if not (m["address"].startswith("+") or m["address"].endswith("-P") or "OTP" in m["body"])]


def sms_backup_xml(today: datetime | None = None) -> bytes:
    """The same inbox as an Android 'SMS Backup & Restore' export."""
    rows = "".join(f'<sms protocol="0" address={quoteattr(m["address"])} date="{m["date_ms"]}" type="1" body={quoteattr(m["body"])} '
                   f'read="1" status="-1" />' for m in inbox(today))
    return f"<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><smses count=\"{len(inbox(today))}\">{rows}</smses>".encode()
