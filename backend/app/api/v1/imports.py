"""Bank-statement import wizard: CSV or Excel (.xlsx/.xls) → column mapping → reconciled transactions."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.v1.ingest import refuse_demo
from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.models import Account
from app.services import csv_import

router = APIRouter(tags=["imports"])
MAX_BYTES = 10 * 1024 * 1024


class NewAccount(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="savings", pattern="^(savings|credit_card|cash|wallet)$")
    institution: str | None = Field(default=None, max_length=80)
    mask: str | None = Field(default=None, pattern=r"^\d{3,4}$")


class CommitBody(BaseModel):
    token: str = Field(pattern=r"^[0-9a-f]{32}$")
    mapping: dict[str, str | None]
    account_id: int | None = None
    new_account: NewAccount | None = None


def _tmp() -> Path:
    p = get_settings().uploads_dir / "csv"
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/imports/csv/preview")
async def preview(user: CurrentUser, file: UploadFile = File(...)) -> dict[str, Any]:
    refuse_demo(user)
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 10 MB.")
    try:
        header, rows = csv_import.read_rows(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = uuid.uuid4().hex
    (_tmp() / f"{token}.data").write_bytes(data)
    (_tmp() / f"{token}.json").write_text(json.dumps({"user": user.id, "filename": file.filename}))
    return {"token": token, "columns": header, "rows": rows[:8], "total": len(rows), "guess": csv_import.guess_mapping(header)}


@router.post("/imports/csv/commit")
def commit(body: CommitBody, db: DB, user: CurrentUser) -> dict[str, Any]:
    refuse_demo(user)
    meta_path, data_path = _tmp() / f"{body.token}.json", _tmp() / f"{body.token}.data"
    if not meta_path.exists() or not data_path.exists() or json.loads(meta_path.read_text()).get("user") != user.id:
        raise HTTPException(404, "Upload expired — choose the file again.")
    account_id = body.account_id
    if body.new_account is not None:
        na = body.new_account
        acct = Account(user_id=user.id, name=na.name.strip(), institution=(na.institution or na.name).strip()[:80], kind=na.kind,
                       mask=na.mask, is_liquid=na.kind != "credit_card")
        db.add(acct)
        db.flush()
        account_id = acct.id
    header, rows = csv_import.read_rows(data_path.read_bytes())
    try:
        res = csv_import.commit_csv(db, user, json.loads(meta_path.read_text()).get("filename") or "statement", header, rows,
                                    body.mapping, account_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    meta_path.unlink(missing_ok=True)
    data_path.unlink(missing_ok=True)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"imported": res.imported, "duplicates": res.duplicates, "skipped": res.skipped, "balance_set": res.balance_set,
            "account_id": account_id}
