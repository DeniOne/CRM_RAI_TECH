/* Бегущая строка задач — клиентская карусель.
 * Пауза 3.5с на окно из 3 чипов, затем сдвиг на 1 позицию вправо-налево,
 * зациклено. Данные статичны (грузятся разово через htmx при загрузке страницы).
 */
(function () {
    "use strict";

    const PAUSE_MS = 3500;
    const SHIFT_MS = 500;
    const VISIBLE = 3; // сколько чипов видно одновременно

    function initTrack(window) {
        if (!window || window.dataset.tickerReady) return;
        const track = window.querySelector(".ticker-track");
        if (!track) return;
        const items = Array.from(track.querySelectorAll(".ticker-item"));
        if (items.length === 0) {
            window.dataset.tickerReady = "1";
            return;
        }
        if (items.length <= VISIBLE) {
            // Места хватает — карусель не нужна, показываем статично.
            window.dataset.tickerReady = "1";
            return;
        }

        // Клонируем первые VISIBLE элементов в конец для бесшовного зацикливания.
        for (let i = 0; i < VISIBLE; i++) {
            track.appendChild(items[i].cloneNode(true));
        }

        let pos = 0;
        let itemWidth = items[0].getBoundingClientRect().width
            + parseFloat(getComputedStyle(track).gap || "0") || 0;
        if (itemWidth <= 0) itemWidth = 200; // запас на случай скрытого рендера

        function step() {
            pos++;
            track.style.transition = "transform " + SHIFT_MS + "ms ease";
            track.style.transform = "translateX(-" + (pos * itemWidth) + "px)";

            if (pos >= items.length) {
                setTimeout(function () {
                    track.style.transition = "none";
                    track.style.transform = "translateX(0)";
                    pos = 0;
                    itemWidth = items[0].getBoundingClientRect().width
                        + parseFloat(getComputedStyle(track).gap || "0") || 200;
                }, SHIFT_MS + 20);
            }
            setTimeout(step, PAUSE_MS);
        }

        window.dataset.tickerReady = "1";
        setTimeout(step, PAUSE_MS);
    }

    function initAll(scope) {
        const root = scope || document;
        root.querySelectorAll(".ticker-window").forEach(initTrack);
    }

    // Запуск после готовности DOM.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { initAll(); });
    } else {
        initAll();
    }

    // htmx подгрузил partial тикера — переинициализируем треки.
    // Важно: событие htmx стреляет на document, НЕ на body.
    document.addEventListener("htmx:afterSwap", function (e) {
        const target = e.detail && e.detail.target;
        if (target && (target.id === "task-ticker" || target.querySelector(".ticker-window"))) {
            initAll(target.id === "task-ticker" ? target : target.parentElement);
        }
    });

    // Запасной запуск: если htmx по какой-то причине не стрельнул afterSwap
    // (или тикер отрисован сервером инлайн), попробуем через 2с.
    setTimeout(function () {
        const bar = document.getElementById("task-ticker");
        if (bar && bar.querySelector(".ticker-window") && !bar.querySelector('[data-ticker-ready]')) {
            initAll(bar);
        }
    }, 2000);
})();
