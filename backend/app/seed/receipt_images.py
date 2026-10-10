"""Sample receipts for the /scan page: printed-receipt PNGs (Pillow) and a digital PDF bill (ReportLab).

Generated from the demo persona's *current* data, so scanning a sample enriches a real transaction that
arrived by SMS — the reconciliation story end to end. One sample is rotated and noisy to show the OCR
coping with a phone photo; one is a cash purchase with no bank alert (creates a new transaction).
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.seed.persona import Persona, TruthTxn

WIDTH = 760


def _font(bold: bool = False, size: int = 26) -> ImageFont.FreeTypeFont:
    import matplotlib

    name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name), size)


def _money(a: Decimal) -> str:
    return f"{a:,.2f}"


def render_receipt(title: str, lines_top: list[str], items: list[tuple[str, int, Decimal]], when: datetime, gstin: str | None,
                   tax_rate: Decimal | None, payment: str, footer: str = "THANK YOU! VISIT AGAIN") -> tuple[Image.Image, Decimal]:
    rows: list[tuple[str, str, bool]] = []  # (left, right, bold)
    rows.append((title, "", True))
    rows += [(t, "", False) for t in lines_top]
    if gstin:
        rows.append((f"GSTIN: {gstin}", "", False))
    rows.append((f"Date: {when:%d/%m/%Y}   Time: {when:%H:%M}", "", False))
    rows.append(("-" * 44, "", False))
    subtotal = Decimal(0)
    for name, qty, price in items:
        amt = price * qty
        subtotal += amt
        left = f"{name[:24]}"
        rows.append((left, f"{qty} x {price:.2f}  {_money(amt)}" if qty > 1 else _money(amt), False))
    rows.append(("-" * 44, "", False))
    total = subtotal
    if tax_rate:
        half = (subtotal * tax_rate / 2 / 100).quantize(Decimal("0.01"))
        rows.append(("Sub Total", _money(subtotal), False))
        rows.append((f"CGST @{tax_rate / 2}%", _money(half), False))
        rows.append((f"SGST @{tax_rate / 2}%", _money(half), False))
        total = subtotal + 2 * half
    rows.append(("GRAND TOTAL", _money(total), True))
    rows.append((f"Paid by {payment}", "", False))
    rows.append(("", "", False))
    rows.append((footer, "", False))
    font, bold = _font(False, 24), _font(True, 26)
    lh = 40
    img = Image.new("RGB", (WIDTH, 60 + lh * len(rows)), "white")
    draw = ImageDraw.Draw(img)
    y = 30
    for left, right, is_bold in rows:
        f = bold if is_bold else font
        if right:
            draw.text((28, y), left, fill="black", font=f)
            w = draw.textlength(right, font=f)
            draw.text((WIDTH - 28 - w, y), right, fill="black", font=f)
        else:
            w = draw.textlength(left, font=f)
            x = (WIDTH - w) / 2 if is_bold or left.startswith(("THANK", "Ph", "No.")) else 28
            draw.text((x, y), left, fill="black", font=f)
        y += lh
    return img, total


def photo_effect(img: Image.Image, degrees: float = 2.2, seed: int = 3) -> Image.Image:
    rng = random.Random(seed)
    canvas = Image.new("RGB", (img.width + 80, img.height + 80), (232, 228, 218))
    canvas.paste(img, (40, 40))
    canvas = canvas.rotate(degrees, resample=Image.BICUBIC, expand=True, fillcolor=(232, 228, 218))
    px = canvas.load()
    for _ in range(canvas.width * canvas.height // 60):
        x, y = rng.randrange(canvas.width), rng.randrange(canvas.height)
        v = rng.randint(150, 230)
        px[x, y] = (v, v, v)
    return canvas.filter(ImageFilter.GaussianBlur(0.6))


def render_bill_pdf(path: Path, when: date, amount: Decimal, account: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, h - 25 * mm, "ACT Fibernet")
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, h - 31 * mm, "Atria Convergence Technologies Ltd · GSTIN: 33AACCA1234F1Z5")
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, h - 45 * mm, "TAX INVOICE")
    c.setFont("Helvetica", 11)
    base = (amount / Decimal("1.18")).quantize(Decimal("0.01"))
    tax = amount - base
    rows = [("Account No", account), ("Invoice Date", f"{when:%d/%m/%Y}"), ("Plan", "ACT Blaze 150 Mbps"),
            ("Plan charges", f"{base:,.2f}"), ("CGST @9%", f"{(tax / 2):,.2f}"), ("SGST @9%", f"{(tax - tax / 2):,.2f}"),
            ("Total Amount Payable", f"{amount:,.2f}"), ("Due Date", f"{when + timedelta(days=5):%d/%m/%Y}")]
    y = h - 58 * mm
    for k, v in rows:
        c.drawString(20 * mm, y, k)
        c.drawRightString(w - 20 * mm, y, v)
        y -= 8 * mm
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(20 * mm, y - 6 * mm, "This is a computer generated invoice.")
    c.save()


def _latest(persona: Persona, pred) -> TruthTxn | None:  # noqa: ANN001
    found = [t for t in persona.txns if pred(t)]
    return found[-1] if found else None


def generate_samples(persona: Persona, out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*"):
        old.unlink()
    meta: list[dict] = []
    nil = _latest(persona, lambda t: t.merchant == "Nilgiris" and t.items)
    if nil:
        img, total = render_receipt("NILGIRIS SUPERMARKET", ["No. 12, Velachery Main Road", "Chennai - 600042", "Ph: 044-2245 1100"],
                                    nil.items, nil.ts, "33AABCN4521R1ZQ", None, "HDFC Debit Card XX4521")
        img.save(out_dir / "nilgiris.png")
        meta.append({"name": "nilgiris.png", "label": "Nilgiris supermarket (matches a card payment)", "kind": "image", "total": str(total),
                     "merchant": "Nilgiris", "date": nil.ts.date().isoformat()})
    dec = _latest(persona, lambda t: t.merchant == "Decathlon" and t.items)
    if dec:
        img, total = render_receipt("DECATHLON SPORTS INDIA", ["Phoenix Marketcity, Velachery", "Chennai - 600042"], dec.items, dec.ts,
                                    "33AAECD1234K1Z9", None, "HDFC Debit Card XX4521", "Store #3321  Keep your receipt")
        photo_effect(img).save(out_dir / "decathlon-photo.jpg", quality=88)
        meta.append({"name": "decathlon-photo.jpg", "label": "Decathlon — a tilted phone photo", "kind": "image", "total": str(total),
                     "merchant": "Decathlon", "date": dec.ts.date().isoformat()})
    when = datetime.combine(persona.end, datetime.min.time()).replace(hour=13, minute=20)
    items = [("Mini Tiffin", 2, Decimal("185.00")), ("Filter Coffee", 2, Decimal("45.00")), ("Rava Kesari", 1, Decimal("70.00"))]
    img, total = render_receipt("A2B - ADYAR ANANDA BHAVAN", ["Velachery, Chennai"], items, when, "33AAACA2B21C1Z1", Decimal("5"), "CASH")
    img.save(out_dir / "a2b-cash.png")
    meta.append({"name": "a2b-cash.png", "label": "A2B restaurant, paid in cash (no bank alert)", "kind": "image", "total": str(total),
                 "merchant": "A2B", "date": when.date().isoformat()})
    act = _latest(persona, lambda t: t.merchant == "ACT Fibernet")
    if act:
        render_bill_pdf(out_dir / "act-invoice.pdf", act.ts.date(), act.amount, "ACT1042277")
        meta.append({"name": "act-invoice.pdf", "label": "ACT Fibernet invoice (digital PDF)", "kind": "pdf", "total": str(act.amount),
                     "merchant": "ACT Fibernet", "date": act.ts.date().isoformat()})
    (out_dir / "samples.json").write_text(json.dumps(meta, indent=2))
    return meta
