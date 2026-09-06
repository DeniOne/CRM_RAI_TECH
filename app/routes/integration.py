"""Integration API для RAI Market Intelligence. X-API-Key: env CRM_INTEGRATION_KEY. Read-only."""
import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import Product, ProductCategory

router = APIRouter(prefix="/api/v1/integration", tags=["integration"])

def _check_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("CRM_INTEGRATION_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid api key")

@router.get("/catalog")
async def get_catalog(x_api_key: str = Header(default=""), session: AsyncSession = Depends(get_session)):
    _check_key(x_api_key)
    cats = (await session.execute(text("SELECT id, name, parent_id, sort_order FROM product_categories ORDER BY sort_order"))).mappings().all()
    prods = (await session.execute(text("SELECT id, category_id, name, sku, unit, description FROM products"))).mappings().all()
    return {
        "categories": [dict(c) for c in cats],
        "products": [dict(p) for p in prods],
        "source_revision": f"crm-{len(prods)}",
    }
