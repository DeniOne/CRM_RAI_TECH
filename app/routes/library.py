"""Библиотека — файловый менеджер для общих материалов (презентации, КП, фото, видео).

Права (курируемая):
- Просмотр и скачивание — все аутентифицированные пользователи.
- Создание папок, загрузка, удаление — admin и supervisor (require_role).
"""
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_session
from app.models import LibraryFolder, LibraryFile

router = APIRouter()

# Разрешённые роли для записи в библиотеку
WRITE_ROLES = ("admin", "supervisor")


def _human_size(size_bytes: int) -> str:
    """Читаемый размер файла."""
    if not size_bytes:
        return "0 Б"
    units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
    size = float(size_bytes)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


async def _build_breadcrumb(session: AsyncSession, folder: LibraryFolder | None) -> list[dict]:
    """Возвращает цепочку от корня до текущей папки: [{id, name}, ...]."""
    crumbs = []
    current = folder
    while current is not None:
        crumbs.append({"id": current.id, "name": current.name})
        parent = None
        if current.parent_id is not None:
            res = await session.execute(
                select(LibraryFolder).where(LibraryFolder.id == current.parent_id)
            )
            parent = res.scalar_one_or_none()
        current = parent
    crumbs.reverse()
    return crumbs


async def _render_listing(
    request: Request,
    session: AsyncSession,
    folder_id: int | None,
    user,
    status_message: dict | None = None,
):
    """Перерисовывает partial со списком содержимого папки (для HTMX-ответов)."""
    from app.main import templates

    folders, files = await _list_folder_contents(session, folder_id)
    breadcrumb = await _build_breadcrumb(session, await _get_folder(session, folder_id))

    can_write = user is not None and user.role.value in WRITE_ROLES

    return templates.TemplateResponse(
        request=request,
        name="partials/library_listing.html",
        context={
            "current_user": user,
            "folders": folders,
            "files": files,
            "current_folder_id": folder_id,
            "breadcrumb": breadcrumb,
            "can_write": can_write,
            "human_size": _human_size,
            "status_message": status_message,
        },
    )


async def _get_folder(session: AsyncSession, folder_id: int | None) -> LibraryFolder | None:
    if folder_id is None:
        return None
    res = await session.execute(select(LibraryFolder).where(LibraryFolder.id == folder_id))
    folder = res.scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Папка не найдена")
    return folder


async def _list_folder_contents(session: AsyncSession, folder_id: int | None):
    """Возвращает (folders, files) внутри папки."""
    folders_res = await session.execute(
        select(LibraryFolder)
        .where(LibraryFolder.parent_id == folder_id)
        .order_by(LibraryFolder.name)
    )
    files_res = await session.execute(
        select(LibraryFile)
        .where(LibraryFile.folder_id == folder_id)
        .order_by(LibraryFile.name)
    )
    return folders_res.scalars().all(), files_res.scalars().all()


# ─── Страница библиотеки ────────────────────────────────────────────

@router.get("/library", response_class=HTMLResponse)
async def library_page(
    request: Request,
    folder: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await get_current_user(request, session)

    # Проверяем существование папки (404 если нет)
    await _get_folder(session, folder)

    folders, files = await _list_folder_contents(session, folder)
    breadcrumb = await _build_breadcrumb(session, await _get_folder(session, folder))
    can_write = user is not None and user.role.value in WRITE_ROLES

    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "current_user": user,
            "folders": folders,
            "files": files,
            "current_folder_id": folder,
            "breadcrumb": breadcrumb,
            "can_write": can_write,
            "human_size": _human_size,
            "status_message": None,
        },
    )


# ─── Формы (в drawer) ───────────────────────────────────────────────

