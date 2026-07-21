/* Раскрывающееся меню «Задачи» в sidebar + lazy-загрузка счётчиков.
 * Паттерн как ticker.js: fetch на DOMContentLoaded, тихий фолбэк при ошибке. */
(function () {
    "use strict";

    var STORAGE_KEY = "sidebar-tasks-open";

    /* ---- Раскрытие/сворачивание ---- */
    window.toggleSidebarSection = function (groupId) {
        var group = document.getElementById(groupId);
        if (!group) return;
        var children = group.querySelector(".sidebar-children");
        var chevron = group.querySelector(".sidebar-chevron");
        var isOpen = !group.classList.contains("collapsed");

        if (isOpen) {
            group.classList.add("collapsed");
            children.style.display = "none";
            if (chevron) chevron.style.transform = "rotate(-90deg)";
            localStorage.setItem(STORAGE_KEY, "0");
        } else {
            group.classList.remove("collapsed");
            children.style.display = "";
            if (chevron) chevron.style.transform = "";
            localStorage.setItem(STORAGE_KEY, "1");
        }
    };

    /* Восстановление состояния из localStorage (по умолчанию развёрнуто) */
    function restoreState() {
        var group = document.getElementById("tasks-sidebar-group");
        if (!group) return;
        if (localStorage.getItem(STORAGE_KEY) === "0") {
            window.toggleSidebarSection("tasks-sidebar-group");
        }
    }

    /* ---- Lazy-загрузка счётчиков ---- */
    function loadCounts() {
        var box = document.getElementById("sidebar-tasks-counts");
        if (!box || box.dataset.loaded) return;
        fetch("/api/tasks/sidebar", { headers: { "HX-Request": "true" }, credentials: "same-origin" })
            .then(function (r) { if (!r.ok) throw new Error("sidebar HTTP " + r.status); return r.text(); })
            .then(function (html) {
                box.innerHTML = html;
                box.dataset.loaded = "1";
                highlightActive();
            })
            .catch(function () { box.dataset.loaded = "error"; /* тихо, как тикер */ });
    }

    /* ---- Подсветка активного подменю по ?filter= в URL ----
     * Заодно сохраняем выбранный менеджер (?manager_id=) в ссылках подменю,
     * чтобы при переходе между «Сегодня / Просроченные / ...» фильтр не сбрасывался. */
    function highlightActive() {
        var params = new URLSearchParams(window.location.search);
        var filter = params.get("filter");
        if (filter) {
            var item = document.querySelector('.sidebar-subitem[data-filter="' + filter + '"]');
            if (item) item.classList.add("bg-slate-100", "font-medium");
        }
        /* Подсветка пункта «Календарь» на странице /tasks/calendar* (у неё нет ?filter). */
        if (window.location.pathname.indexOf("/tasks/calendar") === 0) {
            var cal = document.querySelector(".sidebar-subitem[data-calendar-link]");
            if (cal) cal.classList.add("bg-slate-100", "font-medium");
        }
        var managerId = params.get("manager_id");
        if (managerId) {
            document.querySelectorAll(".sidebar-subitem").forEach(function (a) {
                /* Защита: ссылка вида /tasks/calendar без "?" раньше давала битый URL
                 * "/tasks/calendar&manager_id=...". Корректно ставим ? если его нет. */
                var sep = a.href.indexOf("?") === -1 ? "?" : "&";
                a.href = a.href + sep + "manager_id=" + managerId;
            });
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        restoreState();
        loadCounts();
    });
})();
