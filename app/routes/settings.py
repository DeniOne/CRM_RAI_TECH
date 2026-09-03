"""Настройки компании: реквизиты, логотип, НДС + редактируемые тексты печатных
форм (фаза 20). Только admin — реквизиты и тексты документов чувствительны.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote as urlquote

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_session
from app.services import company_service as cs

router = APIRouter(prefix="/settings", tags=["settings"])

ALLOWED_LOGO = {"png", "jpg", "jpeg"}
MAX_LOGO_BYTES = 2 * 1024 * 1024

COMPANY_FIELDS = [
    "name", "inn", "kpp", "ogrn", "legal_address", "phone", "email", "site",
    "bank_name", "bank_bic", "bank_account", "bank_corr_account", "director_name",
    "tax_note",
]


async def _admin_guard(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    await require_role("admin")(request, session)
    return user


@router.get("")
async def settings_page(request: Request, msg: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _admin_guard(request, session)
    profile = await cs.get_profile(session)
    tpl = await cs.get_template(session, "quote")
    return templates.TemplateResponse(
        request=request,
        name="settings_company.html",
        context={
            "current_user": user, "profile": profile, "tpl": tpl, "msg": msg,
            "placeholder_docs": cs.PLACEHOLDER_DOCS,
        },
    )


@router.post("/company")
async def save_company(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    await _admin_guard(request, session)
    profile = await cs.get_profile(session)
    form = await request.form()
    for field in COMPANY_FIELDS:
        value = (form.get(field) or "").strip()
        setattr(profile, field, value or None)
    await session.commit()
    return RedirectResponse(f"/settings?msg={urlquote('Реквизиты сохранены')}", status_code=303)


@router.post("/company/logo")
async def upload_logo(
    request: Request,
    file: UploadFile = None,
    session: AsyncSession = Depends(get_session),
):
    await _admin_guard(request, session)
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="Файл не передан")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_LOGO:
        raise HTTPException(status_code=400, detail="Только PNG или JPG")
    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=400, detail="Файл больше 2 МБ")
    fname = f"logo.{ext}"
    (settings.COMPANY_DIR / fname).write_bytes(data)
    profile = await cs.get_profile(session)
    profile.logo_path = fname
    await session.commit()
    return RedirectResponse(f"/settings?msg={urlquote('Логотип загружен')}", status_code=303)


@router.get("/logo")
async def company_logo():
    """Логотип для печатных форм. Данные читаются роутом печати напрямую из
    файла (data-URI), этот роут — для превью в настройках."""
    for ext in ALLOWED_LOGO:
        path = settings.COMPANY_DIR / f"logo.{ext}"
        if path.is_file():
            return FileResponse(path)
    raise HTTPException(status_code=404)


@router.post("/templates/quote")
async def save_quote_template(
    request: Request,
    intro: str = Form(None),
    conditions: str = Form(None),
    signature: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    await _admin_guard(request, session)
    tpl = await cs.get_template(session, "quote")
    tpl.intro = intro or None
    tpl.conditions = conditions or None
    tpl.signature = signature or None
    await session.commit()
    return RedirectResponse(f"/settings?msg={urlquote('Тексты КП сохранены')}", status_code=303)
