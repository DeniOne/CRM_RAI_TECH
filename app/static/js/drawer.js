function openDrawer(url, title) {
    var overlay = document.getElementById('drawer-overlay');
    var drawer = document.getElementById('drawer');
    var content = document.getElementById('drawer-content');

    content.innerHTML = '<div class="p-6"><div class="text-lg font-medium text-ink mb-4">' + (title || '') + '</div><div class="text-muted text-sm">Загрузка...</div></div>';

    overlay.classList.remove('hidden');
    drawer.classList.add('open');

    fetch(url).then(function(resp) {
        return resp.text();
    }).then(function(html) {
        content.innerHTML = '<div class="p-6">' +
            '<div class="flex justify-between items-center mb-4">' +
            '<div class="text-lg font-medium text-ink">' + (title || '') + '</div>' +
            '<button onclick="closeDrawer()" class="text-muted hover:text-ink text-xl">&times;</button>' +
            '</div>' + html + '</div>';
    });
}

function closeDrawer() {
    document.getElementById('drawer-overlay').classList.add('hidden');
    document.getElementById('drawer').classList.remove('open');
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeDrawer();
});
