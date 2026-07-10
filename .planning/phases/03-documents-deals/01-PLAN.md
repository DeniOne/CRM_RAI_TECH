---
phase: 3-documents-deals
plan: "01"
slice: 3-01
type: execute
wave: 1
depends_on:
  - phase-2
requirements:
  - CRM-3-01
autonomous: true
files_modified:
  - app/main.py
  - app/templates/base.html
  - app/templates/lead_card.html
  - app/templates/partials/lead_info_form.html
  - app/services/phone_parser.py
  - app/requirements.txt
files_created:
  - app/routes/documents.py
  - app/routes/deals.py
  - app/services/document_service.py
  - app/templates/documents.html
  - app/templates/document_detail.html
  - app/templates/deals.html
  - app/templates/partials/documents_list.html
  - app/templates/partials/deals_list.html
  - app/templates/partials/document_form.html
  - app/templates/upload_template.html
  - app/templates/partials/templates_list.html
must_haves:
  truths:
    - "D-01: app/services/document_service.py содержит extract_placeholders(docx_path) -> list[str] — парсит {placeholder} из параграфов и таблиц .docx, возвращает уникальные имена"
    - "D-02: app/services/document_service.py содержит generate_document(template_path, replacements: dict, output_path) -> str — открывает .docx через python-docx, заменяет плейсхолдеры на уровне параграфа (merge runs → replace → set on first run, clear rest), сохраняет .docx"
    - "D-03: app/services/document_service.py содержит convert_to_pdf(docx_path, pdf_path) -> str — конвертация через docx2pdf (Word COM на Windows). Если docx2pdf недоступен — graceful fallback: только .docx без PDF, статус документа 'draft (no pdf)'"
    - "D-04: app/services/document_service.py содержит DEFAULT_PLACEHOLDERS — маппинг имён плейсхолдеров на поля Lead: {company_name}→lead.name, {inn}→lead.inn, {district}→lead.district, {head_name}→lead.head_name, {site}→lead.site, {phone}→первый контакт.телефон, {email}→первый контакт.email, {region}→lead.region.name, {manager_name}→user.full_name, {date}→текущая дата"
    - "D-05: GET /templates — страница управления шаблонами: список загруженных + форма загрузки нового (.docx-файл, name, doc_type: kp/contract/invoice/act)"
    - "D-06: POST /templates/upload — приём .docx-файла через UploadFile, сохранение в templates_docx/, создание DocumentTemplate с автопарсингом плейсхолдеров через extract_placeholders, JSON-список в поле placeholders"
    - "D-07: POST /templates/{id}/delete — удаление шаблона (soft delete: is_active=False), файл остаётся на диске"
    - "D-08: GET /leads/{id}/documents — список документов лида + форма генерации: выбор template_id (по doc_type), поля для дополнительных плейсхолдеров (amount, number и т.д. — те, которых нет в DEFAULT_PLACEHOLDERS)"
    - "D-09: POST /leads/{id}/documents/generate — генерация документа: загрузка шаблона, сборка replacements из Lead + доп. полей формы, вызов generate_document → .docx, вызов convert_to_pdf → .pdf, создание Document-записи со status='draft', возврат partial с документом"
    - "D-10: GET /documents/{id}/download?format=docx|pdf — отдача файла (FileResponse). Если PDF не сгенерирован и format=pdf → 404 с сообщением"
    - "D-11: POST /documents/{id}/status — смена статуса (draft→sent→viewed→accepted→rejected) через HTMX. При status='sent' → sent_at=now()"
    - "D-12: GET /deals — страница сделок: список всех сделок с фильтром по статусу (new/kp_sent/negotiation/contract/invoiced/paid/lost)"
    - "D-13: POST /leads/{id}/deals — создание сделки (title, amount) через HTMX"
    - "D-14: POST /deals/{id}/status — смена статуса сделки через HTMX"
    - "D-15: В карточке лида (lead_card.html) добавлен 6-й таб 'Документы' с include partials/documents_list.html и 7-й таб 'Сделки' с include partials/deals_list.html"
    - "D-16: Sidebar обновлён: ссылка 'Шаблоны' → /templates, 'Сделки' → /deals"
    - "D-17: phone_parser.py regex исправлен: добавлены альтернативы для 11 цифр подряд без разделителей (892100200475) и 5-значных кодов региона (+7 (81146) 2-13-37). Тест: parse_phones('892100200475')[0]['phone'] содержит '892100200475', parse_phones('+7 (81146) 2-13-37')[0]['phone'] содержит '+7 (81146) 2-13-37'"
    - "D-18: lead_info_form.html — форма назначения менеджера вынесена за пределы формы редактирования (отдельный <div> с собственной <form>), больше не вложена"
    - "D-19: requirements.txt обновлён: добавлен docx2pdf"
    - "D-20: Сгенерированные файлы сохраняются в storage/documents/{lead_id}/doc_{id}.docx и .pdf — структура директорий создаётся автоматически"
  artifacts:
    - path: app/services/document_service.py
      provides: "Парсинг плейсхолдеров .docx, генерация документов с заменой, конвертация в PDF"
    - path: app/routes/documents.py
      provides: "Управление шаблонами, генерация/скачивание/статусы документов"
    - path: app/routes/deals.py
      provides: "CRUD сделок, смена статусов"
  key_links:
    - from: app/routes/documents.py
      to: app/services/document_service.py
      via: "extract_placeholders + generate_document + convert_to_pdf"
      pattern: "docx generation pipeline"
    - from: app/templates/partials/documents_list.html
      to: app/routes/documents.py
      via: "HTMX hx-post generate + hx-get download"
      pattern: "document workflow"
