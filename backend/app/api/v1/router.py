from fastapi import APIRouter

from app.api.v1 import (
    accounts,
    analysis,
    auth,
    dashboard,
    imports,
    ingest,
    messages,
    picks,
    planning,
    receipts,
    review,
    settings,
    sources,
    system,
    transactions,
)

api_router = APIRouter()
for module in (system, auth, sources, ingest, messages, review, transactions, accounts, analysis, planning, picks, dashboard,
               receipts, settings, imports):
    api_router.include_router(module.router)
