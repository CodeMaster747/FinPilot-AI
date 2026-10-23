import json
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def samples(demo) -> Path:
    """Receipt images and a PDF bill drawn from the demo persona's own purchases (test fixtures only)."""
    from app.seed.persona import build_persona
    from app.seed.receipt_images import generate_samples

    out = Path(tempfile.mkdtemp(prefix="finpilot-receipts-"))
    generate_samples(build_persona(date.today(), cutoff=datetime.now()), out)
    return out


def test_pdf_bill_parses_and_links_to_payment(demo_client, samples):
    pdf = (samples / "act-invoice.pdf").read_bytes()
    r = demo_client.post("/api/v1/receipts/parse-pdf", files={"file": ("act.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["fields"]["total"]["value"]
    assert rec["suggested_match"] is not None and "ACT" in rec["suggested_match"]["merchant"]


def test_ocr_lines_extract_fields_and_commit(demo_client, samples):
    meta = json.loads((samples / "samples.json").read_text())
    nil = next(m for m in meta if m["name"] == "nilgiris.png")
    lines = [{"text": "NILGIRIS SUPERMARKET", "confidence": 93, "bbox": {"x0": 120, "y0": 30, "x1": 640, "y1": 60}},
             {"text": "No. 12, Velachery Main Road", "confidence": 90, "bbox": {"x0": 28, "y0": 70, "x1": 500, "y1": 100}},
             {"text": "GSTIN: 33AABCN4521R1ZQ", "confidence": 91, "bbox": {"x0": 28, "y0": 150, "x1": 500, "y1": 180}},
             {"text": "Date: " + "/".join(reversed(nil["date"].split("-"))) + "   Time: 18:10", "confidence": 90,
              "bbox": {"x0": 28, "y0": 190, "x1": 600, "y1": 220}},
             {"text": "GRAND TOTAL " + f"{float(nil['total']):,.2f}", "confidence": 92, "bbox": {"x0": 28, "y0": 600, "x1": 730, "y1": 630}}]
    png = (samples / "nilgiris.png").read_bytes()
    r = demo_client.post("/api/v1/receipts/parse", files={"file": ("n.png", png, "image/png")},
                         data={"ocr": json.dumps({"lines": lines, "text": "\n".join(l["text"] for l in lines), "width": 760, "height": 900})})
    rec = r.json()
    assert rec["fields"]["merchant"]["value"] == "Nilgiris"
    assert rec["fields"]["gstin"]["value"] == "33AABCN4521R1ZQ"
    assert float(rec["fields"]["total"]["value"]) == float(nil["total"])
    match = rec["suggested_match"]
    assert match and match["merchant"] == "Nilgiris"
    out = demo_client.post(f"/api/v1/receipts/{rec['id']}/commit", json={
        "merchant": "Nilgiris", "date": match["date"], "total": float(nil["total"]), "items": [], "transaction_id": match["id"]}).json()
    assert out["linked"] and out["transaction"]["id"] == match["id"]


def test_an_unpaid_bill_is_saved_as_due_not_as_spending(new_user, tmp_path):
    from app.seed.receipt_images import render_bill_pdf

    c = new_user
    path = tmp_path / "bill.pdf"
    render_bill_pdf(path, date.today(), Decimal("1179.00"), "ACT9988776")
    rec = c.post("/api/v1/receipts/parse-pdf", files={"file": ("bill.pdf", path.read_bytes(), "application/pdf")}).json()
    assert float(rec["fields"]["total"]["value"]) == 1179.0
    due = (date.today() + timedelta(days=12)).isoformat()
    out = c.post(f"/api/v1/receipts/{rec['id']}/commit", json={"merchant": "ACT Fibernet", "date": date.today().isoformat(),
                                                                "total": 1179, "items": [], "as_bill": True, "due_date": due}).json()
    assert out["bill"]["due_date"] == due
    assert c.get("/api/v1/transactions").json()["total"] == 0  # nothing was spent yet
    assert any(u["payee"] == "ACT Fibernet" and u["status"] == "upcoming" for u in c.get("/api/v1/upcoming").json())
