"""Каталог товаров: страница с деревом категорий, поиском и карточками.

Фаза 17 (v2.0). Цен в этой фазе нет — карточка показывает «цена по запросу».
Прайс-листы — фаза 18, подбор в КП — фаза 19.
"""

import math
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_session
from app.models import PriceList, Product, ProductCategory, ProductPrice
from app.services import catalog_service as cs

router = APIRouter(prefix="/catalog", tags=["catalog"])

PER_PAGE = 48


async def _staff(request: Request, session: AsyncSession):
    """Правка каталога — admin/supervisor (как прайс-лист)."""
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    await require_role("supervisor", "admin")(request, session)
    return user


def _parse_q(q: Optional[str]) -> Optional[str]:
    return (q or "").strip() or None


async def _category_context(session: AsyncSession, active_id: Optional[int]) -> dict:
    """Дерево категорий + счётчики товаров (с учётом потомков) + id-шники
    поддерева активной категории для фильтра."""
    cats = (
        (await session.execute(
            select(ProductCategory)
            .where(ProductCategory.is_active == True)  # noqa: E712
            .order_by(ProductCategory.sort_order, ProductCategory.name)
        ))
        .scalars()
        .all()
    )

    direct = {}
    if cats:
        rows = await session.execute(
            select(Product.category_id, func.count())
            .where(Product.is_active == True)  # noqa: E712
            .group_by(Product.category_id)
        )
        direct = {cid: n for cid, n in rows.all()}

    by_parent: dict = {}
    for c in cats:
        by_parent.setdefault(c.parent_id, []).append(c)

    parent_of = {c.id: c.parent_id for c in cats}

    # total[cid] = товары в самой категории + во всех потомках
    total = {}
    for c in cats:
        n = direct.get(c.id, 0)
        pid = parent_of.get(c.id)
        while pid is not None:
            total[pid] = total.get(pid, 0) + n
            pid = parent_of.get(pid)
    for c in cats:
        c.total = direct.get(c.id, 0) + total.get(c.id, 0)

    def with_children(node) -> dict:
        return {
            "obj": node,
            "children": [with_children(ch) for ch in by_parent.get(node.id, [])],
        }

    roots = [with_children(c) for c in by_parent.get(None, [])]

    subtree_ids: Optional[set[int]] = None
    if active_id is not None:
        subtree_ids = {active_id}
        stack = [active_id]
        while stack:
            pid = stack.pop()
            for ch in by_parent.get(pid, []):
                subtree_ids.add(ch.id)
                stack.append(ch.id)

    return {"roots": roots, "active_id": active_id, "subtree_ids": subtree_ids}


def _build_filters(q: Optional[str], subtree_ids: Optional[set[int]]):
    conds = [Product.is_active == True]  # noqa: E712
    if subtree_ids is not None:
        conds.append(Product.category_id.in_(subtree_ids))
    if q:
        # u_lower (см. database.py) — SQLite LIKE не фолдит кириллицу
        like = f"%{q.lower()}%"
        conds.append(
            or_(
                func.u_lower(Product.name).like(like),
                func.u_lower(Product.sku).like(like),
            )
        )
    return conds


