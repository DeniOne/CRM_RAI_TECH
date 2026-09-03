---
phase: 19
plan: 1
slice: quotes-cpq
wave: 1
depends_on: [18]
files_modified:
  - app/models.py
  - app/database.py
  - app/main.py
  - app/routes/leads.py
  - app/templates/lead_card.html
  - scripts/import_catalog.py
  - Dockerfile
  - requirements.txt
files_created:
  - app/services/quote_service.py
  - app/services/pdf_service.py
  - app/routes/quotes.py
  - app/templates/quote_form.html
  - app/templates/quote_view.html
  - app/templates/partials/lead_quotes_tab.html
  - app/templates/print/quote.html
  - app/static/js/quote_builder.js
  - .planning/phases/19-quotes-cpq/01-PLAN.md
must_haves:
  truths:
    - "T-01: Модели Quote (number уникальный КП-YYYY-NNNN, lead/deal/user FK, status draft|sent|accepted|rejected, total Numeric) + QuoteItem (СНАПШОТ name/sku/unit/price + qty/discount/amount, product_id nullable) + SequenceCounter (нумерация)"
    - "T-02: Сервер сам считает суммы: amount = qty*price*(1-disc/100), total = сумма; клиентские суммы не доверяются; снапшот name/sku/unit/price берётся из БД по product_id (анти-тампер)"
    - "T-03: Своя позиция (product_id=null) — свободное название/цена, снапшот из формы"
    - "T-04: Typeahead /api/products/search?q= — debounce 300ms на фронте, поиск u_lower по названию/артикулу, JSON с ценой из дефолтного прайса"
    - "T-05: Статусы: draft→sent (sent_at, лид → стадия 3 если числовая < 3, через change_stage с историей) → accepted (Deal.amount = total, статус → contract, лид → 5 если < 5) | rejected; sent/rejected → draft (правка)"
    - "T-06: В карточке лида таб «КП»: список КП лида + создание; черновик правится (замена позиций), после sent — только статусы"
    - "T-07: Печатная форма КП — standalone HTML (self-hosted: без CDN; DejaVu Sans/Mono) → WeasyPrint PDF; Dockerfile + pango/harfbuzz/fonts-dejavu; локально без GTK → мягкий 503 (PDF верифицируется в контейнере)"
    - "T-08: Регрессии: канбан, карточка лида, каталог, прайсы"
context: |
  Фаза 19 v2.0. Кросс-фазные truths (фаза 17): Deal.amount и стадии меняются
  ТОЛЬКО по статусам КП; несколько draft/sent КП на лид — норма. Снапшот цен
  в позициях — анти-«поплыть» при смене прайса. Деньги Decimal.
details:
  - "Нумерация: SequenceCounter(name=КП, year, value) → КП-2026-0001"
  - "items_json из билдера валидируется сервером: qty>0, price>=0, disc 0..100"
  - "Печатная форма без реквизитов продавца (CompanyProfile — фаза 20), без НДС-блоков"
  - "PDF: weasyprint в requirements+Dockerfile; pdf_service.render_pdf изолирован"
