from fastapi import APIRouter

from app.api.v1 import admin, auth, comparisons, documents, invoices, jobs, reviews, search, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, documents, jobs, invoices, reviews, comparisons, search, admin):
    api_router.include_router(module.router)