async def _catalog_context(
    session: AsyncSession, q: Optional[str], category_id: Optional[int], page: int
) -> dict:
    cat_ctx = await _category_context(session, category_id)
    conds = _build_filters(q, cat_ctx["subtree_ids"])

    total = (
        await session.execute(select(func.count()).select_from(Product).where(*conds))
    ).scalar_one()
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(1, page), pages)

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

    pricelist = (
        await session.execute(
            select(PriceList).where(PriceList.is_default == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    prices: dict = {}
    if pricelist and products:
        rows = await session.execute(
            select(ProductPrice.product_id, ProductPrice.price).where(
                ProductPrice.price_list_id == pricelist.id,
                ProductPrice.product_id.in_([p.id for p in products]),
            )
        )
        prices = dict(rows.all())

    base_qs = urlencode(
        {k: v for k, v in {"q": q or "", "category_id": category_id or ""}.items() if v}
    )

    return {
        "q": q or "",
        "category_id": category_id,
        "roots": cat_ctx["roots"],
        "products": products,
        "prices": prices,
        "currency": pricelist.currency if pricelist else "RUB",
        "total": total,
        "page": page,
        "pages": pages,
        "per_page": PER_PAGE,
        "base_qs": base_qs,
    }


async def _current_user_or_401(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    return user


@router.get("")
async def catalog_page(
    request: Request,
    q: str = None,
    category_id: str = None,
    page: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await _current_user_or_401(request, session)
    ctx = await _catalog_context(
        session, _parse_q(q), int(category_id) if category_id and category_id.isdigit() else None,
        int(page) if page and page.isdigit() else 1,
    )
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={"current_user": user, **ctx},
    )


@router.get("/products")
async def catalog_products_partial(
    request: Request,
    q: str = None,
    category_id: str = None,
    page: str = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates

    user = await _current_user_or_401(request, session)
    ctx = await _catalog_context(
        session, _parse_q(q), int(category_id) if category_id and category_id.isdigit() else None,
        int(page) if page and page.isdigit() else 1,
    )
    return templates.TemplateResponse(
        request=request,
        name="partials/catalog_products.html",
        context={"current_user": user, **ctx},
    )


@router.get("/images/{filename}")
async def catalog_image(filename: str):
    """Картинки каталога. Маршрут НЕ в EXEMPT_PATHS — AuthMiddleware требует сессию,
    поэтому storage/ нигде не смонтирован публично. basename отсекает path traversal."""
    safe = Path(filename).name
    path = settings.CATALOG_IMAGES_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


# ---------- Ручное добавление/правка товаров (фаза 17-дополнение) ----------

async def _categories_flat(session: AsyncSession) -> list[ProductCategory]:
    return list(
        (
            await session.execute(
                select(ProductCategory)
                .where(ProductCategory.is_active == True)  # noqa: E712
                .order_by(ProductCategory.sort_order, ProductCategory.name)
            )
        )
        .scalars()
        .all()
    )


async def _default_prices(session: AsyncSession, product_id: int) -> ProductPrice | None:
    pl = (
        await session.execute(select(PriceList).where(PriceList.is_default == True))  # noqa: E712
    ).scalar_one_or_none()
    if not pl:
        return None
    return (
        await session.execute(
            select(ProductPrice).where(
                ProductPrice.price_list_id == pl.id, ProductPrice.product_id == product_id
            )
        )
    ).scalar_one_or_none()


async def _staff_user(request: Request, session: AsyncSession):
    user = await get_current_user(request, session)
    if not user:
        raise HTTPException(status_code=401)
    return user


@router.get("/new")
async def product_new(request: Request, error: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _staff(request, session)
    return templates.TemplateResponse(
        request=request,
        name="catalog_form.html",
        context={
            "current_user": user, "product": None, "pp": None,
            "categories": await _categories_flat(session), "error": error,
        },
    )


@router.get("/{product_id}/edit")
async def product_edit(request: Request, product_id: int, error: str = None, session: AsyncSession = Depends(get_session)):
    from app.main import templates

    user = await _staff(request, session)
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return templates.TemplateResponse(
        request=request,
        name="catalog_form.html",
        context={
            "current_user": user, "product": product,
            "pp": await _default_prices(session, product.id),
            "categories": await _categories_flat(session), "error": error,
        },
    )


def _parse_optional(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        from decimal import Decimal
        return Decimal(value.replace(",", ".").replace(" ", ""))
    except Exception:  # noqa: BLE001
        return None


@router.post("/create")
async def product_create(
    request: Request,
    name: str = Form(...),
    sku: str = Form(None),
    unit: str = Form("шт"),
    description: str = Form(None),
    brand: str = Form(None),
    origin: str = Form("resale"),
    category_id: str = Form(None),
    new_category: str = Form(None),
    price_in: str = Form(None),
    price_out: str = Form(None),
    vat_rate: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    await _staff(request, session)
    name = (name or "").strip()
    if not name:
        return RedirectResponse(f"/catalog/new?error={urlencode('Укажите название товара')}", status_code=303)

    # новая категория, если заполнена, приоритетнее селекта
    cat = None
    new_cat_name = (new_category or "").strip()
    if new_cat_name:
        cat = await cs.upsert_category(session, new_cat_name, 999)
    elif category_id and category_id.isdigit():
        cat = await session.get(ProductCategory, int(category_id))

    product = Product(
        name=name, sku=(sku or "").strip() or None, unit=(unit or "шт").strip(),
        description=(description or "").strip() or None, brand=(brand or "").strip() or None,
        origin=origin if origin in ("resale", "own") else "resale",
        category_id=cat.id if cat else None,
    )
    session.add(product)
    await session.flush()

    pin, pout, vat = _parse_optional(price_in), _parse_optional(price_out), _parse_optional(vat_rate)
    if pin is not None or pout is not None:
        pricelist = await cs.get_or_create_default_pricelist(session)
        await cs.upsert_price(session, product.id, pricelist.id,
                              price_in=pin, price_out=pout, vat_rate=vat)
    await session.commit()
    return RedirectResponse("/catalog", status_code=303)


@router.post("/{product_id}/update")
async def product_update(
    request: Request,
    product_id: int,
    name: str = Form(...),
    sku: str = Form(None),
    unit: str = Form("шт"),
    description: str = Form(None),
    brand: str = Form(None),
    origin: str = Form("resale"),
    is_active: str = Form(None),
    category_id: str = Form(None),
    new_category: str = Form(None),
    price_in: str = Form(None),
    price_out: str = Form(None),
    vat_rate: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    await _staff(request, session)
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    if not (name or "").strip():
        return RedirectResponse(f"/catalog/{product_id}/edit?error={urlencode('Укажите название товара')}", status_code=303)

    product.name = name.strip()
    product.sku = (sku or "").strip() or None
    product.unit = (unit or "шт").strip()
    product.description = (description or "").strip() or None
    product.brand = (brand or "").strip() or None
    product.origin = origin if origin in ("resale", "own") else "resale"
    product.is_active = is_active == "on"

    cat = None
    new_cat_name = (new_category or "").strip()
    if new_cat_name:
        cat = await cs.upsert_category(session, new_cat_name, 999)
    elif category_id and category_id.isdigit():
        cat = await session.get(ProductCategory, int(category_id))
    if cat:
        product.category_id = cat.id

    pin, pout, vat = _parse_optional(price_in), _parse_optional(price_out), _parse_optional(vat_rate)
    if pin is not None or pout is not None:
        pricelist = await cs.get_or_create_default_pricelist(session)
        await cs.upsert_price(session, product.id, pricelist.id,
                              price_in=pin, price_out=pout, vat_rate=vat)
    await session.commit()
    return RedirectResponse("/catalog", status_code=303)


@router.post("/{product_id}/archive")
async def product_archive(request: Request, product_id: int, restore: str = Form(None), session: AsyncSession = Depends(get_session)):
    """Мягкое удаление: документы ссылаются на товар, физически не удаляем."""
    await _staff(request, session)
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    product.is_active = restore == "1"  # не bool(restore): непустая строка "0" — True
    await session.commit()
    return RedirectResponse("/catalog", status_code=303)
