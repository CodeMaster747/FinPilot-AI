"""Downloadable sample files for the import features (regenerated with the demo so dates stay current):
an Android 'SMS Backup & Restore' XML, an SMS CSV, an .mbox mailbox and a bank-statement CSV."""

from __future__ import annotations

import csv
import io
import mailbox
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path
from xml.sax.saxutils import quoteattr

from app.seed.emails import render_emails
from app.seed.persona import Persona
from app.seed.sms import render_sms

SAMPLES = [
    {"name": "sms_backup.xml", "label": "SMS backup (Android 'SMS Backup & Restore' XML) — last 3 months", "kind": "sms"},
    {"name": "sms_messages.csv", "label": "SMS export as CSV (date, sender, message) — last month", "kind": "sms"},
    {"name": "inbox.mbox", "label": "Mailbox archive (.mbox, e.g. Google Takeout) — last 3 months", "kind": "email"},
    {"name": "hdfc_statement.csv", "label": "HDFC savings statement CSV — last 2 months", "kind": "csv"},
]


def write_samples(persona: Persona, out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    end = datetime.combine(persona.end, datetime.max.time())
    sms = render_sms(persona)
    recent3 = [m for m in sms if m.received_at >= end - timedelta(days=92)]
    xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>', f'<smses count="{len(recent3)}">']
    for m in recent3:
        ms = int(m.received_at.timestamp() * 1000)
        xml.append(f'  <sms protocol="0" address={quoteattr(m.sender)} date="{ms}" type="1" subject="null" '
                   f'body={quoteattr(m.body)} read="1" status="-1" readable_date={quoteattr(m.received_at.strftime("%d %b %Y %I:%M:%S %p"))} />')
    xml.append("</smses>")
    (out / "sms_backup.xml").write_text("\n".join(xml), encoding="utf-8")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "sender", "message"])
    for m in (m for m in sms if m.received_at >= end - timedelta(days=31)):
        w.writerow([m.received_at.strftime("%Y-%m-%d %H:%M:%S"), m.sender, m.body])
    (out / "sms_messages.csv").write_text(buf.getvalue(), encoding="utf-8")
    box_path = out / "inbox.mbox"
    box_path.unlink(missing_ok=True)
    box = mailbox.mbox(str(box_path))
    for m in (m for m in render_emails(persona) if m.received_at >= end - timedelta(days=92)):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = m.sender, "aarav.sharma@example.com", m.subject or ""
        msg["Date"] = format_datetime(m.received_at.astimezone())
        msg["Message-ID"] = make_msgid(domain="sample.finpilot")
        msg.set_content(m.body)
        if m.html:
            msg.add_alternative(m.html, subtype="html")
        box.add(msg)
    box.flush()
    box.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["HDFC BANK LTD — Statement of account", "", "", "", "", ""])
    w.writerow(["Account No: XXXXXXXX4521", "", "", "", "", ""])
    w.writerow(["Date", "Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"])
    for t in (t for t in persona.txns if t.account == "hdfc" and t.ts >= end - timedelta(days=62)):
        narr = f"{'UPI' if t.channel == 'upi' else t.channel.upper()}-{t.payee}" + (f"-{t.vpa}" if t.vpa else "")
        w.writerow([t.ts.strftime("%d/%m/%y"), narr, t.ref, f"{t.amount:.2f}" if t.direction == "debit" else "",
                    f"{t.amount:.2f}" if t.direction == "credit" else "", f"{t.balance_after:.2f}"])
    (out / "hdfc_statement.csv").write_text(buf.getvalue(), encoding="utf-8")
    return SAMPLES
