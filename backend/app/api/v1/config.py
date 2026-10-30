from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.modules.documents.fingerprint import ALLOWED_EXTENSIONS
from app.shared.enums import CurrencyCode
from app.shared.money import CURRENCY_MINOR_UNITS

router = APIRouter(prefix="/config", tags=["config"])


class CurrencyOption(BaseModel):
    code: CurrencyCode
    minor_units: int


class PublicConfig(BaseModel):
    app_name: str
    registration_mode: Literal["open", "disabled"]
    upload_max_file_bytes: int
    upload_max_files: int
    allowed_extensions: list[str]
    direct_upload_available: bool
    currencies: list[CurrencyOption]


@router.get("/public", response_model=PublicConfig)
def get_public_config() -> PublicConfig:
    settings = get_settings()
    direct_upload = settings.originals_storage == "uploadthing" and bool(settings.uploadthing_token)
    return PublicConfig(
        app_name=getattr(settings, "app_name", "DocIntel AI"),
        registration_mode=settings.registration_mode,
        upload_max_file_bytes=settings.upload_max_file_bytes,
        upload_max_files=settings.upload_max_files,
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
        direct_upload_available=direct_upload,
        currencies=[CurrencyOption(code=c, minor_units=CURRENCY_MINOR_UNITS[c]) for c in CurrencyCode],
    )
