document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.kanban-cards').forEach(function(el) {
        new Sortable(el, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'opacity-50',
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
});

function updateColumnCounts() {
    document.querySelectorAll('.kanban-column').forEach(function(col) {
        var count = col.querySelectorAll('.kanban-card').length;
        var badge = col.querySelector('.kanban-count');
        if (badge) badge.textContent = count;
    });
}
