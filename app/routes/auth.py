from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_user, set_session, clear_session
from app.database import get_session

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    from app.main import templates
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await authenticate_user(session, email, password)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Неверный email или пароль"})
    response = RedirectResponse("/", status_code=303)
    set_session(response, user.id)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response
