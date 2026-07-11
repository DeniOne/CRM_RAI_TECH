import json
import os
import time
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_session
from app.models import Document, DocumentTemplate, Lead
from app.services.document_service import (
    extract_placeholders, generate_document, convert_to_pdf, build_replacements, DEFAULT_PLACEHOLDERS
)

router = APIRouter()


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request, session: AsyncSession = Depends(get_session)):
    from app.main import templates
    user = await require_role("admin")(request, session)

    result = await session.execute(
        select(DocumentTemplate).order_by(DocumentTemplate.doc_type, DocumentTemplate.name)
    )
    template_list = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="upload_template.html",
        context={"current_user": user, "templates_list": template_list},
    )


@router.post("/templates/upload")
async def upload_template(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    doc_type: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Только .docx файлы")

    ts = int(time.time())
    filename = f"{doc_type}_{name}_{ts}.docx"
    save_path = str(settings.DOCX_TEMPLATES_DIR / filename)
    os.makedirs(settings.DOCX_TEMPLATES_DIR, exist_ok=True)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    placeholders = extract_placeholders(save_path)

    doc_template = DocumentTemplate(
        name=name,
        doc_type=doc_type,
        file_path=save_path,
        placeholders=json.dumps(placeholders),
        is_active=True,
    )
    session.add(doc_template)
    await session.commit()

    result = await session.execute(
        select(DocumentTemplate).order_by(DocumentTemplate.doc_type, DocumentTemplate.name)
    )
    template_list = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="upload_template.html",
        context={"current_user": user, "templates_list": template_list, "uploaded_placeholders": placeholders},
    )


@router.post("/templates/{template_id}/delete")
async def delete_template(
    request: Request,
    template_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role("admin")(request, session)

    result = await session.execute(select(DocumentTemplate).where(DocumentTemplate.id == template_id))
    doc_template = result.scalar_one_or_none()
    if not doc_template:
        raise HTTPException(status_code=404)

    doc_template.is_active = False
    await session.commit()

    result = await session.execute(
        select(DocumentTemplate).order_by(DocumentTemplate.doc_type, DocumentTemplate.name)
    )
    template_list = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="upload_template.html",
        context={"current_user": user, "templates_list": template_list},
    )


@router.get("/leads/{lead_id}/documents", response_class=HTMLResponse)
async def lead_documents(
    request: Request,
    lead_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    docs_result = await session.execute(
        select(Document).where(Document.lead_id == lead_id).order_by(Document.created_at.desc())
    )
    documents = docs_result.scalars().all()

    tmpl_result = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.is_active == True).order_by(DocumentTemplate.doc_type)
    )
    active_templates = tmpl_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/documents_list.html",
        context={
            "current_user": user,
            "documents": documents,
            "active_templates": active_templates,
            "lead_id": lead_id,
        },
    )


@router.get("/templates/{template_id}/fields", response_class=HTMLResponse)
async def template_fields(
    request: Request,
    template_id: int,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(select(DocumentTemplate).where(DocumentTemplate.id == template_id))
    doc_template = result.scalar_one_or_none()
    if not doc_template:
        raise HTTPException(status_code=404)

    all_placeholders = json.loads(doc_template.placeholders) if doc_template.placeholders else []
    extra_fields = [p for p in all_placeholders if p not in DEFAULT_PLACEHOLDERS]

    return templates.TemplateResponse(
        request=request,
        name="partials/document_form.html",
        context={"current_user": user, "extra_fields": extra_fields, "template": doc_template},
    )


@router.post("/leads/{lead_id}/documents/generate", response_class=HTMLResponse)
async def generate_doc(
    request: Request,
    lead_id: int,
    template_id: int = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    lead_result = await session.execute(
        select(Lead).where(Lead.id == lead_id).options(
            selectinload(Lead.contacts), selectinload(Lead.region)
        )
    )
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404)

    tmpl_result = await session.execute(select(DocumentTemplate).where(DocumentTemplate.id == template_id))
    doc_template = tmpl_result.scalar_one_or_none()
    if not doc_template:
        raise HTTPException(status_code=404)

    form_data = await request.form()
    extra = {}
    for key, val in form_data.items():
        if key not in ("template_id",) and key not in DEFAULT_PLACEHOLDERS and val:
            extra[key] = val

    replacements = build_replacements(lead, user, extra)

    lead_dir = f"storage/documents/{lead_id}"
    os.makedirs(lead_dir, exist_ok=True)
    ts = int(time.time())
    docx_path = f"{lead_dir}/doc_{ts}.docx"
    pdf_path = f"{lead_dir}/doc_{ts}.pdf"

    generate_document(doc_template.file_path, replacements, docx_path)
    pdf_result = convert_to_pdf(docx_path, pdf_path)

    title = f"{doc_template.doc_type.upper()} для {lead.name}"
    amount = None
    if "amount" in extra:
        try:
            amount = float(extra["amount"])
        except ValueError:
            pass

    document = Document(
        lead_id=lead_id,
        user_id=user.id,
        doc_type=doc_template.doc_type,
        template_id=doc_template.id,
        title=title,
        number=extra.get("number"),
        amount=amount,
        file_path=docx_path,
        file_path_pdf=pdf_result,
        status="draft",
    )
    session.add(document)
    await session.commit()

    docs_result = await session.execute(
        select(Document).where(Document.lead_id == lead_id).order_by(Document.created_at.desc())
    )
    documents = docs_result.scalars().all()

    active_tmpl_result = await session.execute(
        select(DocumentTemplate).where(DocumentTemplate.is_active == True).order_by(DocumentTemplate.doc_type)
    )
    active_templates = active_tmpl_result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="partials/documents_list.html",
        context={
            "current_user": user,
            "documents": documents,
            "active_templates": active_templates,
            "lead_id": lead_id,
        },
    )


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: int, format: str = "docx", session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404)

    if format == "pdf":
        if not doc.file_path_pdf or not os.path.exists(doc.file_path_pdf):
            raise HTTPException(status_code=404, detail="PDF не сгенерирован")
        return FileResponse(doc.file_path_pdf, filename=f"{doc.title}.pdf")
    else:
        if not doc.file_path or not os.path.exists(doc.file_path):
            raise HTTPException(status_code=404)
        return FileResponse(doc.file_path, filename=f"{doc.title}.docx")


@router.post("/documents/{doc_id}/status", response_class=HTMLResponse)
async def update_doc_status(
    request: Request,
    doc_id: int,
    status: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404)

    doc.status = status
    if status == "sent":
        doc.sent_at = datetime.now()

    await session.commit()

    return templates.TemplateResponse(
        request=request,
        name="partials/document_row.html",
        context={"current_user": user, "doc": doc},
    )
