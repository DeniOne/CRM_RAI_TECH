// Билдер КП: typeahead-поиск товара (debounce 300ms), динамические строки,
// пересчёт сумм на лету. Сервер валидирует и пересчитывает всё заново —
// клиентские числа только для удобства менеджера (фаза 19).
(function () {
  var boot = window.QUOTE_BOOTSTRAP || { mode: 'create', items: [] };
  var rows = (boot.items || []).map(function (it) {
    return {
      product_id: it.product_id || null,
      name: it.name || '',
      sku: it.sku || '',
      unit: it.unit || 'шт',
      qty: it.qty || '1',
      price: it.price || '0',
      discount_percent: it.discount_percent || '0'
    };
  });

  var tbody = document.getElementById('items-body');
  var totalEl = document.getElementById('quote-total');
  var form = document.getElementById('quote-form');
  var searchInput = document.getElementById('product-search');
  var searchBox = document.getElementById('search-results');
  var searchTimer = null;

  function num(v) { var n = parseFloat(String(v).replace(',', '.')); return isNaN(n) ? 0 : n; }
  function fmt(n) { return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function rowAmount(r) { return Math.round(num(r.qty) * num(r.price) * (100 - num(r.discount_percent))) / 100; }

  function inp(i, field, value, extra) {
    return '<input type="text" inputmode="decimal" data-idx="' + i + '" data-field="' + field + '" value="' + esc(value) + '" ' + (extra || '') + ' class="w-full px-2 py-1 rounded-lg border border-black/10 text-right font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ink/10">';
  }

  function render() {
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-muted text-sm">Добавьте позиции поиском выше или кнопкой «Своя позиция»</td></tr>';
      totalEl.textContent = '0,00';
      return;
    }
    tbody.innerHTML = rows.map(function (r, i) {
      var nameCell = r.product_id
        ? '<span class="text-ink">' + esc(r.name) + (r.sku ? ' <span class="text-xs font-mono text-muted">' + esc(r.sku) + '</span>' : '') + '</span>'
        : '<input type="text" data-idx="' + i + '" data-field="name" value="' + esc(r.name) + '" placeholder="Наименование (своя позиция)" class="w-full px-2 py-1 rounded-lg border border-black/10 text-sm focus:outline-none focus:ring-2 focus:ring-ink/10">';
      return '<tr class="border-b border-black/5">' +
        '<td class="px-3 py-1.5">' + nameCell + '</td>' +
        '<td class="px-2 py-1.5 w-24">' + inp(i, 'qty', r.qty) + '</td>' +
        '<td class="px-2 py-1.5 w-16 text-sm text-muted">' + esc(r.unit) + '</td>' +
        '<td class="px-2 py-1.5 w-32">' + inp(i, 'price', r.price) + '</td>' +
        '<td class="px-2 py-1.5 w-24">' + inp(i, 'discount_percent', r.discount_percent) + '</td>' +
        '<td class="px-3 py-1.5 w-32 text-right font-mono text-sm" data-amount="' + i + '">' + fmt(rowAmount(r)) + '</td>' +
        '<td class="px-2 py-1.5 w-10 text-center"><button type="button" data-remove="' + i + '" class="text-red-500 hover:text-red-700 text-xl leading-none" title="Убрать">×</button></td>' +
        '</tr>';
    }).join('');
    bindRowEvents();
    recalcTotal();
  }

  function bindRowEvents() {
    tbody.querySelectorAll('input[data-field]').forEach(function (inpEl) {
      inpEl.addEventListener('input', function () {
        var i = +inpEl.dataset.idx;
        rows[i][inpEl.dataset.field] = inpEl.value;
        var cell = tbody.querySelector('[data-amount="' + i + '"]');
        if (cell) cell.textContent = fmt(rowAmount(rows[i]));
        recalcTotal();
      });
    });
    tbody.querySelectorAll('button[data-remove]').forEach(function (btn) {
      btn.addEventListener('click', function () { rows.splice(+btn.dataset.remove, 1); render(); });
    });
  }

  function recalcTotal() {
    var t = 0;
    rows.forEach(function (r) { t += rowAmount(r); });
    totalEl.textContent = fmt(Math.round(t * 100) / 100);
  }

  function addItem(r) {
    rows.push({
      product_id: r.product_id, name: r.name || '', sku: r.sku || '',
      unit: r.unit || 'шт', qty: '1', price: r.price || '0', discount_percent: '0'
    });
    render();
  }

  // Typeahead: пауза 300мс, минимум 2 символа
  searchInput.addEventListener('input', function () {
    clearTimeout(searchTimer);
    var q = searchInput.value.trim();
    if (q.length < 2) { searchBox.classList.add('hidden'); return; }
    searchTimer = setTimeout(function () {
      fetch('/api/products/search?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) { renderResults(data.items || []); })
        .catch(function () { searchBox.classList.add('hidden'); });
    }, 300);
  });

  function renderResults(items) {
    if (!items.length) { searchBox.classList.add('hidden'); return; }
    searchBox.innerHTML = items.map(function (p, i) {
      var right = p.price
        ? '<span class="font-mono text-xs float-right mt-0.5">' + fmt(+p.price) + ' ₽</span>'
        : '<span class="text-xs text-muted float-right mt-0.5">цена по запросу</span>';
      return '<button type="button" data-result="' + i + '" class="w-full text-left px-3 py-2 hover:bg-slate-100 text-sm">' +
        esc(p.name) + (p.sku ? ' <span class="font-mono text-xs text-muted">' + esc(p.sku) + '</span>' : '') + right + '</button>';
    }).join('');
    searchBox.classList.remove('hidden');
    searchBox.querySelectorAll('[data-result]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        addItem(items[+btn.dataset.result]);
        searchInput.value = '';
        searchBox.classList.add('hidden');
        searchInput.focus();
      });
    });
  }

  document.addEventListener('click', function (e) {
    if (!searchBox.contains(e.target) && e.target !== searchInput) searchBox.classList.add('hidden');
  });

  document.getElementById('add-custom').addEventListener('click', function () {
    addItem({ product_id: null });
  });

  form.addEventListener('submit', function (e) {
    var empty = rows.some(function (r) { return !r.product_id && !String(r.name).trim(); });
    if (empty) {
      e.preventDefault();
      showToast('У своей позиции заполните название', 'error');
      return;
    }
    if (!rows.length) {
      e.preventDefault();
      showToast('Добавьте хотя бы одну позицию', 'error');
      return;
    }
    document.getElementById('items_json').value = JSON.stringify(rows);
  });

  render();
})();
