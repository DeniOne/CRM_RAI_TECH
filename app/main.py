from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db

EXEMPT_PATHS = {"/login", "/docs", "/openapi.json", "/favicon.ico", "/invite"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/static") or path in EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/invite"):
            return await call_next(request)
        token = request.cookies.get("session")
        if not token and path != "/login":
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="CRM RAI", lifespan=lifespan)

app.add_middleware(AuthMiddleware)

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

from app.routes import auth, dashboard, leads, tasks, documents, deals, reports, agent, admin, ticker  # noqa: E402

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(leads.router)
app.include_router(tasks.router)
app.include_router(documents.router)
app.include_router(deals.router)
app.include_router(reports.router)
app.include_router(agent.router)
app.include_router(admin.router)
app.include_router(ticker.router)
