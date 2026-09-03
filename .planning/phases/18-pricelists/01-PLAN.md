---
phase: 18
plan: 1
slice: pricing
wave: 1
depends_on: [17]
files_modified:
  - app/models.py
  - app/database.py
  - app/routes/catalog.py
  - app/templates/partials/catalog_products.html
  - app/templates/base.html
  - app/main.py
  - scripts/import_catalog.py
files_created:
  - app/services/catalog_service.py
  - app/routes/prices.py
  - app/templates/prices.html
  - .planning/phases/18-pricelists/01-PLAN.md
must_haves:
  truths:
    - "T-01: Модели PriceList (name/currency/is_default) + ProductPrice (product, price_list, price Numeric(12,2), min_qty, unique product+list) — create_all, ALTER существующих нет"
    - "T-02: Дефолтный прайс-лист создаётся лениво (get_or_create), валюта RUB по умолчанию; карточка каталога показывает цену из дефолтного списка, без цены — «цена по запросу»"
    - "T-03: Страница /prices (supervisor+admin; менеджеру 403): фильтр по категории/поиску, массовое сохранение цен одной формой, пустой/некорректный ввод — цена не меняется"
    - "T-04: Импорт цен из xlsx (загрузка файла, формат каталога фазы 17, колонка 6): numeric-строки («1 234,56») парсятся, товар ищется по source_url, затем по sku; отчёт created/updated/skipped"
    - "T-05: scripts/import_catalog.py при полном импорте подхватывает numeric-цены из той же колонки в дефолтный прайс"
    - "T-06: Экспорт прайса xlsx (товар/артикул/категория/цена) — BytesIO, StreamingResponse, без tempfile"
    - "T-07: Регрессии: /catalog, /kanban, /reports/center → 200; поиск u_lower работает"
context: |
  Фаза 18 milestone v2.0. Решение владельца: базовый прайс + ручная скидка в КП
  (фаза 19); модель закладывается под будущие сегментные прайсы (price_list_id
  везде FK, is_default у списка). Цены появляются по мере работы — товар без
  цены валиден и показывается как «цена по запросу».
details:
  - "Деньги — Numeric(12,2) (Decimal в Python); Float для денег не используем"
  - "Морфология цен у поставщика: «уточняйте», пробелы-разделители, запятая —
     parse_price_amount() возвращает Decimal|None"
  - "Валюты: колонка в PriceList (RUB default); пересчёт BYN/EUR — вне скоупа
     до появления реальных прайсов поставщика (открытый вопрос владельцу)"
