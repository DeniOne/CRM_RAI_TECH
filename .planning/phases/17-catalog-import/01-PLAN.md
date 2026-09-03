---
phase: 17
plan: 1
slice: catalog
wave: 1
depends_on: [16]
files_modified:
  - app/models.py
  - app/database.py
  - app/config.py
  - app/main.py
  - app/templates/base.html
files_created:
  - app/routes/catalog.py
  - app/templates/catalog.html
  - app/templates/partials/catalog_products.html
  - scripts/import_catalog.py
  - .planning/phases/17-catalog-import/01-PLAN.md
must_haves:
  truths:
    - "T-01: GET /catalog — страница каталога (дерево категорий слева, поиск, сетка карточек), доступна любой авторизованной роли, без сессии — редирект на /login"
    - "T-02: поиск по подстроке названия/артикула через HTMX-партиал /catalog/products, debounce 300ms, без перезагрузки страницы"
    - "T-03: фильтр по категории включает товары всех дочерних категорий (дерево self-FK), состояние в URL (push-url)"
    - "T-04: GET /catalog/images/{file} отдаёт файлы только из storage/catalog/images/ (basename-guard против path traversal), маршрут НЕ в EXEMPT_PATHS — требует сессии; storage/ нигде не смонтирован публично"
    - "T-05: scripts/import_catalog.py идемпотентен — повторный запуск upsert'ит по source_url (все 1355 URL в xlsx уникальны — проверено), не плодит дубли, обновляет name/sku"
    - "T-06: импорт из agrovita_catalog.xlsx создаёт 1355 товаров и 40 категорий (проверено на локальной копии прод-БД)"
    - "T-07: загрузчик картинок: timeout, retries с backoff, throttle-пауза, browser-UA, возобновляемость (существующие файлы пропускаются), битые/404 — позиция остаётся без картинки, импорт не падает"
    - "T-08: карточка без цены показывает «цена по запросу» (цены появляются в фазе 18, поле цены в v17 не существует)"
    - "T-09: регрессий нет — kanban, deals, reports, library отвечают 200 после изменений"
context: |
  CRM v2.0 milestone «Ассортимент». Фаза 17 — фундамент каталога: номенклатура
  без цен (цены — фаза 18), первый импорт из каталога производителя АгроВита
  (agrovita.by, 1355 позиций, 40 категорий, 1342 картинки).

  Решения владельца (сессия 2026-09-03):
  - подбор покупателя — внутренний CPQ менеджером (витрина — v2.1 backlog);
  - склад/остатки — вне v2.0;
  - ценообразование — базовый прайс + ручная скидка в КП (модель прайс-листов
    закладывается в фазе 18 сразу под будущие сегменты);
  - счета генерирует CRM (1С-интеграция — backlog).

  Улика безопасности (ревью): картинки каталога — ТОЛЬКО в storage/catalog/images/
  (volume, переживает пересоздание контейнера). app/static НЕ используется — он
  запекается в образ и не является volume. Публичный mount storage/ запрещён.
gap: |
  Сущностей Product/Category в БД нет (проверено grep по app/ — 0 совпадений).
  init_db поднимает новые таблицы через create_all — ALTER существующих таблиц
  фаза не требует.
details:
  - "ProductCategory: self-FK дерево (ondelete CASCADE), sort_order, is_active"
  - "Product: name/sku/unit/description, brand, origin(resale|own), image_file (имя файла,
     URL строится /catalog/images/{file}), source_url (upsert-ключ), attrs_json — гибкие
     характеристики без ALTER'ов на каждый атрибут"
  - "Импорт: категории — корневые узлы из колонки «Категория» (в файле подкатегория
     дублирует категорию; дерево пригодится следующим поставщикам)"
  - "Скрипт: async (конвенция scripts/import_xlsx.py), httpx.AsyncClient, отчёт JSON
     в storage/exports/catalog_import_{ts}.json"