---

# Plan 3-01 — Документооборот и сделки (Wave 1)

**Phase:** 3 — documents-deals
**Wave:** B-1
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo

## Контекст (почему эта фаза)

Фаза 2 дала менеджеру канбан, карточку лида и журнал контактов. Менеджер довёл лид до стадии «КП отправлено» — но КП генерируется вручную в Word. Фаза 3 автоматизирует документооборот: загрузка .docx-шаблонов → генерация КП/договора/счёта с автоподстановкой данных лида → PDF → скачивание. Плюс модуль сделок для отслеживания цепочки документов.

**Разведка техлида (проверено runtime):**
- `python-docx 1.2.0` — установлен, работает
- `docx2pdf` — установлен, конвертация через Word COM работает (проверено: test.docx → test.pdf, 69KB, ~4 сек)
- Microsoft Word установлен: `C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE`
- LibreOffice НЕ установлен — используем docx2pdf (Word COM)
- Плейсхолдеры `{name}` парсятся из параграфов и таблиц корректно
- **Split-run проблема подтверждена:** Word разбивает текст на несколько runs, run-level замена не работает. Решение: paragraph-level merge (объединить text всех runs → заменить → записать в первый run, очистить остальные)
- Модели Deal, Document, DocumentTemplate готовы из Фазы 1 (связи, FK, поля — всё на месте)
- `templates_docx/` существует, пустой
- `storage/documents/` существует, пустой

**Долги Фазы 2, закрываемые здесь:**
- D-B2: парсер телефонов — 2 паттерна всё ещё урезаются
- D-E: вложенная `<form>` в lead_info_form.html

## Стек документов

| Компонент | Технология | Статус |
|---|---|---|
| Чтение/запись .docx | python-docx 1.2.0 | ✅ установлен |
| Парсинг плейсхолдеров | regex `\{(\w+)\}` по параграфам + таблицам | ✅ проверено |
| Замена плейсхолдеров | paragraph-level merge (split-run safe) | ✅ проверено |
| PDF-конвертация | docx2pdf (Word COM) | ✅ установлен, проверено |
| Хранение файлов | `templates_docx/` (шаблоны), `storage/documents/{lead_id}/` (генерируемые) | ✅ директории есть |

## Что делает кодер (пофайлово)

### 1. `app/services/document_service.py` (новый) — ядро документооборота

