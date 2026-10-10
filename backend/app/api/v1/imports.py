"""Bank-statement CSV wizard and the downloadable sample files."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.jobs.runner import runner
from app.seed.import_samples import SAMPLES
from app.services import csv_import

router = APIRouter(tags=["imports"])


class CommitBody(BaseModel):
    token: str
    mapping: dict[str, str | None]
    account_id: int | None = None


def _tmp() -> Path:
    p = get_settings().uploads_dir / "csv"
    p.mkdir(parents=True, exist_ok=True)
    return p


def samples_dir() -> Path:
    return get_settings().data_dir / "samples" / "imports"


@router.post("/imports/csv/preview")
async def preview(user: CurrentUser, file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 10 MB.")
    try:
        header, rows = csv_import.read_rows(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = uuid.uuid4().hex
    (_tmp() / f"{token}.csv").write_bytes(data)
    (_tmp() / f"{token}.json").write_text(json.dumps({"user": user.id, "filename": file.filename}))
    return {"token": token, "columns": header, "rows": rows[:8], "total": len(rows), "guess": csv_import.guess_mapping(header)}


@router.post("/imports/csv/commit")
def commit(body: CommitBody, db: DB, user: CurrentUser) -> dict[str, Any]:
    meta_path, data_path = _tmp() / f"{body.token}.json", _tmp() / f"{body.token}.csv"
    if not meta_path.exists() or json.loads(meta_path.read_text()).get("user") != user.id:
        raise HTTPException(404, "Upload expired — choose the file again.")
    header, rows = csv_import.read_rows(data_path.read_bytes())
    try:
        res = csv_import.commit_csv(db, user, json.loads(meta_path.read_text()).get("filename") or "statement.csv", header, rows,
                                    body.mapping, body.account_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    meta_path.unlink(missing_ok=True)
    data_path.unlink(missing_ok=True)
    runner.enqueue("user_analytics", user_id=user.id, db=db)
    return {"imported": res.imported, "duplicates": res.duplicates, "skipped": res.skipped}


@router.get("/samples")
def list_samples(user: CurrentUser) -> list[dict]:
    return [{**s, "url": f"/api/v1/samples/{s['name']}"} for s in SAMPLES if (samples_dir() / s["name"]).exists()]


@router.get("/samples/{name}")
def get_sample(name: str, user: CurrentUser) -> FileResponse:
    path = (samples_dir() / name).resolve()
    if path.parent != samples_dir().resolve() or not path.exists():
        raise HTTPException(404, "Sample not found")
    return FileResponse(path, filename=name)
