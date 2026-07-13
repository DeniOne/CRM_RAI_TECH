function initSortable() {
    document.querySelectorAll('.kanban-cards').forEach(function(el) {
        if (el._sortable) return;
        el._sortable = new Sortable(el, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'opacity-50',
            // Автоскролл горизонтального kanban-board при drag у правого/левого края.
            // forceFallback обязателен: нативный HTML5-drag плохо автоскроллит
            // горизонтальные контейнеры в большинстве браузеров.
            forceFallback: true,
            bubbleScroll: true,
            scroll: true,
            scrollSensitivity: 80,
            scrollSpeed: 15,
            onEnd: function(evt) {
                var leadId = evt.item.dataset.leadId;
                var toStage = evt.to.dataset.stage;
                var fromStage = evt.from.dataset.stage;

                if (fromStage === toStage) return;

                var formData = new FormData();
                formData.append('stage', toStage);

                fetch('/api/leads/' + leadId + '/stage', {
                    method: 'POST',
                    body: formData
                }).then(function(resp) {
                    if (!resp.ok) {
                        evt.from.insertBefore(evt.item, evt.from.children[evt.oldIndex]);
                        return resp.json().then(function(data) {
                            var errors = data.detail && data.detail.errors ? data.detail.errors : ['Ошибка смены стадии'];
                            alert('Невозможно сменить стадию:\n' + errors.join('\n'));
                        });
                    }
                    updateColumnCounts();
                }).catch(function() {
                    evt.from.insertBefore(evt.item, evt.from.children[evt.oldIndex]);
                });
            }
        });
    });
}

function updateColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(function(col) {
        var count = col.querySelectorAll('.kanban-card').length;
        var badge = col.querySelector('.kanban-count');
        if (badge) badge.textContent = count;
    });
}

document.addEventListener('DOMContentLoaded', initSortable);

document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target && evt.detail.target.id === 'kanban-board') {
        document.querySelectorAll('.kanban-cards').forEach(function(el) {
            el._sortable = null;
        });
        initSortable();
    }
});
