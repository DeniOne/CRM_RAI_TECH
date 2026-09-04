"""Прайс-листы: просмотр/массовая правка цен, импорт из xlsx поставщика,
экспорт (фаза 18). Правка — supervisor/admin; менеджерам 403 (цены в каталоге
они видят, менять не могут).
"""

import io
import math
from urllib.parse import urlencode

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user, require_role
from app.database import get_session
from app.models import PriceList, Product, ProductCategory, ProductPrice
from app.routes.catalog import _build_filters, _category_context, _parse_q
from app.services import catalog_service as cs

router = APIRouter(prefix="/prices", tags=["prices"])

PER_PAGE = 100


async def _staff_guard(request: Request, session: AsyncSession):
    """Изменение цен — supervisor/admin. Менеджерам входящая цена не видна
    (решение владельца 2026-09-04), на просмотр отпускных пускаем всех."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    await require_role("supervisor", "admin")(request, session)
    return user


async def _default_pricelist(session: AsyncSession) -> PriceList | None:
    return (
        await session.execute(
            select(PriceList).where(PriceList.is_default == True)  # noqa: E712
        )
    ).scalar_one_or_none()


def _parse_page(page: str | None) -> int:
    return max(1, int(page)) if page and page.isdigit() else 1


async def _prices_page_context(session, q, category_id, page) -> dict:
    cat_ctx = await _category_context(session, category_id)
    conds = _build_filters(_parse_q(q), cat_ctx["subtree_ids"])

    total = (
        await session.execute(select(func.count()).select_from(Product).where(*conds))
    ).scalar_one()
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(page, pages)

    products = (
        (
            await session.execute(
                select(Product)
                .where(*conds)
                .options(joinedload(Product.category))
                .order_by(Product.category_id, Product.name)
                .offset((page - 1) * PER_PAGE)
                .limit(PER_PAGE)
            )
        )
        .scalars()
        .unique()
        .all()
    )

    pricelist = await _default_pricelist(session)
    prices: dict[int, object] = {}
    if pricelist and products:
        rows = await session.execute(
            select(ProductPrice).where(
                ProductPrice.price_list_id == pricelist.id,
                ProductPrice.product_id.in_([p.id for p in products]),
            )
        )
        prices = {pp.product_id: pp for pp in rows.scalars().all()}

    base_qs = urlencode(
        {k: v for k, v in {"q": _parse_q(q) or "", "category_id": category_id or ""}.items() if v}
    )
    return {
        "roots": cat_ctx["roots"],
        "category_id": category_id,
        "q": _parse_q(q) or "",
        "products": products,
        "prices": prices,
        "pricelist": pricelist,
        "total": total,
        "page": page,
        "pages": pages,
        "base_qs": base_qs,
    }


@router.get("")
async def prices_page(
    request: Request,
    q: str = None,
    category_id: str = None,
    page: str = None,
    saved: str = None,
    skipped: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    ctx = await _prices_page_context(
        session, q, int(category_id) if category_id and category_id.isdigit() else None,
        _parse_page(page),
    )
    is_staff = user.role.value in ("supervisor", "admin")
    if not is_staff:
        # менеджеру входящая цена не отдаётся даже в контексте шаблона
        ctx["prices"] = {
            pid: {"price_out": pp.price_out, "price": pp.price} for pid, pp in ctx["prices"].items()
        }
    ctx.update({"current_user": user, "saved": saved, "skipped": skipped, "is_staff": is_staff})
    return templates.TemplateResponse(request=request, name="prices.html", context=ctx)


@router.post("/save")
async def prices_save(
    request: Request,
    q: str = None,
    category_id: str = None,
    page: str = None,
    session: AsyncSession = Depends(get_session),
):
    await _staff_guard(request, session)
    pricelist = await cs.get_or_create_default_pricelist(session)

    form = await request.form()
    # Раскладка: price_in_* (входящая б/НДС), price_out_* (отпускная б/НДС),
    # vat_* (ставка). Отпускная с НДС считается в upsert_price.
    fields_by_pid: dict[int, dict] = {}
    for key, raw in form.multi_items():
        for prefix in ("price_in_", "price_out_", "vat_"):
            if key.startswith(prefix) and key[len(prefix):].isdigit():
                fields_by_pid.setdefault(int(key[len(prefix):]), {})[prefix[:-1]] = raw

    saved = skipped = 0
    for product_id, fields in fields_by_pid.items():
        pin = cs.parse_price_amount(fields.get("price_in"))
        pout = cs.parse_price_amount(fields.get("price_out"))
        vat = cs.parse_price_amount(fields.get("vat"))
        if pin is None and pout is None:
            skipped += 1
            continue
        await cs.upsert_price(session, product_id, pricelist.id,
                              price_in=pin, price_out=pout, vat_rate=vat)
        saved += 1
    await session.commit()

    params = {"saved": saved}
    if skipped:
        params["skipped"] = skipped
    back = {"q": q or "", "category_id": category_id or "", "page": page or ""}
    params.update({k: v for k, v in back.items() if v})
    return RedirectResponse(f"/prices?{urlencode(params)}", status_code=303)


@router.post("/import")
async def prices_import(
    request: Request,
    file: UploadFile = None,
    session: AsyncSession = Depends(get_session),
):
    await _staff_guard(request, session)
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="Файл не передан")
    try:
        rows = cs.read_catalog_rows(file.file)
    except Exception:
        raise HTTPException(status_code=400, detail="Не удалось прочитать xlsx")

    pricelist = await cs.get_or_create_default_pricelist(session)
    created = updated = no_price = no_product = 0
    for row in rows:
        product = await cs.find_product(session, row["url"], row["sku"])
        if product is None:
            no_product += 1
            continue
        value = cs.parse_price_amount(row["price_raw"])
        if value is None:
            no_price += 1
            continue
        # Цена поставщика — ВХОДЯЩАЯ б/НДС (решение владельца 2026-09-04);
        # отпускную ставят вручную в форме прайса.
        status = await cs.upsert_price(session, product.id, pricelist.id, price_in=value)
        if status == "created":
            created += 1
        else:
            updated += 1
    await session.commit()

    params = {"saved": created + updated, "skipped": no_price + no_product}
    return RedirectResponse(f"/prices?{urlencode(params)}", status_code=303)


@router.get("/export")
async def prices_export(request: Request, session: AsyncSession = Depends(get_session)):
    """Экспорт базового прайса xlsx. ASCII-имя файла — конвенция фазы 16
    (кириллица в Content-Disposition не используется)."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Прайс"
    ws.append(["Название", "Артикул", "Категория", "Цена"])
    pricelist = await _default_pricelist(session)
    count = 0
    if pricelist:
        rows = (
            await session.execute(
                select(Product, ProductPrice.price, ProductCategory.name)
                .join(ProductPrice, (ProductPrice.product_id == Product.id) &
                      (ProductPrice.price_list_id == pricelist.id), isouter=True)
                .join(ProductCategory, Product.category_id == ProductCategory.id, isouter=True)
                .where(Product.is_active == True)  # noqa: E712
                .order_by(ProductCategory.sort_order, Product.name)
            )
        ).all()
        for product, price, cat_name in rows:
            ws.append([product.name, product.sku or "", cat_name or "", float(price) if price is not None else None])
            count += 1
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=price_list_{count}.xlsx"},
    )
