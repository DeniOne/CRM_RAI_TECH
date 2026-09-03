---
phase: 21
plan: 1
slice: contract-invoice
wave: 1
depends_on: [20]
files_modified:
  - app/models.py
  - app/database.py
  - app/templates/quote_view.html
  - requirements.txt
files_created:
  - app/services/docgen_service.py
  - app/routes/invoices.py
  - app/templates/print/invoice.html
  - app/templates/doc_view.html
  - .planning/phases/21-contract-invoice/01-PLAN.md
must_haves:
  truths:
    - "T-01: Сумма прописью: money_in_words(Decimal) → «Сто сорок пять тысяч двести рублей 00 копеек» (num2words ru + склонение руб/коп)"
    - "T-02: Из accepted-КП: «Сформировать счёт» → Document(doc_type='invoice', номер СЧ-YYYY-NNNN, amount=total, deal_id) + печатная форма PDF; «Сформировать договор» → Document(doc_type='contract', номер Д-YYYY-NNNN, docx через docxtpl)"
    - "T-03: Счёт печатается с полными реквизитами продавца (CompanyProfile) и покупателя (лид), таблицей позиций КП, суммой прописью, tax_note"
    - "T-04: Тексты счёта редактируемые (PrintTemplate kind='invoice': conditions/signature) — тот же механизм, что у КП"
    - "T-05: Отметка оплаты: Document.status='paid' + paid_at/paid_amount (ALTER ADD COLUMN) → Deal.status='paid' + closed_at → лид стадия 6 «Оплачено» (если числовая < 6)"
    - "T-06: Договор — docx через docxtpl; дефолтный шаблон генерируется кодом при первом использовании (в git не хранится); скачивание через существующий /documents/{id}/download"
    - "T-07: Повторное формирование счёта/договора по тому же КП не создаёт дублей (возврат существующего); операции только на accepted-КП"
    - "T-08: Регрессии: КП-страницы, печать КП, каталог"
context: |
  Фаза 21 milestone v2.0. Кросс-фазные truths: оплаты двигают сделку (paid,
  closed_at) и лид (стадия 6) — единственная точка синхронизации.
  Реквизиты продавца и тексты — из фазы 20 (CompanyProfile / PrintTemplate).
details:
  - "Прописью: целая часть — num2words ru capitalize, копейки цифрой + склонение"
  - "Договор: стороны/предмет/сумма через docxtpl; владелец может заменить
     шаблон файлом storage/contract_template.docx (проверяется при генерации)"
  - "Документы видны в существующем табе «Документы» карточки лида"
