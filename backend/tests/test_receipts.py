import json
from pathlib import Path

from app.core.config import get_settings


def test_samples_exist_and_parse(demo_client):
    samples = demo_client.get("/api/v1/receipts/samples").json()
    names = {s["name"] for s in samples}
    assert {"nilgiris.png", "a2b-cash.png", "act-invoice.pdf"} <= names


def test_pdf_bill_parses_and_links_to_payment(demo_client):
    pdf = (get_settings().data_dir / "samples" / "receipts" / "act-invoice.pdf").read_bytes()
    r = demo_client.post("/api/v1/receipts/parse-pdf", files={"file": ("act.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["fields"]["total"]["value"]
    assert rec["suggested_match"] is not None and "ACT" in rec["suggested_match"]["merchant"]


def test_ocr_lines_extract_fields_and_commit(demo_client):
    meta = json.loads((get_settings().data_dir / "samples" / "receipts" / "samples.json").read_text())
    nil = next(m for m in meta if m["name"] == "nilgiris.png")
    lines = [{"text": "NILGIRIS SUPERMARKET", "confidence": 93, "bbox": {"x0": 120, "y0": 30, "x1": 640, "y1": 60}},
             {"text": "No. 12, Velachery Main Road", "confidence": 90, "bbox": {"x0": 28, "y0": 70, "x1": 500, "y1": 100}},
             {"text": "GSTIN: 33AABCN4521R1ZQ", "confidence": 91, "bbox": {"x0": 28, "y0": 150, "x1": 500, "y1": 180}},
             {"text": "Date: " + "/".join(reversed(nil["date"].split("-"))) + "   Time: 18:10", "confidence": 90,
              "bbox": {"x0": 28, "y0": 190, "x1": 600, "y1": 220}},
             {"text": "GRAND TOTAL " + f"{float(nil['total']):,.2f}", "confidence": 92, "bbox": {"x0": 28, "y0": 600, "x1": 730, "y1": 630}}]
    png = (get_settings().data_dir / "samples" / "receipts" / "nilgiris.png").read_bytes()
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