#### `def extract_placeholders(docx_path: str) -> list[str]`

```python
def extract_placeholders(docx_path: str) -> list[str]:
    """Парсит {placeholder} из .docx — в параграфах и таблицах.
    Возвращает уникальные имена без скобок."""
    doc = Document(docx_path)
    placeholders = set()
    pattern = re.compile(r'\{(\w+)\}')

    for para in doc.paragraphs:
        placeholders.update(pattern.findall(para.text))

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    placeholders.update(pattern.findall(para.text))

    # Also check headers and footers
    for section in doc.sections:
        for para in section.header.paragraphs:
            placeholders.update(pattern.findall(para.text))
        for para in section.footer.paragraphs:
            placeholders.update(pattern.findall(para.text))

    return sorted(placeholders)
```

#### `def generate_document(template_path: str, replacements: dict, output_path: str) -> str`

```python
def generate_document(template_path: str, replacements: dict, output_path: str) -> str:
    """Открывает шаблон .docx, заменяет {placeholder} на значения, сохраняет."""
    doc = Document(template_path)

    def replace_in_paragraphs(paragraphs):
        for para in paragraphs:
            full_text = para.text
            changed = False
            for key, val in replacements.items():
                placeholder = '{' + key + '}'
                if placeholder in full_text:
                    full_text = full_text.replace(placeholder, str(val))
                    changed = True
            if changed and para.runs:
                # Split-run safe: write merged text to first run, clear rest
                para.runs[0].text = full_text
                for run in para.runs[1:]:
                    run.text = ''

    replace_in_paragraphs(doc.paragraphs)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                replace_in_paragraphs(cell.paragraphs)

    for section in doc.sections:
        replace_in_paragraphs(section.header.paragraphs)
        replace_in_paragraphs(section.footer.paragraphs)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc.save(output_path)
    return output_path
```

#### `def convert_to_pdf(docx_path: str, pdf_path: str) -> str | None`

```python
def convert_to_pdf(docx_path: str, pdf_path: str) -> str | None:
    """Конвертация .docx → .pdf через docx2pdf (Word COM).
    Возвращает путь к PDF или None при ошибке."""
    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        if os.path.exists(pdf_path):
            return pdf_path
        return None
    except Exception:
        return None
```

#### `DEFAULT_PLACEHOLDERS` — маппинг полей Lead

```python
DEFAULT_PLACEHOLDERS = {
    "company_name": lambda lead, user: lead.name,
    "inn": lambda lead, user: lead.inn or "",
    "district": lambda lead, user: lead.district or "",
    "settlement": lambda lead, user: lead.settlement or "",
    "address": lambda lead, user: lead.address or "",
    "head_name": lambda lead, user: lead.head_name or "",
    "site": lambda lead, user: lead.site or "",
    "region": lambda lead, user: lead.region.name if lead.region else "",
    "manager_name": lambda lead, user: user.full_name,
    "date": lambda lead, user: datetime.now().strftime("%d.%m.%Y"),
    "phone": lambda lead, user: lead.contacts[0].phone if lead.contacts else "",
    "email": lambda lead, user: lead.contacts[0].email if lead.contacts else "",
    "rapeseed_volume": lambda lead, user: lead.rapeseed_volume or "",
    "harvest_timing": lambda lead, user: lead.harvest_timing or "",
}
```

#### `def build_replacements(lead, user, extra: dict = None) -> dict`

```python
def build_replacements(lead, user, extra: dict = None) -> dict:
    """Собирает словарь замен: DEFAULT_PLACEHOLDERS + extra (из формы)."""
    replacements = {}
    for key, func in DEFAULT_PLACEHOLDERS.items():
        replacements[key] = func(lead, user)
    if extra:
        for key, val in extra.items():
            if val:  # не перезаписывать пустыми
                replacements[key] = val
    return replacements
```

### 2. `app/routes/documents.py` (новый) — роутер документов

Подключается в `app/main.py`: `app.include_router(documents.router)`

