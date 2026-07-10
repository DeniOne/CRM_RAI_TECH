# README-CONTRACT — Phase 3: Документооборот и сделки

**Phase:** 3 — documents-deals
**Verdict:** **PARTIAL**
**Author (Tech Lead):** @zcode-assistant
**Coder:** mimo
**Date:** 2026-07-11

---

## Итоговый вердикт: PARTIAL

Фаза 3 функционально завершена: загрузка .docx-шаблонов с автопарсингом плейсхолдеров, генерация документов с заменой → .docx + PDF, скачивание, статусы, сделки. Пайплайн документов проверен end-to-end. Но есть 1 блокирующий баг (создание сделки → 500) и 2 некритичных долга.

---

## D-критерии — сводка

| # | Критерий | Статус | Примечание |
|---|---|:---:|---|
| D-01 | extract_placeholders: парсинг {placeholder} из параграфов, таблиц, колонтитулов | ✅ | Проверено: test_kp.docx → `['company_name', 'date', 'inn', 'manager_name']` |
| D-02 | generate_document: замена split-run safe (paragraph-level merge) | ✅ | Проверено: все плейсхолдеры заменены, 0 незаменённых |
| D-03 | convert_to_pdf через docx2pdf, graceful fallback | ✅ | Проверено: PDF создан (52497 bytes), конвертация через Word COM |
| D-04 | DEFAULT_PLACEHOLDERS: 14 авто-полей из Lead | ✅ | company_name, inn, district, settlement, address, head_name, site, region, manager_name, date, phone, email, rapeseed_volume, harvest_timing |
| D-05 | GET /templates — список + форма загрузки | ✅ | 200, форма рендерится |
| D-06 | POST /templates/upload — приём .docx, автопарсинг плейсхолдеров → JSON | ✅ | Проверено: шаблон загружен, DocumentTemplate создан, placeholders в JSON |
| D-07 | POST /templates/{id}/delete — soft delete (is_active=False) | ✅ | Реализован |
| D-08 | GET /leads/{id}/documents — список + форма генерации | ✅ | 200, форма с выбором шаблона |
| D-09 | POST /leads/{id}/documents/generate — генерация .docx + .pdf + Document-запись | ✅ | Проверено end-to-end: .docx (37753 bytes) + .pdf (52497 bytes), Document в БД |
| D-10 | GET /documents/{id}/download?format=docx\|pdf — FileResponse | ✅ | Проверено: оба формата отдаются (200) |
| D-11 | POST /documents/{id}/status — HTMX смена статуса, sent_at при 'sent' | ✅ | Проверено: draft→sent, sent_at записан |
| D-12 | GET /deals — список сделок с фильтром | ✅ | 200, страница рендерится |
| D-13 | POST /leads/{id}/deals — создание сделки через HTMX | ❌ | **БАГ**: 500 Internal Server Error. `create_deal` не использует `selectinload(Deal.lead)`, шаблон `deal_row.html` обращается к `deal.lead.name` → lazy-load → `MissingGreenlet` |
| D-14 | POST /deals/{id}/status — смена статуса сделки | ✅ | Реализован с `selectinload(Deal.lead)` |
| D-15 | Карточка лида: 7 табов (5 старых + Документы + Сделки) | ✅ | Проверено: все 7 табов в HTML |
| D-16 | Sidebar: Шаблоны, Сделки | ✅ | Проверено в HTML |
| D-17 | phone_parser: 11 цифр подряд + 5-значные коды | ✅ | Все 6 тестов PASS: `892100200475`, `+7 (81146) 2-13-37` и др. |
| D-18 | lead_info_form.html: форма назначения менеджера вынесена | ✅ | Проверено: `</form>` на строке 71, форма assign — на строке 76, вне внешней формы |
| D-19 | requirements.txt: добавлен docx2pdf | ✅ | Проверено |
| D-20 | Файлы в storage/documents/{lead_id}/doc_{ts}.docx + .pdf | ✅ | Проверено: `storage/documents/1/doc_1783719003.docx` + `.pdf` |

**Итог:** 19/20 PASS, 1 FAIL (D-13 — создание сделки падает с 500).

---

## Runtime-верификация

| Проверка | Результат |
|---|---|
| `GET /templates` | ✅ 200, форма загрузки |
| `POST /templates/upload` (multipart .docx) | ✅ 200, DocumentTemplate создан, плейсхолдеры распарсены |
| `GET /leads/1` — 7 табов | ✅ Информация, Контакты, Журнал, Комментарии, Таски, Документы, Сделки |
| `GET /templates/1/fields` — динамические поля | ✅ 200, корректно фильтрует DEFAULT_PLACEHOLDERS |
| `POST /leads/1/documents/generate` | ✅ 200, .docx + .pdf созданы, Document в БД |
| Замена плейсхолдеров в .docx | ✅ 0 незаменённых, значения корректны |
| `GET /documents/1/download?format=docx` | ✅ 200, 37753 bytes |
| `GET /documents/1/download?format=pdf` | ✅ 200, 52497 bytes |
| `POST /documents/1/status` (draft→sent) | ✅ 200, sent_at записан |
| `GET /deals` | ✅ 200, страница рендерится |
| `POST /leads/1/deals` (создание сделки) | ❌ 500 MissingGreenlet |
| Sidebar: Шаблоны, Сделки | ✅ |
| `parse_phones('892100200475')` | ✅ Полный номер |
| `parse_phones('+7 (81146) 2-13-37')` | ✅ Полный номер |
| lead_info_form.html — нет вложенных `<form>` | ✅ |

---

