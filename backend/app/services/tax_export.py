"""Tax summary exports: CSV (category-wise annual totals + deductions) and a one-page PDF (ReportLab)."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import fmt_inr
from app.models import Category, Transaction, User
from app.services.tax import YEARS, tax_summary


def category_totals(db: Session, user: User, year: str) -> list[tuple[str, str, Decimal]]:
    cfg = YEARS[year]
    rows = db.execute(select(Category.name, Transaction.direction, func.sum(Transaction.amount)).join(Category).where(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.is_transfer.is_(False),
        Transaction.txn_date >= cfg["start"], Transaction.txn_date <= cfg["end"]).group_by(Category.name, Transaction.direction)
        .order_by(func.sum(Transaction.amount).desc())).all()
    return [(n, d, v or Decimal(0)) for n, d, v in rows]


def export_csv(db: Session, user: User, year: str) -> str:
    s = tax_summary(db, user, year)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"FinPilot AI tax summary — {s['label']} ({s['act']})"])
    w.writerow([s["disclaimer"]])
    w.writerow([])
    w.writerow(["Regime", "Taxable income", "Tax before rebate", "Rebate", "Surcharge", "Cess", "Total tax"])
    for name in ("old", "new"):
        r = s["regimes"][name]
        w.writerow([name, r["taxable"], r["slab_tax"], r["rebate"], r["surcharge"], r["cess"], r["total"]])
    w.writerow([])
    w.writerow(["Old-regime deductions", "Amount"])
    for d in s["regimes"]["old"]["deductions"]:
        w.writerow([d["name"], d["amount"]])
    w.writerow([])
    w.writerow(["Category", "Direction", "Total for the year"])
    for name, direction, total in category_totals(db, user, year):
        w.writerow([name, direction, f"{total:.2f}"])
    return buf.getvalue()


def export_pdf(db: Session, user: User, year: str) -> bytes:
    s = tax_summary(db, user, year)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Tax summary {s['label']}")
    st = getSampleStyleSheet()
    rupee = lambda v: fmt_inr(Decimal(str(v))).replace("₹", "Rs ")  # noqa: E731  (base-14 fonts have no ₹ glyph)
    story = [Paragraph(f"Tax summary — {s['label']}", st["Title"]),
             Paragraph(f"{user.name} · {s['act']} · as of {s['as_of']}", st["Normal"]), Spacer(1, 6 * mm),
             Paragraph(s["recommendation"]["text"].replace("₹", "Rs "), st["Heading3"])]
    table = [["", "Old regime", "New regime"]]
    for label, key in (("Taxable income", "taxable"), ("Tax before rebate", "slab_tax"), ("Rebate (87A)", "rebate"),
                       ("Surcharge", "surcharge"), ("Health & education cess", "cess"), ("Total tax", "total")):
        table.append([label, rupee(s["regimes"]["old"][key]), rupee(s["regimes"]["new"][key])])
    t = Table(table, colWidths=[70 * mm, 45 * mm, 45 * mm])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.grey),
                           ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [t, Spacer(1, 6 * mm), Paragraph("Deductions detected (old regime)", st["Heading3"])]
    ded = [[d["name"], rupee(d["amount"])] for d in s["regimes"]["old"]["deductions"]]
    dt = Table(ded, colWidths=[115 * mm, 45 * mm])
    dt.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    story += [dt, Spacer(1, 6 * mm)]
    if s["headroom"]:
        story.append(Paragraph("Headroom", st["Heading3"]))
        for h in s["headroom"]:
            story.append(Paragraph("• " + h["tip"].replace("₹", "Rs "), st["Normal"]))
        story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(s["disclaimer"], st["Italic"]))
    doc.build(story)
    return buf.getvalue()