#### `GET /templates` — управление шаблонами
- Запрос: `select(DocumentTemplate).order_by(DocumentTemplate.doc_type, DocumentTemplate.name)`
- Рендер: `upload_template.html` (список + форма загрузки)

#### `POST /templates/upload` — загрузка шаблона
- Параметры: `file: UploadFile`, `name: str = Form(...)`, `doc_type: str = Form(...)` (kp/contract/invoice/act)
- Сохранение: `templates_docx/{doc_type}_{name}_{timestamp}.docx`
- Автопарсинг: `extract_placeholders(path)` → JSON в поле `placeholders`
- Создание `DocumentTemplate(name, doc_type, file_path, placeholders, is_active=True)`
- Редирект на `/templates`

#### `POST /templates/{id}/delete` — soft delete
- `template.is_active = False`, commit, редирект на `/templates`

#### `GET /leads/{id}/documents` — список документов лида + форма генерации (HTMX partial)
- Загрузка: `select(Document).where(Document.lead_id == id).order_by(Document.created_at.desc())`
- Загрузка активных шаблонов для select'а: `select(DocumentTemplate).where(DocumentTemplate.is_active == True)`
- Рендер: `partials/documents_list.html`

#### `POST /leads/{id}/documents/generate` — генерация документа (HTMX)
- Параметры: `template_id: int = Form(...)`, плюс динамические поля из формы (`amount`, `number`, `title` и т.д. — те плейсхолдеры, которых нет в DEFAULT_PLACEHOLDERS)
- Логика:
  1. Загрузить Lead с `selectinload(Lead.contacts, Lead.region)`
  2. Загрузить DocumentTemplate
  3. `extra = {k: v for k, v in form_fields if k not in DEFAULT_PLACEHOLDERS}`
  4. `replacements = build_replacements(lead, user, extra)`
  5. `docx_path = f"storage/documents/{lead_id}/doc_{timestamp}.docx"`
  6. `generate_document(template.file_path, replacements, docx_path)`
  7. `pdf_path = docx_path.replace('.docx', '.pdf')`
  8. `convert_to_pdf(docx_path, pdf_path)` — может вернуть None
  9. Создать `Document(lead_id, user_id, doc_type=template.doc_type, template_id, title, number, amount, file_path=docx_path, file_path_pdf=pdf_path if exists else None, status='draft')`
  10. Вернуть `partials/documents_list.html` (обновлённый список)

#### `GET /documents/{id}/download` — скачивание
- Query: `format: str = "docx"` (docx/pdf)
- Загрузить Document, проверить file_path/file_path_pdf
- `FileResponse(path, filename=...)`
- Если format=pdf и file_path_pdf is None → 404

#### `POST /documents/{id}/status` — смена статуса (HTMX)
- Параметры: `status: str = Form(...)` (draft/sent/viewed/accepted/rejected)
- При `status='sent'` → `sent_at = datetime.now()`
- Вернуть обновлённый `partials/document_row.html`

### 3. `app/routes/deals.py` (новый) — роутер сделок

Подключается в `app/main.py`.

#### `GET /deals` — список сделок
- Query: `status: str = None` (фильтр)
- Запрос: `select(Deal).options(selectinload(Deal.lead)).order_by(Deal.created_at.desc())`
- Рендер: `deals.html`

#### `POST /leads/{id}/deals` — создание сделки (HTMX)
- Параметры: `title: str = Form(...)`, `amount: float = Form(None)`
- Создать `Deal(lead_id, user_id, title, amount, status='new')`
- Вернуть `partials/deals_list.html`

#### `POST /deals/{id}/status` — смена статуса (HTMX)
- Параметры: `status: str = Form(...)`
- При `status='paid'` → `closed_at = now()`
- Вернуть обновлённую строку сделки

### 4. Шаблоны (новые)

#### `app/templates/upload_template.html`
- Список шаблонов (таблица: имя, тип, плейсхолдеры, статус, кнопка удалить)
- Форма загрузки: file input (.docx), name, doc_type (select)
- После загрузки показываются найденные плейсхолдеры

