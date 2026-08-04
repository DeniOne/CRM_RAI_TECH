import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import init_db

logger = logging.getLogger("app.main")

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

    # Предзапускная sanity-проверка интеграции с Hermes. Ловит частый рассинхрон:
    # .env на сервере обновили (положили HERMES_API_TOKEN), но контейнер не
    # пересоздали (docker compose up) — он держит в памяти старый env и шлёт
    # запросы без Authorization → Hermes отдаёт 401, чат молча падает. Если Hermes
    # включён, а токен пустой — loudly кричим в лог при старте.
    if settings.HERMES_ENABLED:
        if not settings.HERMES_API_TOKEN:
            logger.warning(
                "⚠️  HERMES_ENABLED=true, но HERMES_API_TOKEN пустой. "
                "Hermes требует Authorization: Bearer — чат будет падать с 401. "
                "Положите токен в .env и ПЕРЕСОЗДАЙТЕ контейнер: "
                "`docker compose up -d` (не restart — restart не перечитывает env_file)."
            )
        logger.info(
            "Hermes integration: enabled=%s, url=%s, token_set=%s, timeout=%ds",
            settings.HERMES_ENABLED,
            settings.HERMES_API_URL,
            bool(settings.HERMES_API_TOKEN),
            settings.HERMES_TIMEOUT,
        )

    yield


app = FastAPI(title="CRM RAI", lifespan=lifespan)

app.add_middleware(AuthMiddleware)

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

from app.routes import auth, dashboard, leads, tasks, documents, deals, reports, agent, admin, ticker, library  # noqa: E402

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
app.include_router(library.router)