@router.get("/library/folder/form", response_class=HTMLResponse)
async def folder_form(
    request: Request,
    parent: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role(*WRITE_ROLES)(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/library_folder_form.html",
        context={"current_user": user, "parent_folder_id": parent},
    )


@router.get("/library/upload/form", response_class=HTMLResponse)
async def upload_form(
    request: Request,
    folder: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    from app.main import templates
    user = await require_role(*WRITE_ROLES)(request, session)
    return templates.TemplateResponse(
        request=request,
        name="partials/library_upload_form.html",
        context={"current_user": user, "current_folder_id": folder},
    )


# ─── Создание папки ─────────────────────────────────────────────────

@router.post("/library/folder", response_class=HTMLResponse)
async def create_folder(
    request: Request,
    name: str = Form(...),
    parent_folder_id: int | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_role(*WRITE_ROLES)(request, session)

    name = name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Имя папки не может быть пустым")
    if len(name) > 255:
        raise HTTPException(status_code=422, detail="Имя слишком длинное (макс. 255 символов)")

    # Проверяем существование родителя
    if parent_folder_id is not None:
        await _get_folder(session, parent_folder_id)

    # Проверяем уникальность имени в рамках папки
    existing = await session.execute(
        select(LibraryFolder).where(
            LibraryFolder.parent_id == parent_folder_id,
            LibraryFolder.name == name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Папка «{name}» уже существует")

    folder = LibraryFolder(
        parent_id=parent_folder_id,
        name=name,
        created_by=user.id,
    )
    session.add(folder)
    await session.commit()

    return await _render_listing(
        request, session, parent_folder_id, user,
        status_message={"type": "success", "text": f"Папка «{name}» создана"},
    )


# ─── Загрузка файлов ────────────────────────────────────────────────

@router.post("/library/upload", response_class=HTMLResponse)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    folder_id: int | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    user = await require_role(*WRITE_ROLES)(request, session)

    # Проверяем существование папки
    if folder_id is not None:
        await _get_folder(session, folder_id)

    os.makedirs(settings.LIBRARY_DIR, exist_ok=True)

    uploaded_count = 0
    skipped = []
    for upload in files:
        original = upload.filename or "без_имени"
        # Оригинальное имя (как видят пользователи)
        base_name = os.path.splitext(os.path.basename(original))[0] or original
        ext = os.path.splitext(original)[1].lower().lstrip(".")

        # Уникальное имя файла на диске
        safe_name = f"{uuid.uuid4().hex}_{original}"
        save_path = str(settings.LIBRARY_DIR / safe_name)

        content = await upload.read()
        if not content:
            skipped.append(original)
            continue

        with open(save_path, "wb") as f:
            f.write(content)

        db_file = LibraryFile(
            folder_id=folder_id,
            name=base_name if base_name else original,
            original_filename=original,
            extension=ext,
            size_bytes=len(content),
            file_path=save_path,
            mime_type=upload.content_type,
            uploaded_by=user.id,
        )
        session.add(db_file)
        uploaded_count += 1

    await session.commit()

    if uploaded_count and skipped:
        msg = {"type": "success",
               "text": f"Загружено файлов: {uploaded_count}. Пропущено (пустые): {len(skipped)}"}
    elif uploaded_count:
        msg = {"type": "success", "text": f"Загружено файлов: {uploaded_count}"}
    else:
        msg = {"type": "error", "text": "Не загружено ни одного файла"}

    return await _render_listing(request, session, folder_id, user, status_message=msg)


# ─── Удаление ───────────────────────────────────────────────────────

@router.post("/library/folder/{folder_id}/delete", response_class=HTMLResponse)
async def delete_folder(
    request: Request,
    folder_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await require_role(*WRITE_ROLES)(request, session)

    folder = await _get_folder(session, folder_id)

    # Подсчёт содержимого
    children_cnt_res = await session.execute(
        select(func.count()).select_from(LibraryFolder).where(LibraryFolder.parent_id == folder_id)
    )
    children_cnt = children_cnt_res.scalar() or 0

    files_cnt_res = await session.execute(
        select(func.count()).select_from(LibraryFile).where(LibraryFile.folder_id == folder_id)
    )
    files_cnt = files_cnt_res.scalar() or 0

    if children_cnt or files_cnt:
        parts = []
        if children_cnt:
            parts.append(f"подпапок: {children_cnt}")
        if files_cnt:
            parts.append(f"файлов: {files_cnt}")
        raise HTTPException(
            status_code=422,
            detail=f"Нельзя удалить непустую папку ({', '.join(parts)}). Сначала очистите её.",
        )

    parent_id = folder.parent_id
    await session.delete(folder)
    await session.commit()

    return await _render_listing(
        request, session, parent_id, user,
        status_message={"type": "success", "text": f"Папка «{folder.name}» удалена"},
    )


@router.post("/library/file/{file_id}/delete", response_class=HTMLResponse)
async def delete_file(
    request: Request,
    file_id: int,
    session: AsyncSession = Depends(get_session),
):
    user = await require_role(*WRITE_ROLES)(request, session)

    res = await session.execute(select(LibraryFile).where(LibraryFile.id == file_id))
    db_file = res.scalar_one_or_none()
    if db_file is None:
        raise HTTPException(status_code=404, detail="Файл не найден")

    folder_id = db_file.folder_id
    file_name = db_file.name
    phys_path = db_file.file_path

    await session.delete(db_file)
    await session.commit()

    # Удаляем физический файл (после успешного коммита)
    if phys_path and os.path.exists(phys_path):
        try:
            os.remove(phys_path)
        except OSError:
            pass  # не блокируем ответ, если файл не удалился с диска

    return await _render_listing(
        request, session, folder_id, user,
        status_message={"type": "success", "text": f"Файл «{file_name}» удалён"},
    )


# ─── Скачивание ─────────────────────────────────────────────────────

@router.get("/library/file/{file_id}/download")
async def download_file(
    file_id: int,
    session: AsyncSession = Depends(get_session),
):
    res = await session.execute(select(LibraryFile).where(LibraryFile.id == file_id))
    db_file = res.scalar_one_or_none()
    if db_file is None:
        raise HTTPException(status_code=404, detail="Файл не найден")

    if not db_file.file_path or not os.path.exists(db_file.file_path):
        raise HTTPException(status_code=404, detail="Файл отсутствует на диске")

    return FileResponse(db_file.file_path, filename=db_file.original_filename)
