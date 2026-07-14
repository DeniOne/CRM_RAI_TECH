/* ─────────────────────────────────────────────────────────────
   datepicker.js — flatpickr на всех полях даты/даты-времени.

   Зачем: нативный <input type="date"> / "datetime-local" сабмитит
   родительскую форму при нажатии Enter (менеджеры жмут Enter, ожидая
   «применить дату», и форма уходит). Flatpickr перехватывает ввод +
   даёт явные кнопки «Установить» / «Удалить» / «Сегодня» внизу календаря.

   Формат: visible-инпут показывает d.m.Y H:i (altInput), а реальный
   value остаётся Y-m-dTH:i — тот же формат, что шлёт нативный инпут,
   поэтому серверный парсинг трогать не нужно.
   ───────────────────────────────────────────────────────────── */

// Кнопки в футере календаря. Вызываются из onReady flatpickr.
function _fpAddFooterButtons(_, __, instance) {
    var cal = instance.calendarContainer;
    if (cal.querySelector('.fp-footer')) return; // уже добавлен

    var footer = document.createElement('div');
    footer.className = 'fp-footer';

    var btnClear = document.createElement('button');
    btnClear.type = 'button';
    btnClear.className = 'fp-btn fp-clear';
    btnClear.textContent = 'Удалить';
    btnClear.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); instance.clear(); });

    var btnToday = document.createElement('button');
    btnToday.type = 'button';
    btnToday.className = 'fp-btn fp-today';
    btnToday.textContent = 'Сегодня';
    btnToday.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); instance.setDate(new Date(), true); });

    var btnApply = document.createElement('button');
    btnApply.type = 'button';
    btnApply.className = 'fp-btn fp-apply';
    btnApply.textContent = 'Установить';
    btnApply.addEventListener('click', function(e) { e.preventDefault(); e.stopPropagation(); instance.close(); });

    footer.appendChild(btnClear);
    footer.appendChild(btnToday);
    footer.appendChild(btnApply);
    cal.appendChild(footer);
}

// Перехват Enter на visible-инпуте: НЕ сабмитить форму, а закрыть пикер
// (применить выбранное). Корень проблемы «Enter = Записать».
function _fpEnterGuard(instance) {
    instance.altInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            instance.close();
        }
    });
}

function initDatepickers(root) {
    if (typeof flatpickr === 'undefined') return; // CDN не загрузился — нативный fallback
    var inputs = root.querySelectorAll('input[type="date"], input[type="datetime-local"]');
    inputs.forEach(function(el) {
        if (el._flatpickr) return; // уже инициализирован
        var withTime = el.type === 'datetime-local';
        flatpickr(el, {
            locale: 'ru',
            enableTime: withTime,
            noCalendar: false,
            // Реальное value = нативный формат: 'Y-m-d' для date, 'Y-m-dTH:i'
            // для datetime-local (сервер парсит именно так — strptime с 'T').
            dateFormat: withTime ? 'Y-m-dTH:i' : 'Y-m-d',
            altInput: true,
            altFormat: withTime ? 'd.m.Y H:i' : 'd.m.Y',   // отображение юзеру
            time_24hr: true,
            allowInput: true,
            onReady: [_fpAddFooterButtons],
            onOpen: function(_, __, inst) { _fpEnterGuard(inst); },
        });
    });
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() { initDatepickers(document); });
// HTMX подгружает формы в drawer — инициализировать после swap
document.addEventListener('htmx:afterSwap', function(e) {
    var drawer = document.getElementById('drawer-content');
    if (drawer && drawer.contains(e.detail.target)) {
        initDatepickers(e.detail.target);
    }
});
