"""Optional uploads: scanned receipts (OCR runs in the browser) and digital PDF bills."""

from __future__ import annotations

import datetime as dt
import io
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.money import D
from app.jobs.runner import runner
from app.models import Receipt
from app.schemas.common import iso
from app.schemas.serialize import Lookups, txn_out
from app.services import receipts as svc

router = APIRouter(prefix="/receipts", tags=["receipts"])
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_BYTES = 12 * 1024 * 1024


class CommitBody(BaseModel):
    merchant: str = Field(min_length=1, max_length=120)
    date: dt.date
    total: float = Field(gt=0, lt=1e8)
    items: list[dict[str, Any]] = Field(default_factory=list)
    category_id: int | None = None
    transaction_id: int | None = None
    as_bill: bool = False  # an unpaid bill (e.g. a PDF electricity bill): record it as due, not as a payment
    due_date: dt.date | None = None


def receipt_out(db, user, r: Receipt) -> dict[str, Any]:  # noqa: ANN001
    fields = {k: v for k, v in (r.fields or {}).items() if k != "merchant_raw"}
    match = None
    if r.status == "parsed":
        m = svc.suggest_match(db, user, fields)
        match = txn_out(m, Lookups(db, user.id)) if m else None
    linked = None
    if r.transaction_id:
        from app.models import Transaction

        t = db.get(Transaction, r.transaction_id)
        linked = txn_out(t, Lookups(db, user.id)) if t else None
    return {"id": r.id, "filename": r.filename, "kind": r.kind, "status": r.status, "fields": fields, "image_size": r.image_size,
            "file_url": f"/api/v1/receipts/{r.id}/file", "suggested_match": match, "transaction": linked,
            "created_at": iso(r.created_at), "ocr_text": r.ocr_text[:4000]}


def _store(data: bytes, ext: str) -> Path:
    folder = get_settings().uploads_dir / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    return path


@router.post("/parse")
async def parse_image(db: DB, user: CurrentUser, file: UploadFile = File(...), ocr: str = Form(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 12 MB.")
    ext = IMAGE_TYPES.get(file.content_type or "", Path(file.filename or "").suffix.lower() or ".png")
    try:
        payload = json.loads(ocr)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "OCR result is not valid JSON") from exc
    fields = svc.extract_fields(db, user, payload.get("lines", []), payload.get("text"))
    r = Receipt(user_id=user.id, filename=(file.filename or "receipt")[:200], file_path=str(_store(data, ext)), kind="image",
                status="parsed", ocr_text=str(payload.get("text", ""))[:20000], words=[], fields=fields,
                image_size={"width": payload.get("width"), "height": payload.get("height")})
    db.add(r)
    db.flush()
    return receipt_out(db, user, r)


@router.post("/parse-pdf")
async def parse_pdf(db: DB, user: CurrentUser, file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "PDF is larger than 12 MB.")
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages[:5])
    except Exception as exc:  # noqa: BLE001 - corrupt or encrypted PDFs
        raise HTTPException(422, "Couldn't read that PDF (it may be scanned or password-protected). Try a photo instead.") from exc
    if not text.strip():
        raise HTTPException(422, "This PDF has no text layer (it's a scan). Upload it as an image so it can be read with OCR.")
    fields = svc.extract_fields(db, user, [], text)
    r = Receipt(user_id=user.id, filename=(file.filename or "bill.pdf")[:200], file_path=str(_store(data, ".pdf")), kind="pdf",
                status="parsed", ocr_text=text[:20000], fields=fields)
    db.add(r)
    db.flush()
    return receipt_out(db, user, r)


@router.get("")
def list_receipts(db: DB, user: CurrentUser) -> list[dict]:
    rows = db.scalars(select(Receipt).where(Receipt.user_id == user.id, Receipt.status != "discarded").order_by(Receipt.id.desc()).limit(50)).all()
    return [{"id": r.id, "filename": r.filename, "kind": r.kind, "status": r.status, "created_at": iso(r.created_at),
             "total": (r.fields.get("total") or {}).get("value"), "merchant": (r.fields.get("merchant") or {}).get("value")} for r in rows]


@router.get("/{receipt_id}")
def get_receipt(receipt_id: int, db: DB, user: CurrentUser) -> dict:
    r = db.get(Receipt, receipt_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Receipt not found")
    return receipt_out(db, user, r)


@router.get("/{receipt_id}/file")
def receipt_file(receipt_id: int, db: DB, user: CurrentUser) -> FileResponse:
    r = db.get(Receipt, receipt_id)
    if r is None or r.user_id != user.id or not Path(r.file_path).exists():
        raise HTTPException(404, "File not found")
    return FileResponse(r.file_path)


@router.post("/{receipt_id}/commit")
def commit_receipt(receipt_id: int, body: CommitBody, db: DB, user: CurrentUser) -> dict:
    r = db.get(Receipt, receipt_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Receipt not found")
    if r.status == "committed":
        raise HTTPException(409, "This receipt was already saved.")
    if body.as_bill:
        up = svc.save_as_bill(db, user, r, body.merchant.strip(), D(body.total), body.due_date or body.date)
        runner.enqueue("user_analytics", user_id=user.id, db=db)
        return {"ok": True, "bill": {"id": up.id, "payee": up.payee, "amount": float(up.amount), "due_date": up.due_date.isoformat()}}
    txn = svc.commit(db, user, r, body.merchant.strip(), body.date, D(body.total), body.items, body.category_id, body.transaction_id)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"ok": True, "transaction": txn_out(txn, Lookups(db, user.id)), "linked": body.transaction_id is not None}


@router.delete("/{receipt_id}")
def discard(receipt_id: int, db: DB, user: CurrentUser) -> dict:
    r = db.get(Receipt, receipt_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(404, "Receipt not found")
    r.status = "discarded"
    return {"ok": True}
