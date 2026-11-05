// The Split editor (docs/design/split-editor.md): a modal dialog, copied from the page's `template.split-editor`, that
// splits one Transaction, or a Review queue group of several, into Parts. The server judges the Split (a refusal is
// a 400 whose text the status line shows); this keeps the bar, the rest and the status line as the Member types.
// - Opens from the chip panel's "Split into Parts…", from Change on a Split Transaction (instead of the chip panel),
//   from the native select's "Split into Parts…" / "Edit the Split…" with a coarse pointer, and from the Review
//   queue's decide box.
// - The last Part fills itself with what's left of each Transaction until the Member types in it; in a group, an
//   amount typed in the first row is offered to the rows under it.
// - Save posts through HTMX, so that the swap convention (swap.js) keeps the button busy and the server's
//   announcement is read out; the row, or the Review queue, swaps in with "Saved as a Split … · Undo".
(() => {
  const coarse = matchMedia('(pointer: coarse)');
  const fill = (text, values) => text.replace(/%\((\w+)\)s/g, (_, name) => values[name]);
  const money = cents => window.Figures.money(cents / 100);
  const typedAs = cents => (cents / 100).toFixed(2).replace('.', ',');
  const icon = name => `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  const announce = value => document.dispatchEvent(new CustomEvent('announce', { detail: { value } }));

  // An amount as typed, "1.234,56", "61,20" or "61.20", in cents; null when empty, NaN when it isn't one.
  const cents = text => {
    let digits = text.replace(/[^\d,.]/g, '');
    if (!digits) return null;
    if (digits.includes(',')) digits = digits.replace(/\./g, '').replace(',', '.');
    const value = Number(digits);
    return Number.isFinite(value) ? Math.round(value * 100) : NaN;
  };

  let ed = null;

  // ---- Opening ----
  // `rows`: [{ pk, total (cents, unsigned), label }]; `parts`: [[Subcategory id, cents]] of a Split reopened, or
  // `first`, Part 1's Subcategory.
  const open = ({ template, opener, rows, sign, title, meta, parts, first, url, target, values, row }) => {
    const dialog = template.content.firstElementChild.cloneNode(true);
    const words = dialog.dataset;
    const kind = sign < 0 ? 'spending' : 'income';
    const choices = dialog.querySelector('.sp-choices');
    for (const group of choices.querySelectorAll('optgroup')) if (group.dataset.kind !== kind) group.remove();
    const known = id => id && choices.querySelector(`option[value="${CSS.escape(String(id))}"]`) ? String(id) : '';
    const untyped = () => rows.map(() => ({ text: '', typed: false }));
    ed = {
      dialog, words, rows, sign, url, target, values, opener, row, choices,
      parts: parts?.length
        ? parts.map(([sub, amount], i) => ({
          sub: known(sub),
          // The last Part shows the rest again, which is its amount.
          vals: rows.map(() => (i < parts.length - 1 ? { text: typedAs(Math.abs(amount)), typed: true } : { text: '', typed: false })),
        }))
        : [{ sub: known(first), vals: untyped() }, { sub: '', vals: untyped() }],
    };
    dialog.querySelector('#sp-title').textContent = title;
    dialog.querySelector('.sp-meta').textContent = meta;
    dialog.querySelector('.sp-total').textContent = money(sign * rows.reduce((sum, r) => sum + r.total, 0));
    dialog.querySelector('[data-sp-one]').hidden = !(parts?.length && row && !coarse.matches);
    dialog.classList.toggle('group', rows.length > 1);
    document.body.append(dialog);
    build();
    dialog.showModal();
    dialog.querySelector('.sp-parts select:not(:disabled)')?.focus();
  };

  const close = ({ focus = true } = {}) => {
    if (!ed) return;
    const { dialog, opener } = ed;
    ed = null;
    if (dialog.open) dialog.close();
    dialog.remove();
    if (focus && opener?.isConnected) opener.focus();
  };

  // ---- The Parts: selects and amount fields ----
  const select = (part, i) => {
    const el = ed.choices.cloneNode(true);
    el.hidden = false;
    el.disabled = false;
    el.className = 'sp-sel';
    el.dataset.part = i;
    el.setAttribute('aria-label', fill(ed.words.part, { number: i + 1 }));
    for (const option of el.options) option.dataset.label = option.textContent;
    el.value = part.sub;
    return el;
  };
  const amountField = (i, r, label) => {
    const wrap = document.createElement('span');
    wrap.className = 'sp-amt';
    wrap.innerHTML = '<input type="text" inputmode="decimal" autocomplete="off" spellcheck="false"><span aria-hidden="true">€</span>';
    const input = wrap.firstElementChild;
    input.dataset.part = i;
    input.dataset.row = r;
    input.dataset.name = label;
    return wrap;
  };
  const removeButton = i => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost icon-button sp-x';
    button.dataset.spRemove = i;
    button.setAttribute('aria-label', fill(ed.words.remove, { number: i + 1 }));
    button.innerHTML = icon('x');
    return button;
  };
  const dot = () => {
    const el = document.createElement('i');
    el.className = 'dot';
    el.setAttribute('aria-hidden', 'true');
    return el;
  };

  const build = () => {
    const { parts, rows, words } = ed;
    const area = ed.dialog.querySelector('.sp-parts');
    const removable = parts.length > 2;
    if (rows.length === 1) {
      // One line per Part: its dot, Subcategory, amount and remove.
      area.replaceChildren(...parts.map((part, i) => {
        const line = document.createElement('div');
        line.className = 'sp-line';
        line.append(dot(), select(part, i), amountField(i, 0, fill(words.amountOf, { number: i + 1 })));
        line.append(removable ? removeButton(i) : document.createElement('span'));
        return line;
      }));
    } else {
      // A table: a column per Part, its Subcategory chosen once at the top; a row per Transaction.
      const table = document.createElement('table');
      table.className = 'sp-table';
      const head = table.createTHead().insertRow();
      head.append(document.createElement('td'));
      parts.forEach((part, i) => {
        const th = document.createElement('th');
        th.scope = 'col';
        const col = document.createElement('div');
        col.className = 'sp-col';
        col.append(dot(), select(part, i));
        if (removable) col.append(removeButton(i));
        th.append(col);
        head.append(th);
      });
      const body = table.createTBody();
      rows.forEach((row, r) => {
        const tr = body.insertRow();
        const th = document.createElement('th');
        th.scope = 'row';
        th.innerHTML = '<span class="fig sp-date"></span> <span class="pill"></span> <span class="fig sp-of"></span>';
        th.querySelector('.sp-date').textContent = row.date;
        th.querySelector('.pill').textContent = row.account;
        th.querySelector('.sp-of').textContent = money(ed.sign * row.total);
        tr.append(th);
        parts.forEach((part, i) => {
          const td = tr.insertCell();
          // On a phone, where the table is a block per Transaction, each field is labelled with its Part.
          const label = document.createElement('span');
          label.className = 'sp-lab';
          label.dataset.part = i;
          label.setAttribute('aria-hidden', 'true');
          td.append(label, amountField(i, r, fill(words.amountFor, { row: row.label, number: i + 1 })));
        });
      });
      area.replaceChildren(table);
    }
    refresh();
  };

  // ---- What each field holds, and what's wrong ----
  // cents[part][row]: typed, offered from the first row, or the rest; `auto` where the Member didn't type it.
  const amounts = () => {
    const { parts, rows } = ed;
    const last = parts.length - 1;
    return rows.map((row, r) => {
      const shown = parts.map((part, i) => {
        const val = part.vals[r];
        if (val.typed) return { cents: cents(val.text), auto: false };
        if (i === last) return null;
        const above = part.vals[0];
        if (r > 0 && above.typed) return { cents: cents(above.text), auto: true };
        return { cents: null, auto: false };
      });
      if (!shown[last]) {
        const others = shown.slice(0, last).reduce((sum, s) => sum + (s.cents > 0 ? s.cents : 0), 0);
        const rest = row.total - others;
        shown[last] = { cents: rest > 0 ? rest : null, auto: true };
      }
      return shown;
    });
  };

  const problems = shown => {
    const { parts, rows, words } = ed;
    const prefix = r => (rows.length > 1 ? `${rows[r].label}: ` : '');
    const found = [];
    shown.forEach((row, r) => {
      const sum = row.reduce((total, s) => total + (s.cents > 0 ? s.cents : 0), 0);
      const left = rows[r].total - sum;
      if (left > 0) found.push(prefix(r) + fill(words.left, { amount: money(left) }));
      if (left < 0) found.push(prefix(r) + fill(words.over, { over: money(-left), total: money(rows[r].total) }));
    });
    parts.forEach((part, i) => {
      if (!part.sub) found.push(fill(words.noSubcategory, { number: i + 1 }));
    });
    const seen = new Map();
    parts.forEach((part, i) => {
      if (!part.sub) return;
      if (seen.has(part.sub)) {
        const outcome = ed.choices.querySelector(`option[value="${CSS.escape(part.sub)}"]`).textContent;
        found.push(fill(words.both, { first: seen.get(part.sub) + 1, second: i + 1, outcome }));
      } else seen.set(part.sub, i);
    });
    shown.forEach((row, r) => row.forEach((s, i) => {
      if (s.cents === null || Number.isNaN(s.cents)) found.push(prefix(r) + fill(words.noAmount, { number: i + 1 }));
      else if (s.cents <= 0) found.push(prefix(r) + fill(words.zero, { number: i + 1, zero: money(0) }));
    }));
    return found;
  };

  const hueOf = sub => sub && ed.choices.querySelector(`option[value="${CSS.escape(sub)}"]`)?.dataset.hue;

  const refresh = () => {
    const { dialog, parts, rows, words } = ed;
    const shown = amounts();
    // The fields, but not the one being typed in.
    for (const input of dialog.querySelectorAll('.sp-amt input')) {
      const s = shown[+input.dataset.row][+input.dataset.part];
      const last = +input.dataset.part === parts.length - 1;
      if (input !== document.activeElement || s.auto) {
        const val = parts[+input.dataset.part].vals[+input.dataset.row];
        input.value = val.typed ? val.text : s.cents > 0 ? typedAs(s.cents) : '';
      }
      input.classList.toggle('auto', s.auto && s.cents > 0);
      input.setAttribute('aria-label', last && s.auto ? fill(words.theRest, { name: input.dataset.name }) : input.dataset.name);
    }
    // Each Part's dot and hue, and a Subcategory another Part has taken.
    const taken = parts.map(p => p.sub);
    for (const el of dialog.querySelectorAll('.sp-sel')) {
      const i = +el.dataset.part;
      for (const option of el.options) {
        const other = option.value && option.value !== parts[i].sub && taken.includes(option.value);
        option.disabled = other;
        option.textContent = other ? fill(words.taken, { outcome: option.dataset.label }) : option.dataset.label;
      }
      const hue = hueOf(parts[i].sub);
      const holder = el.closest('.sp-line, .sp-col');
      holder.style.setProperty('--hue', hue ? `var(--${hue})` : '');
      holder.querySelector('.dot').classList.toggle('awaiting', !hue);
    }
    for (const label of dialog.querySelectorAll('.sp-lab')) {
      const i = +label.dataset.part;
      const option = parts[i].sub && ed.choices.querySelector(`option[value="${CSS.escape(parts[i].sub)}"]`);
      label.textContent = option ? option.textContent : fill(words.part, { number: i + 1 });
    }
    // The bar: each Part's share of the whole, what's left hatched, an overrun in Ink.
    const total = rows.reduce((sum, r) => sum + r.total, 0);
    const per = parts.map((_, i) => shown.reduce((sum, row) => sum + (row[i].cents > 0 ? row[i].cents : 0), 0));
    const placed = per.reduce((sum, c) => sum + c, 0);
    const bar = dialog.querySelector('.sp-bar');
    bar.replaceChildren();
    per.forEach((c, i) => {
      if (c <= 0) return;
      const seg = document.createElement('i');
      seg.style.flex = String(c);
      const hue = hueOf(parts[i].sub);
      if (hue) seg.style.setProperty('--hue', `var(--${hue})`);
      else seg.className = 'awaiting';
      bar.append(seg);
    });
    if (placed !== total) {
      const seg = document.createElement('i');
      seg.className = placed < total ? 'left' : 'over';
      seg.style.flex = String(Math.abs(total - placed));
      bar.append(seg);
    }
    // The status line and Save, which says why it can't rather than going grey.
    const found = problems(shown);
    const status = dialog.querySelector('.sp-status');
    status.classList.toggle('bad', found.length > 0);
    if (found.length) {
      status.innerHTML = `${icon('alert')}<span></span>`;
      status.lastChild.textContent = found[0];
      if (found.length > 1) {
        const more = document.createElement('span');
        more.className = 'muted';
        more.textContent = ` ${fill(words.more, { count: found.length - 1 })}`;
        status.append(more);
      }
    } else {
      status.innerHTML = `${icon('check')}<span></span>`;
      status.lastChild.textContent = rows.length > 1
        ? fill(words.readyGroup, { count: rows.length })
        : fill(words.readyOne, { count: parts.length, total: money(total) });
    }
    const save = dialog.querySelector('[data-sp-save]');
    save.textContent = rows.length > 1 ? fill(words.saveGroup, { count: rows.length }) : words.saveOne;
    if (found.length) {
      save.setAttribute('aria-disabled', 'true');
      save.setAttribute('aria-describedby', 'sp-why');
    } else {
      save.removeAttribute('aria-disabled');
      save.removeAttribute('aria-describedby');
    }
    ed.ready = found.length === 0;
    ed.shown = shown;
  };

  // ---- Saving ----
  const save = () => {
    if (!ed.ready) {
      announce(ed.dialog.querySelector('.sp-status').textContent.trim());
      return;
    }
    const values = { ...ed.values, subcategory: ed.parts.map(p => p.sub) };
    ed.rows.forEach((row, r) => {
      values[`amount-${row.pk}`] = ed.shown[r].map(s => (s.cents / 100).toFixed(2));
    });
    htmx.ajax('POST', ed.url, { source: ed.dialog.querySelector('[data-sp-save]'), target: ed.target, swap: 'outerHTML', values });
  };

  // A swap's events name its target as `elt`; the element that sent it is the request's.
  const ours = e => ed && (e.detail.requestConfig?.elt || e.detail.elt) === ed.dialog.querySelector('[data-sp-save]');
  // Saved: the dialog goes before the swap, as the page under a modal dialog can't take focus.
  document.addEventListener('htmx:beforeSwap', e => {
    if (!ours(e) || !e.detail.shouldSwap) return;
    const { row } = ed;
    close({ focus: false });
    if (!row) return;
    // After swap.js has settled the row, focus goes to its Change, as after any other save.
    const id = row.id;
    document.addEventListener('htmx:afterSettle', () => {
      const swapped = document.getElementById(id);
      const change = swapped?.querySelector(coarse.matches ? '.oc-form select' : '[data-change]');
      change?.focus({ preventScroll: true });
    }, { once: true });
  });
  const fail = e => {
    if (!ours(e)) return;
    const status = ed.dialog.querySelector('.sp-status');
    const why = e.detail.xhr?.status === 400 && e.detail.xhr.responseText ? e.detail.xhr.responseText : ed.words.failed;
    status.classList.add('bad');
    status.innerHTML = `${icon('alert')}<span></span>`;
    status.lastChild.textContent = why;
    announce(why);
  };
  document.addEventListener('htmx:responseError', fail);
  document.addEventListener('htmx:sendError', fail);

  // ---- Inside the dialog ----
  document.addEventListener('input', e => {
    const input = e.target.closest?.('.sp-dialog .sp-amt input');
    if (!input || !ed) return;
    const val = ed.parts[+input.dataset.part].vals[+input.dataset.row];
    // Emptied, it fills itself again.
    val.text = input.value;
    val.typed = input.value.trim() !== '';
    refresh();
  });
  // An amount filled in for the Member is selected whole, so that typing replaces it.
  document.addEventListener('focusin', e => {
    const input = e.target.closest?.('.sp-dialog .sp-amt input.auto');
    if (input) input.select();
  });
  document.addEventListener('change', e => {
    const el = e.target.closest?.('.sp-dialog .sp-sel');
    if (!el || !ed) return;
    ed.parts[+el.dataset.part].sub = el.value;
    refresh();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && ed && e.target.closest?.('.sp-dialog .sp-amt input')) {
      e.preventDefault();
      save();
    }
  });
  document.addEventListener('click', e => {
    if (!ed || !ed.dialog.contains(e.target)) return;
    // The scrim: a click outside the dialog's box lands on the dialog itself.
    if (e.target === ed.dialog) {
      const box = ed.dialog.getBoundingClientRect();
      const inside = e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom;
      if (!inside) close();
      return;
    }
    const button = e.target.closest('button');
    if (!button) return;
    if (button.matches('[data-sp-cancel]')) close();
    else if (button.matches('[data-sp-save]')) save();
    else if (button.matches('[data-sp-add]')) {
      // The old last Part keeps what it shows now; the new one takes the rest.
      const last = ed.parts[ed.parts.length - 1];
      last.vals.forEach((val, r) => {
        const s = ed.shown[r][ed.parts.length - 1];
        if (!val.typed && s.cents > 0) Object.assign(val, { text: typedAs(s.cents), typed: true });
      });
      ed.parts.push({ sub: '', vals: ed.rows.map(() => ({ text: '', typed: false })) });
      build();
      ed.dialog.querySelector(`.sp-sel[data-part="${ed.parts.length - 1}"]`).focus();
    } else if (button.matches('[data-sp-remove]')) {
      const i = +button.dataset.spRemove;
      ed.parts.splice(i, 1);
      build();
      ed.dialog.querySelector(`.sp-sel[data-part="${Math.min(i, ed.parts.length - 1)}"]`).focus();
    } else if (button.matches('[data-sp-one]')) {
      // One outcome instead of the Split: the chip panel, as for any other Transaction.
      const change = ed.row.querySelector('[data-change]');
      close({ focus: false });
      bypass = true;
      change.click();
      bypass = false;
    }
  });
  // Escape, or the dialog closed any other way.
  document.addEventListener('cancel', e => {
    if (ed && e.target === ed.dialog) {
      e.preventDefault();
      close();
    }
  }, true);

  // ---- The ways in ----
  const fromRow = (row, opener) => {
    const template = row.closest('table')?.parentElement.querySelector('template.split-editor');
    if (!template) return;
    const amount = Number(row.dataset.amount);
    const parts = row.dataset.parts ? row.dataset.parts.split(',').map(p => p.split(':')).map(([sub, a]) => [sub, Math.round(Number(a) * 100)]) : null;
    const words = template.content.firstElementChild.dataset;
    const date = row.querySelector('.c-date').textContent.trim();
    const account = row.querySelector('.c-acct .pill').textContent.trim();
    const description = row.querySelector('.desc').textContent.trim();
    open({
      template,
      opener,
      rows: [{ pk: row.id.replace('transaction-', ''), total: Math.round(Math.abs(amount) * 100), label: '' }],
      sign: amount < 0 ? -1 : 1,
      title: words.title,
      meta: `${description} · ${date} · ${account}`,
      parts,
      first: /^\d+$/.test(row.dataset.outcome) ? row.dataset.outcome : '',
      url: row.dataset.splitUrl,
      target: `#${row.id}-rows`,
      values: {},
      row,
    });
  };

  const fromReview = opener => {
    const data = JSON.parse(document.getElementById('split-group').textContent);
    const template = document.querySelector('#review template.split-editor');
    const words = template.content.firstElementChild.dataset;
    const form = opener.closest('form');
    const rows = data.rows.map(row => {
      const total = Math.round(Math.abs(Number(row.amount)) * 100);
      return { pk: row.pk, total, date: row.date, account: row.account, label: fill(words.row, { date: row.date, amount: money(total) }) };
    });
    const sign = Number(data.rows[0].amount) < 0 ? -1 : 1;
    const total = rows.reduce((sum, r) => sum + r.total, 0);
    open({
      template,
      opener,
      rows,
      sign,
      title: rows.length > 1 ? fill(words.groupTitle, { count: rows.length, description: data.description }) : words.title,
      meta: rows.length > 1 ? fill(words.groupMeta, { count: rows.length, total: money(total) }) : data.description,
      first: data.first,
      url: data.url,
      target: '#review',
      values: {
        transaction: rows.map(r => r.pk),
        ...(form.elements.resolved ? { resolved: form.elements.resolved.value } : {}),
      },
    });
  };

  // Change on a Split opens its editor rather than the chip panel; captured, before outcome.js sees the click.
  let bypass = false;
  window.addEventListener('click', e => {
    const opener = e.target.closest?.('[data-split-open]');
    if (opener) {
      const panel = opener.closest('tr.chip-panel');
      if (panel) {
        const row = panel.previousElementSibling;
        // Cancel closes the chip panel and gives focus back to Change, which the dialog then gives it back to.
        panel.querySelector('[data-cancel]').click();
        fromRow(row, row.querySelector('[data-change]'));
      } else if (opener.closest('.decide')) {
        fromReview(opener);
      }
      e.stopPropagation();
      return;
    }
    const change = e.target.closest?.('tr.txn.is-split [data-change]');
    if (change && !bypass) {
      e.stopPropagation();
      fromRow(change.closest('tr.txn'), change);
    }
  }, true);

  // The native select's "Split into Parts…" / "Edit the Split…", picked in the picker a tap opened (as outcome.js).
  const tapped = new WeakSet();
  document.addEventListener('pointerdown', e => {
    const el = e.target.closest?.('.oc-form select');
    if (el) tapped.add(el);
  });
  document.addEventListener('keydown', e => {
    const el = e.target.closest?.('.oc-form select');
    if (el) tapped.delete(el);
  });
  window.addEventListener('change', e => {
    const el = e.target.closest?.('.oc-form select');
    if (!el || el.value !== 'split') return;
    e.stopPropagation();
    el.form.reset();
    if (coarse.matches && tapped.has(el)) fromRow(el.closest('tr.txn'), el);
  }, true);
})();
