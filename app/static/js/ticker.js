/* Бегущая строка задач.
 * Загрузка: явный fetch при готовности DOM (надёжнее htmx hx-trigger=load,
 * который не всегда срабатывает на элементах вне основного прохода парсинга).
 * Карусель: пауза 3.5с на окно из 3 чипов, сдвиг на 1 вправо-налево, зациклено.
 */
(function () {
    "use strict";

    var PAUSE_MS = 3500;
    var SHIFT_MS = 500;
    var VISIBLE = 3;

    /* ---- Загрузка содержимого тикера ---- */
    function loadTicker() {
        var bar = document.getElementById("task-ticker");
        if (!bar || bar.dataset.loaded) return;

        fetch("/api/ticker", { headers: { "HX-Request": "true" }, credentials: "same-origin" })
            .then(function (r) {
                if (!r.ok) throw new Error("ticker HTTP " + r.status);
                return r.text();
            })
            .then(function (html) {
                bar.innerHTML = html;
                bar.dataset.loaded = "1";
                initAll(bar);
            })
            .catch(function (e) {
                // Тихо: тикер не критичен, не ломаем страницу.
                bar.dataset.loaded = "error";
            });
    }

    /* ---- Карусель ---- */
    function initTrack(window) {
        if (!window || window.dataset.tickerReady) return;
        var track = window.querySelector(".ticker-track");
        if (!track) return;
        var items = Array.prototype.slice.call(track.querySelectorAll(".ticker-item"));
        if (items.length === 0) {
            window.dataset.tickerReady = "1";
            return;
        }
        if (items.length <= VISIBLE) {
            // Места хватает — показываем статично, без карусели.
            window.dataset.tickerReady = "1";
            return;
        }

        // Клонируем первые VISIBLE элементов для бесшовного зацикливания.
        for (var i = 0; i < VISIBLE; i++) {
            track.appendChild(items[i].cloneNode(true));
        }

        var pos = 0;
        var items0 = items[0];
        var gap = parseFloat(getComputedStyle(track).gap || "0") || 0;

        function itemWidth() {
            var w = items0.getBoundingClientRect().width + gap;
            return w > 0 ? w : 200;
        }

        function step() {
            pos++;
            var w = itemWidth();
            track.style.transition = "transform " + SHIFT_MS + "ms ease";
            track.style.transform = "translateX(-" + (pos * w) + "px)";

            if (pos >= items.length) {
                setTimeout(function () {
                    track.style.transition = "none";
                    track.style.transform = "translateX(0)";
                    pos = 0;
                }, SHIFT_MS + 20);
            }
            setTimeout(step, PAUSE_MS);
        }

        window.dataset.tickerReady = "1";
        setTimeout(step, PAUSE_MS);
    }

    function initAll(scope) {
        var root = scope || document;
        var windows = root.querySelectorAll(".ticker-window");
        for (var i = 0; i < windows.length; i++) {
            initTrack(windows[i]);
        }
    }

    /* ---- Запуск ---- */
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadTicker);
    } else {
        loadTicker();
    }
})();
