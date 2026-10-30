from fastapi import APIRouter

from app.api.v1 import admin, auth, comparisons, config, documents, invoices, jobs, organization, reviews, search, users

api_router = APIRouter(prefix="/api/v1")
for module in (auth, users, organization, documents, jobs, invoices, reviews, comparisons, search, admin, config):
    api_router.include_router(module.router)
