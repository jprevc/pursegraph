// The Transaction row's outcome control (docs/design/transaction-row.md). The outcome is text, and only a deliberate
// choice saves it; arrow keys never do.
// - With a fine pointer, Change opens the chip panel under the row (copied from the table's `template.outcome-chips`).
//   One panel is open at a time; Escape or Cancel closes it and gives focus back to Change.
// - With a coarse pointer, Change is a native select laid over it (CSS), which saves on a confirmed pick: a touch
//   picker fires `change` only on confirm.
// Either way the row's own form posts the outcome, and the server swaps the row in with "Saved as … · Undo", which goes
// after 10 s. A failed save leaves the row as it was and says so in it, naming the outcome, with Try again.
(() => {
  const coarse = matchMedia('(pointer: coarse)');
  const SAVED_FOR = 10000;
  const rowOf = el => el.closest('tr.txn');
  const changeOf = row => row?.querySelector('[data-change]');
  const formOf = row => row.querySelector('.oc-form');

  const save = (row, value) => {
    const form = formOf(row);
    form.elements.outcome.value = value;
    form.requestSubmit();
  };

  // ---- The chip panel ----
  let open = null; // { row, panel, category }
  const close = ({ focus = true } = {}) => {
    if (!open) return;
    const { row, panel } = open;
    open = null;
    panel.remove();
    const change = changeOf(row);
    if (!change?.isConnected) return;
    change.setAttribute('aria-expanded', 'false');
    if (focus) change.focus();
  };

  const showStep = (panel, key) => {
    for (const s of panel.querySelectorAll('[data-step]:not([data-step="pairs"])')) s.hidden = s.dataset.step !== key;
  };

  const openPanel = row => {
    close({ focus: false });
    const template = row.closest('table').parentElement.querySelector('template.outcome-chips');
    if (!template) return;
    const panel = template.content.firstElementChild.cloneNode(true);
    panel.id = `${row.id}-panel`;
    const title = panel.querySelector('[data-title]');
    const [before, after = ''] = title.dataset.title.split('%(description)s');
    const name = document.createElement('b');
    name.textContent = row.querySelector('.desc').textContent;
    title.replaceChildren(before, name, after);
    title.id = `${row.id}-pick`;
    panel.querySelector('.pick').setAttribute('aria-labelledby', title.id);
    const current = row.dataset.outcome;
    if (current) panel.querySelectorAll(`[data-pick="${CSS.escape(current)}"]`).forEach(chip => chip.setAttribute('aria-current', 'true'));
    // An ambiguous Transfer side: one card per candidate for its other side, from its select.
    const candidates = row.querySelectorAll('optgroup[data-pairs] option');
    if (candidates.length) {
      const cards = panel.querySelector('.pairs');
      for (const option of candidates) {
        const card = document.createElement('button');
        card.type = 'button';
        card.dataset.pick = option.value;
        card.textContent = option.textContent;
        cards.append(card);
      }
      panel.querySelector('[data-step="pairs"]').hidden = false;
    }
    row.after(panel);
    open = { row, panel, category: '' };
    const change = changeOf(row);
    change.setAttribute('aria-expanded', 'true');
    change.setAttribute('aria-controls', panel.id);
    panel.querySelector('[data-pick], [data-category]').focus();
    panel.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  };

  document.addEventListener('click', e => {
    const change = e.target.closest('[data-change]');
    if (change) {
      const row = rowOf(change);
      if (open?.row === row) close();
      else openPanel(row);
      return;
    }
    if (!open) return;
    if (!open.panel.contains(e.target)) {
      close({ focus: false });
      return;
    }
    const chip = e.target.closest('[data-pick], [data-category], [data-cancel]');
    if (!chip) return;
    if (chip.matches('[data-cancel]')) {
      close();
    } else if (chip.matches('[data-category]')) {
      // A Category swaps the chips for its Subcategories; "‹ All Categories" goes back to it.
      const key = chip.dataset.category;
      showStep(open.panel, key);
      if (key) {
        open.category = key;
        open.panel.querySelector(`[data-step="${key}"] [data-pick]`)?.focus();
      } else {
        open.panel.querySelector(`[data-step=""] [data-category="${open.category}"]`)?.focus();
      }
    } else {
      // Focus goes back to Change first, so that the swap convention finds it again in the row swapped in.
      const { row } = open;
      close();
      save(row, chip.dataset.pick);
    }
  });

  // Captured, so that the drill-down around the row stays open.
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !open) return;
    if (!open.panel.contains(document.activeElement) && !open.row.contains(document.activeElement)) return;
    e.stopPropagation();
    close();
  }, true);

  // ---- The native select, with a coarse pointer ----
  document.addEventListener('change', e => {
    const select = e.target.closest('.oc-form select');
    if (select && coarse.matches && select.value) select.form.requestSubmit();
  });

  // ---- After a save: the saved line, Undo and a failure ----
  document.addEventListener('htmx:afterSettle', e => {
    for (const line of document.querySelectorAll('[data-saved]:not([data-timed])')) {
      line.dataset.timed = '';
      setTimeout(() => {
        if (!line.isConnected) return;
        const had = line.contains(document.activeElement);
        const row = rowOf(line);
        line.remove();
        if (had) changeOf(row)?.focus();
      }, SAVED_FOR);
    }
    // Undo takes its line with it; focus goes back to the row's Change.
    if (/^\/transactions\/\d+\/undo\/$/.test(e.detail.requestConfig?.path || '')) {
      changeOf(document.getElementById(e.detail.target?.id))?.focus();
    }
  });

  // The outcome a form is sending, to name it if the save fails.
  document.addEventListener('htmx:beforeRequest', e => {
    const form = e.detail.elt.closest?.('.oc-form');
    if (!form) return;
    const select = form.elements.outcome;
    form.dataset.tried = select.value;
    form.dataset.triedLabel = select.selectedOptions[0]?.textContent || '';
    rowOf(form).querySelector('.oc-failed')?.remove();
  });

  const fail = e => {
    const form = e.detail.elt.closest?.('.oc-form');
    const status = e.detail.xhr?.status;
    // A lost session goes to log in (swap.js).
    if (!form || status === 401 || status === 403) return;
    const row = rowOf(form);
    const { tried, triedLabel, failed, retry } = form.dataset;
    const message = failed.replace('%(outcome)s', triedLabel);
    const line = document.createElement('p');
    line.className = 'oc-failed';
    line.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-alert"/></svg>';
    const words = document.createElement('span');
    words.textContent = message;
    const again = document.createElement('button');
    again.type = 'button';
    again.className = 'link';
    again.textContent = retry;
    again.addEventListener('click', () => save(row, tried));
    line.append(words, again);
    row.querySelector('[data-saved]')?.remove();
    row.querySelector('.oc').append(line);
    document.dispatchEvent(new CustomEvent('announce', { detail: { value: message } }));
  };
  document.addEventListener('htmx:responseError', fail);
  document.addEventListener('htmx:sendError', fail);
})();
