"""Счета на оплату и договоры из принятых КП (фаза 21).

Счёт — печатная форма PDF (print/invoice.html) с суммой прописью и реквизитами
сторон; оплата счёта — единственная точка синхронизации сделки (paid) и воронки
(стадия 6 «Оплачено»). Договор — docx через docxtpl.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from urllib.parse import quote as urlquote

from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.models import CompanyProfile, Document, Lead, Quote
from app.services import company_service as cs
from app.services import docgen_service as dg
from app.services.pdf_service import PDFUnavailable, render_pdf

router = APIRouter(prefix="/invoices", tags=["invoices"])

DOC_STATUS_LABELS = {
    "draft": "Черновик",
    "sent": "Отправлен",
    "paid": "Оплачен",
}


async def _user_401(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    return user


async def _doc_or_404(session: AsyncSession, doc_id: int) -> Document:
    doc = (
        await session.execute(
            select(Document).where(Document.id == doc_id)
            .options(
                selectinload(Document.lead).options(
                    selectinload(Lead.assigned_manager), selectinload(Lead.region),
                ),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return doc


async def _quote_for_doc(session: AsyncSession, doc: Document) -> Quote | None:
    if not doc.quote_id:
        return None
    return (
        await session.execute(
            select(Quote).where(Quote.id == doc.quote_id)
            .options(selectinload(Quote.items))
        )
    ).scalar_one_or_none()


@router.post("/create/{quote_id}")
async def create_from_quote(request: Request, quote_id: int, kind: str = Form(...),
                            session: AsyncSession = Depends(get_session)):
    """Счёт или договор по принятому КП. Повторно — возвращает существующий."""
    user = await _user_401(request, session)
    quote = (
        await session.execute(
            select(Quote).where(Quote.id == quote_id)
            .options(selectinload(Quote.items), selectinload(Quote.lead))
        )
    ).scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="КП не найдено")
    if quote.status != "accepted":
        return RedirectResponse(
            f"/quotes/{quote.id}?msg={urlquote('Счёт и договор формируются только по принятому КП')}",
            status_code=303,
        )

    profile = await cs.get_profile(session)
    if kind == "invoice":
        doc = await dg.get_or_create_invoice(session, quote)
        doc.quote_id = quote.id
        await session.commit()
        return RedirectResponse(f"/invoices/{doc.id}", status_code=303)
    elif kind == "contract":
        doc = await dg.get_or_create_contract(session, quote, profile)
        doc.quote_id = quote.id
        await session.commit()
        return RedirectResponse(f"/invoices/{doc.id}", status_code=303)
    raise HTTPException(status_code=400, detail="Неизвестный тип документа")


@router.get("/{doc_id}")
async def doc_view(request: Request, doc_id: int, msg: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _user_401(request, session)
    doc = await _doc_or_404(session, doc_id)
    quote = await _quote_for_doc(session, doc)
    return templates.TemplateResponse(
        request=request,
        name="doc_view.html",
        context={
            "current_user": user, "doc": doc, "quote": quote,
            "status_labels": DOC_STATUS_LABELS, "msg": msg,
        },
    )


@router.post("/{doc_id}/pay")
async def mark_paid(request: Request, doc_id: int, session: AsyncSession = Depends(get_session)):
    user = await _user_401(request, session)
    doc = await _doc_or_404(session, doc_id)
    try:
        await dg.mark_invoice_paid(session, doc)
        await session.commit()
        msg = "Оплата зафиксирована: сделка «Оплачена», лид на стадии 6"
    except Exception as e:  # noqa: BLE001
        await session.rollback()
        msg = str(e)
    return RedirectResponse(f"/invoices/{doc_id}?msg={urlquote(msg)}", status_code=303)


@router.get("/{doc_id}/print")
async def doc_print(request: Request, doc_id: int, preview: str = None, session: AsyncSession = Depends(get_session)):
    """Печатная форма счёта → PDF. Договор печатается из docx (файл)."""
    from app.main import templates

    await _user_401(request, session)
    doc = await _doc_or_404(session, doc_id)
    if doc.doc_type == "contract":
        raise HTTPException(status_code=400, detail="Договор скачивается как docx")
    quote = await _quote_for_doc(session, doc)
    profile = await cs.get_profile(session)
    tpl = await cs.get_template(session, "invoice")

    values = {
        "{Номер}": doc.number,
        "{Дата}": doc.created_at.strftime("%d.%m.%Y"),
        "{Итого}": cs.fmt_money(doc.amount),
        "{Прописью}": dg.money_in_words(doc.amount or 0),
        "{Компания}": profile.name or "",
        "{Клиент}": doc.lead.name,
    }
    buyer_lines = [
        line for line in [
            doc.lead.name,
            f"ИНН {doc.lead.inn}" if doc.lead.inn else "",
            f"КПП {doc.lead.kpp}" if doc.lead.kpp else "",
            doc.lead.legal_address or doc.lead.address or "",
        ] if line
    ]

    html_ = templates.env.get_template("print/invoice.html").render(
        doc=doc, quote=quote, profile=profile, values=values,
        intro=cs.render_text(tpl.intro, values),
        conditions=cs.render_text(tpl.conditions, values),
        signature=cs.render_text(tpl.signature, values),
        total_words=dg.money_in_words(doc.amount or 0),
        buyer_lines=buyer_lines,
        supplier_lines=cs.company_requisites_lines(profile),
    )
    if preview:
        return HTMLResponse(html_)
    try:
        pdf = render_pdf(html_)
    except PDFUnavailable as e:
        return HTMLResponse(
            f"<h2>PDF сейчас недоступен</h2><p>{e}</p><p>На проде добавь ?preview=1 для HTML-версии.</p>",
            status_code=503,
        )
    filename = doc.number.replace("СЧ", "SCH")
    return Response(
        pdf, media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}.pdf"},
    )