## Блокирующий баг: D-13 — создание сделки → 500

### Корневая причина

`app/routes/deals.py`, функция `create_deal` (строка 62):

```python
result = await session.execute(
    select(Deal).where(Deal.lead_id == lead_id).order_by(Deal.created_at.desc())
)
deals = result.scalars().all()
```

Запрос не использует `.options(selectinload(Deal.lead))`. После commit, при рендеринге `partials/deals_list.html` → `partials/deal_row.html`, шаблон обращается к `deal.lead.name` (строка 7 deal_row.html). SQLAlchemy пытается выполнить lazy-load отношения `lead`, но в async-контексте это вызывает `MissingGreenlet`:

```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here.
```

### Сравнение с работающими роутами

| Роут | selectinload(Deal.lead)? | Результат |
|---|:---:|---|
| `GET /deals` (deals_page) | ✅ | Работает |
| `POST /deals/{id}/status` (update_deal_status) | ✅ | Работает |
| `POST /leads/{id}/deals` (create_deal) | ❌ | **500** |
| `GET /leads/{id}/deals` (lead_deals) | ❌ | **Предположительно тоже 500** (не проверен, но та же проблема) |

### Фикс

В `create_deal` и `lead_deals` добавить `.options(selectinload(Deal.lead))`:

```python
result = await session.execute(
    select(Deal).where(Deal.lead_id == lead_id)
    .options(selectinload(Deal.lead))
    .order_by(Deal.created_at.desc())
)
```

---

## Открытые долги (2 шт.)

### Долг D-G: Баг create_deal / lead_deals — MissingGreenlet (БЛОКИРУЮЩИЙ)

**Почему:** Отсутствует `selectinload(Deal.lead)` в двух роутах `deals.py`. Шаблон `deal_row.html` обращается к `deal.lead.name`.

**Когда закроется:** (a) отдельная cleanup-правка прямо сейчас — однострочный фикс в двух функциях. Включу в PLAN Фазы 4 как пре-фикс.

**Блокирует Фазу 4:** Да — создание сделок неработоспособно. Но фикс тривиальный (2 строки), не откладывает Фазу 4.

### Долг D-H: documents_list.html — `active_templates[0].id` в hx-get при пустом списке

**Почему:** В `partials/documents_list.html` строка 19:
```html
hx-get="/templates/{{ active_templates[0].id if active_templates else 0 }}/fields"
```
Если `active_templates` пуст (нет загруженных шаблонов), hx-get указывает на `/templates/0/fields` — роут вернёт 404. Не падает, но в консоли будет ошибка. Не блокирует функциональность при наличии хотя бы одного шаблона.

**Когда закроется:** (b) попутно в Фазе 5 (Redesign) — при переработке UI. Фикс: проверять `active_templates` перед рендерингом формы, показывать empty state «Загрузите шаблон» вместо формы.

**Блокирует Фазу 4:** Нет.

---

## Долги Фазы 2 — статус

| Долг | Фаза 2 статус | Фаза 3 результат |
|---|---|---|
| D-B2: Парсер телефонов | открыт | ✅ **ЗАКРЫТ** — все 6 паттернов проходят |
| D-E: Вложенная `<form>` | открыт | ✅ **ЗАКРЫТ** — форма assign вынесена за пределы формы edit |
| D-F: cleanup_data.py | closed (known-limitation) | ✅ Подтверждено — данные чистые |

---

## Архитектурные замечания (информационные)

1. **document_service.py** — чистая, хорошо структурированная реализация. `build_replacements` с try/except на каждый lambda — защитное программирование, предотвращает падение при отсутствии связей. ОК.

2. **generate_document** — split-run safe замена реализована правильно: merge → replace → first run → clear rest. Проверено: 0 незаменённых плейсхолдеров.

3. **convert_to_pdf** — graceful fallback через try/except, возвращает None при ошибке. Если docx2pdf недоступен (нет Word), документ всё равно создаётся со status='draft' и file_path_pdf=None. Правильный подход.

4. **Динамические поля шаблона** — `GET /templates/{id}/fields` возвращает только плейсхолдеры, которых нет в DEFAULT_PLACEHOLDERS. HTMX подгружает их при выборе шаблона. Хорошее UX-решение.

5. **Кодер создал тестовый шаблон** `test_kp.docx` с 4 плейсхолдерами (company_name, inn, manager_name, date) — все из DEFAULT_PLACEHOLDERS. Это позволило протестировать полный пайплайн без реальных шаблонов от заказчика.

6. **PDF-конвертация** — ~4 секунды на документ через Word COM. При массовом生成 (например, 100 КП за раз) это будет медленно. Для текущего объёма (единицы документов в день) — приемлемо. При росте — рассмотреть LibreOffice headless (параллельная конвертация).

---

## Что даёт Фаза 3 для проекта

Менеджер получил полный цикл документооборота:
- ✅ **Шаблоны** — загрузка .docx с автопарсингом плейсхолдеров
- ✅ **Генерация КП/договора/счёта** — из карточки лида, автоподстановка реквизитов
- ✅ **PDF** — конвертация через Word, скачивание в 1 клик
- ✅ **Статусы документов** — draft → sent → accepted/rejected
- ✅ **Сделки** — список с фильтрами, статусы new → paid (создание — баг D-G)
- ✅ **Долги Фазы 2 закрыты** — парсер телефонов, вложенная форма

## Следующий шаг

**Фаза 4 — Аналитика супервайзера:** воронка по регионам, KPI менеджеров, просадки воронки, экспорт в Excel. Включает пре-фикс долга D-G (selectinload в create_deal/lead_deals).
