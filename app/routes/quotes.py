"""КП (коммерческие предложения): билдер, статусы, печатная форма. Фаза 19.

Суммы и снапшоты позиций считает сервер (quote_service), клиентский items_json —
только намерение менеджера. Черновик правится, после отправки — только статусы.
"""

from datetime import date, datetime, timedelta
from urllib.parse import quote as urlquote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.models import Lead, PriceList, Product, ProductPrice, Quote
from app.services import company_service as cs
from app.services import quote_service as qs
from app.services.pdf_service import PDFUnavailable, render_pdf

router = APIRouter(prefix="/quotes", tags=["quotes"])
api_router = APIRouter(prefix="/api/products", tags=["products"])

STATUS_LABELS = {
    "draft": "Черновик",
    "sent": "Отправлено",
    "accepted": "Принято",
    "rejected": "Отказ",
}


async def _user_401(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    return user


async def _lead_or_404(session: AsyncSession, lead_id_raw) -> Lead:
    if not lead_id_raw or not str(lead_id_raw).isdigit():
        raise HTTPException(status_code=400, detail="Не указан лид")
    lead = await session.get(Lead, int(lead_id_raw))
    if not lead:
        raise HTTPException(status_code=404, detail="Лид не найден")
    return lead


async def _quote_or_404(session: AsyncSession, quote_id: int) -> Quote:
    quote = (
        await session.execute(
            select(Quote).where(Quote.id == quote_id)
            .options(
                selectinload(Quote.items),
                # печатная форма трогает assigned_manager и region лида —
                # ленивая загрузка в async-сессии = MissingGreenlet
                selectinload(Quote.lead).options(
                    selectinload(Lead.assigned_manager),
                    selectinload(Lead.region),
                ),
                selectinload(Quote.user),
            )
        )
    ).scalar_one_or_none()
    if not quote:
        raise HTTPException(status_code=404, detail="КП не найдено")
    return quote


def _parse_valid_until(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


async def _default_prices(session: AsyncSession, product_ids: list[int]) -> dict[int, object]:
    if not product_ids:
        return {}
    pricelist = (
        await session.execute(select(PriceList).where(PriceList.is_default == True))  # noqa: E712
    ).scalar_one_or_none()
    if not pricelist:
        return {}
    rows = await session.execute(
        select(ProductPrice.product_id, ProductPrice.price).where(
            ProductPrice.price_list_id == pricelist.id,
            ProductPrice.product_id.in_(product_ids),
        )
    )
    return dict(rows.all())


@api_router.get("/search")
async def products_search(request: Request, q: str = None, session: AsyncSession = Depends(get_session)):
    """Typeahead для билдера КП: u_lower (кириллица) по названию/артикулу."""
    await _user_401(request, session)
    q = (q or "").strip()
    if len(q) < 2:
        return JSONResponse({"items": []})
    like = f"%{q.lower()}%"
    products = (
        (
            await session.execute(
                select(Product)
                .where(
                    Product.is_active == True,  # noqa: E712
                    or_(func.u_lower(Product.name).like(like), func.u_lower(Product.sku).like(like)),
                )
                .order_by(Product.name)
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    prices = await _default_prices(session, [p.id for p in products])
    return JSONResponse({
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "unit": p.unit,
                "price": str(prices.get(p.id)) if prices.get(p.id) is not None else None,
            }
            for p in products
        ]
    })


@router.get("/new")
async def quote_new(
    request: Request,
    lead_id: str = None,
    error: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await _user_401(request, session)
    lead = await _lead_or_404(session, lead_id)
    return templates.TemplateResponse(
        request=request,
        name="quote_form.html",
        context={
            "current_user": user, "lead": lead, "mode": "create", "quote": None,
            "bootstrap_items": [], "error": error,
            "default_valid_until": (datetime.now().date() + timedelta(days=14)).isoformat(),
        },
    )


@router.post("/create")
async def quote_create(
    request: Request,
    lead_id: int = Form(...),
    items_json: str = Form(...),
    valid_until: str = Form(None),
    comment: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    user = await _user_401(request, session)
    lead = await _lead_or_404(session, lead_id)
    try:
        quote = await qs.create_quote(session, lead, user.id, items_json,
                                      _parse_valid_until(valid_until), comment or None)
        await session.commit()
    except ValueError as e:
        return RedirectResponse(
            f"/quotes/new?lead_id={lead.id}&error={urlquote(str(e))}", status_code=303
        )
    return RedirectResponse(f"/quotes/{quote.id}", status_code=303)


@router.get("/{quote_id}")
async def quote_view(request: Request, quote_id: int, msg: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _user_401(request, session)
    quote = await _quote_or_404(session, quote_id)
    return templates.TemplateResponse(
        request=request,
        name="quote_view.html",
        context={
            "current_user": user, "quote": quote, "status_labels": STATUS_LABELS, "msg": msg,
            "today": datetime.now().date(),
        },
    )


@router.get("/{quote_id}/edit")
async def quote_edit(request: Request, quote_id: int, error: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _user_401(request, session)
    quote = await _quote_or_404(session, quote_id)
    if quote.status != "draft":
        return RedirectResponse(f"/quotes/{quote.id}", status_code=303)
    items = [
        {
            "product_id": it.product_id,
            "name": it.name,
            "sku": it.sku,
            "unit": it.unit,
            "qty": str(it.qty),
            "price": str(it.price),
            "discount_percent": str(it.discount_percent),
        }
        for it in quote.items
    ]
    return templates.TemplateResponse(
        request=request,
        name="quote_form.html",
        context={
            "current_user": user, "lead": quote.lead, "mode": "edit", "quote": quote,
            "bootstrap_items": items, "error": error,
            "default_valid_until": quote.valid_until.isoformat() if quote.valid_until else "",
        },
    )


@router.post("/{quote_id}/update")
async def quote_update(
    request: Request,
    quote_id: int,
    items_json: str = Form(...),
    valid_until: str = Form(None),
    comment: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    await _user_401(request, session)
    quote = await _quote_or_404(session, quote_id)
    try:
        await qs.update_quote_items(session, quote, items_json,
                                    _parse_valid_until(valid_until), comment or None)
        await session.commit()
    except ValueError as e:
        return RedirectResponse(
            f"/quotes/{quote.id}/edit?error={urlquote(str(e))}", status_code=303
        )
    return RedirectResponse(f"/quotes/{quote.id}", status_code=303)


@router.post("/{quote_id}/status")
async def quote_status(
    request: Request,
    quote_id: int,
    action: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    await _user_401(request, session)
    quote = await _quote_or_404(session, quote_id)
    try:
        await qs.apply_status(session, quote, action)
        await session.commit()
        msg = {
            "send": "КП отправлено", "accept": "КП принято",
            "reject": "Отказ зафиксирован", "reopen": "Возвращено в черновик",
        }.get(action, "")
    except ValueError as e:
        await session.rollback()
        msg = str(e)
    return RedirectResponse(f"/quotes/{quote_id}?msg={urlquote(msg)}", status_code=303)


@router.get("/{quote_id}/print")
async def quote_print(request: Request, quote_id: int, preview: str = None, session: AsyncSession = Depends(get_session)):
    """Печатная форма КП: тексты из редактируемого шаблона (Настройки),
    логотип/реквизиты из профиля компании. preview=1 → HTML вместо PDF."""
    from app.main import templates

    await _user_401(request, session)
    quote = await _quote_or_404(session, quote_id)
    profile = await cs.get_profile(session)
    tpl = await cs.get_template(session, "quote")
    values = cs.placeholder_values(profile, quote)

    logo_data_uri = None
    if profile.logo_path:
        logo_file = settings.COMPANY_DIR / profile.logo_path
        if logo_file.is_file():
            import base64
            mime = "image/png" if logo_file.suffix == ".png" else "image/jpeg"
            logo_data_uri = f"data:{mime};base64," + base64.b64encode(logo_file.read_bytes()).decode()

    html_ = templates.env.get_template("print/quote.html").render(
        quote=quote,
        profile=profile,
        values=values,
        intro=cs.render_text(tpl.intro, values),
        conditions=cs.render_text(tpl.conditions, values),
        signature=cs.render_text(tpl.signature, values),
        requisites_lines=cs.company_requisites_lines(profile),
        requisites_head=", ".join(x for x in (profile.phone, profile.email, profile.site) if x),
        tax_note=profile.tax_note,
        logo_data_uri=logo_data_uri,
    )
    if preview:
        return HTMLResponse(html_)
    try:
        pdf = render_pdf(html_)
    except PDFUnavailable as e:
        return HTMLResponse(
            f"<h2>PDF сейчас недоступен</h2><p>{e}</p>"
            "<p>Печатная форма рендерится WeasyPrint'ом — он установлен в контейнере прода. "
            "Можно открыть HTML-версию: добавить ?preview=1 к адресу.</p>",
            status_code=503,
        )
    from fastapi.responses import Response
    filename = quote.number.replace("КП", "KP")  # ASCII в Content-Disposition
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}.pdf"},
    )