#### `app/templates/partials/documents_list.html`
- Список документов лида (таблица: тип, номер, сумма, статус, кнопки скачать .docx/.pdf)
- Форма генерации:
  - Select шаблона (по doc_type)
  - Динамические поля для доп. плейсхолдеров (amount, number — те, что не в DEFAULT_PLACEHOLDERS)
  - При выборе шаблона — HTMX-запрос для отображения нужных полей (загрузка плейсхолдеров из template.placeholders, фильтр тех, что не в DEFAULT_PLACEHOLDERS)

#### `app/templates/partials/document_form.html`
- Динамическая форма: показывает поля только для плейсхолдеров, которых нет в DEFAULT_PLACEHOLDERS
- HTMX: `hx-get="/templates/{id}/fields"` возвращает этот partial

#### `app/templates/partials/deals_list.html`
- Список сделок лида + форма создания (title, amount)

#### `app/templates/deals.html`
- Таблица сделок: title, lead.name, amount, status (select), created_at
- Фильтр по статусу

#### `app/templates/document_detail.html` (опционально)
- Детальная страница документа: реквизиты, статусы, кнопки скачивания, история

### 5. `app/templates/lead_card.html` (модификация)

Добавить 2 новых таба после «Таски»:
```html
<button class="tab-btn ..." data-tab="documents" onclick="switchTab('documents')">Документы ({{ lead.documents|length }})</button>
<button class="tab-btn ..." data-tab="deals" onclick="switchTab('deals')">Сделки ({{ lead.deals|length }})</button>
```
И соответствующие div'ы:
```html
<div id="tab-documents" class="tab-content hidden">
    {% include "partials/documents_list.html" %}
</div>
<div id="tab-deals" class="tab-content hidden">
    {% include "partials/deals_list.html" %}
</div>
```

В роуте `lead_card` добавить `selectinload(Lead.documents, Lead.deals)`.

### 6. `app/templates/base.html` (модификация)

Добавить в sidebar:
```html
<a href="/templates" class="...">Шаблоны</a>
<a href="/deals" class="...">Сделки</a>
```

### 7. `app/templates/partials/lead_info_form.html` (модификация) — фикс долга D-E

**Сейчас:** форма назначения менеджера (строка 71) вложена в форму редактирования (строка 3).

**Задача:** вынести форму назначения менеджера ЗА пределы формы редактирования. Структура:
```html
<div class="bg-white rounded-lg shadow p-6">
    <!-- Форма редактирования -->
    <form hx-post="/leads/{id}/edit" ...>
        ... все поля ...
        <button>Сохранить</button>
    </form>
    
    <!-- Назначение менеджера — ОТДЕЛЬНАЯ форма -->
    {% if users and current_user.role.value in ('supervisor', 'admin') %}
    <div class="mt-4 border-t pt-4">
        <h3 class="text-sm font-medium mb-2">Назначение менеджера</h3>
        <form hx-post="/leads/{id}/assign" hx-target="#tab-info" hx-swap="innerHTML" class="flex gap-2">
            <select name="manager_id" ...>...</select>
            <button>Назначить</button>
        </form>
    </div>
    {% endif %}
</div>
```

### 8. `app/services/phone_parser.py` (модификация) — фикс долга D-B2

**Сейчас:** regex не покрывает 2 паттерна:
- `892100200475` (11 цифр подряд без разделителей)
- `+7 (81146) 2-13-37` (5-значный код региона)

**Задача:** добавить альтернативы в PHONE_RE:

```python
PHONE_RE = re.compile(
    # 11 digits straight: 892100200475, +79210020047
    r'(?:\+?7|8)\d{10}'
    # Standard with separators: +7 (811) 523-23-36
    r'|(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    # 5-digit region code: +7 (81146) 2-13-37
    r'|(?:\+?7|8)[\s\-()]*\d{5}[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d[\s\-()]*\d'
    # 4-digit region code: (8112) 75-34-42
    r'|(?:\+?7|8)?[\s\-()]*\d{4}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'
    # Short city numbers: 72-41-80
    r'|\d{2,3}[\s\-()]*\d{2}[\s\-()]*\d{2}[\s\-()]*\d{2}'
)
```

