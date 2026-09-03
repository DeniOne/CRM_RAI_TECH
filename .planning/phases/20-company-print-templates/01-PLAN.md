---
phase: 20
plan: 1
slice: company-print-templates
wave: 1
depends_on: [19]
files_modified:
  - app/models.py
  - app/database.py
  - app/main.py
  - app/templates/base.html
  - app/routes/quotes.py
  - app/templates/print/quote.html
files_created:
  - app/services/company_service.py
  - app/routes/settings.py
  - app/templates/settings_company.html
  - .planning/phases/20-company-print-templates/01-PLAN.md
must_haves:
  truths:
    - "T-01: CompanyProfile (singleton): реквизиты (название, ИНН/КПП/ОГРН, адреса, тел/email, банк, р/с/к/с, БИК, подписант), налоговый режим (НДС %/без НДС), logo_path"
    - "T-02: PrintTemplate(kind='quote'): intro/conditions/signature — тексты правятся из админки, плейсхолдеры {Клиент} {Менеджер} {Автор} {Номер} {Дата} {Действует_до} {Итого} {Компания}"
    - "T-03: {Менеджер} = ФИО назначенного на лида менеджера (fallback — автор КП); плейсхолдеры подставляются через словарь и str.replace — НЕ Jinja (пользовательские шаблоны в Jinja = RCE)"
    - "T-04: XSS-безопасность: текст шаблона и значения экранируются ДО подстановки; <script> в тексте не исполняется"
    - "T-05: Страница /settings/company (только admin): реквизиты + логотип (png/jpg ≤2МБ → storage/company/) + тексты КП + шпаргалка плейсхолдеров"
    - "T-06: Печатная форма КП: шапка с логотипом и реквизитами, тексты из шаблона, НДС-строка (по профилю), подпись; /quotes/{id}/print?preview=1 отдаёт HTML (проверка без PDF)"
    - "T-07: Регрессии: КП-страницы, каталог, прайсы"
context: |
  Запрос владельца (2026-09-04): «тексты редактируемыми без программиста — шапка
  с логотипом и реквизитами, шаблон текста с подстановкой ФИО назначенца и т.п.».
  Договор/счёт (docxtpl, сумма прописью, оплаты) переезжают в фазу 21; аналитика — фаза 22.
details:
  - "Плейсхолдеры кириллицей — владельцу удобно; справочник на странице настроек"
  - "Логотип — файл в storage/company/ (volume); в PDF через base_url"
  - "НДС: nds_enabled + nds_rate; «Без НДС» строкой, если выключен"