⚠ **Важно:** альтернативы идут от длинных к коротким (жадный матч). 11-значный паттерн — первым, чтобы не перехватывался более короткими.

Обновить тесты в `if __name__ == "__main__":` блоке.

### 9. `app/main.py` (модификация)

```python
from app.routes import auth, dashboard, leads, tasks, documents, deals
app.include_router(documents.router)
app.include_router(deals.router)
```

### 10. `requirements.txt` (модификация)

Добавить:
```
docx2pdf
```

## Anti-conflict (важно для кодера)

**НЕ ТРОГАТЬ:**
- `app/models.py` — модели Deal, Document, DocumentTemplate готовы из Фазы 1
- `app/auth.py`, `app/database.py`, `app/config.py`
- `Екатерина.xlsx`, `_Вероника.xlsx`
- `.planning/`
- Существующие роуты `app/routes/auth.py`, `app/routes/dashboard.py`, `app/routes/tasks.py` — без изменений
- `app/routes/leads.py` — только добавление selectinload(documents, deals) в lead_card

**Модифицировать (аккуратно):**
- `app/main.py` — только добавление include_router
- `app/templates/base.html` — только sidebar
- `app/templates/lead_card.html` — только 2 новых таба
- `app/templates/partials/lead_info_form.html` — вынос вложенной формы (D-E)
- `app/services/phone_parser.py` — только regex PHONE_RE
- `requirements.txt` — только добавление docx2pdf

## Готово, когда (success criteria)

- [ ] D-01..D-20 — все выполнены
- [ ] `python run.py` — сервер запускается без ошибок
- [ ] `http://127.0.0.1:8000/templates` — страница шаблонов, форма загрузки
- [ ] Загрузка .docx-шаблона → создаётся DocumentTemplate, плейсхолдеры распарсены
- [ ] `http://127.0.0.1:8000/leads/1` — 7 табов (5 старых + Документы + Сделки)
- [ ] Генерация КП из карточки лида → .docx + .pdf создаются, Document-запись в БД
- [ ] Скачивание .docx и .pdf — работает (FileResponse)
- [ ] Смена статуса документа (draft→sent) через HTMX
- [ ] `http://127.0.0.1:8000/deals` — список сделок
- [ ] Создание сделки из карточки лида через HTMX
- [ ] `parse_phones('892100200475')` → полный номер
- [ ] `parse_phones('+7 (81146) 2-13-37')` → полный номер
- [ ] lead_info_form.html — нет вложенных `<form>`
- [ ] Sidebar: Шаблоны, Сделки — рабочие ссылки
- [ ] Нет `print` / `console.log` отладочного мусора

## Не готово, когда

- Загрузка шаблона не работает (UploadFile не обрабатывается)
- Генерация документа падает (python-docx ошибка, неправильный путь)
- PDF не создаётся и нет graceful fallback (должен работать хотя бы .docx)
- Плейсхолдеры не заменяются (split-run проблема не решена)
- Скачивание отдаёт 404 или пустой файл
- Вложенная форма в lead_info_form не исправлена
- Парсер телефонов всё ещё урезает 11-значные номера
- Новые табы в карточке лида не отображаются

## Что даёт эта фаза

Менеджер получает полный цикл документооборота:
- ✅ **Шаблоны** — загрузка .docx с автопарсингом плейсхолдеров
- ✅ **Генерация КП/договора/счёта** — из карточки лида, с автоподстановкой реквизитов
- ✅ **PDF** — конвертация через Word, скачивание в 1 клик
- ✅ **Статусы документов** — draft → sent → accepted/rejected
- ✅ **Сделки** — отслеживание цепочки документов, статусы new → paid
- ✅ **Долги Фазы 2 закрыты** — парсер телефонов, вложенная форма

## Следующий шаг

Фаза 4 — Аналитика супервайзера: воронка по регионам, KPI менеджеров, просадки воронки, экспорт в Excel.
