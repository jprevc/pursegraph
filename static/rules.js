// Rules (docs/design/rules.md). On the Rules page, the list of links becomes a listbox: ↑/↓ (Home/End) select a
// Rule and swap in its detail, Enter or a click opens it (over the list on a phone), Alt+↑/↓ move it, and a drag
// reorders the list; the server announces every move. Keep it closes the inline delete confirmation. On the Rule
// page, the word chips widen or narrow the description condition as one run of words, and Enter in a field doesn't
// save, as only the save bar does.
(() => {
  const DETAIL_AFTER = 150;
  const fold = text => text.normalize('NFKD').replace(/\p{M}/gu, '').toUpperCase().trim();

  // ---------- The Rules page ----------
  const options = list => [...list.querySelectorAll('li[data-rule]')];
  const selected = list => list.querySelector('[aria-selected="true"]');

  const upgrade = root => {
    const list = root.querySelector?.('[data-rule-list]') || (root.matches?.('[data-rule-list]') && root);
    if (!list || list.getAttribute('role') === 'listbox') return;
    list.setAttribute('role', 'listbox');
    options(list).forEach(li => {
      const on = li.classList.contains('selected');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', on);
      li.tabIndex = on ? 0 : -1;
      li.draggable = true;
      li.querySelector('a').tabIndex = -1;
    });
    if (!selected(list) && options(list)[0]) {
      options(list)[0].tabIndex = 0;
    }
  };
  htmx.onLoad(upgrade);

  let pending = null;
  let timer = null;
  const hrefOf = li => li.querySelector('a').getAttribute('href');
  const remember = (li, opened) => {
    const url = new URL(hrefOf(li), location.href);
    if (!opened) {
      url.searchParams.set('at', url.searchParams.get('rule'));
      url.searchParams.delete('rule');
    }
    history.replaceState(history.state, '', url);
  };
  const load = li => {
    pending = htmx.ajax('GET', hrefOf(li), { source: li, target: '#rule-detail', swap: 'outerHTML' });
    return pending;
  };

  const select = (list, li) => {
    options(list).forEach(o => {
      const on = o === li;
      o.setAttribute('aria-selected', on);
      o.classList.toggle('selected', on);
      o.tabIndex = on ? 0 : -1;
    });
    li.focus();
    li.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    remember(li, false);
    clearTimeout(timer);
    timer = setTimeout(() => load(li), DETAIL_AFTER);
  };

  const open = async (list, li) => {
    const shown = document.querySelector('#rule-detail')?.dataset.rule === li.dataset.rule;
    if (selected(list) !== li) select(list, li);
    clearTimeout(timer);
    if (!shown) await load(li);
    else if (pending) await pending;
    list.closest('.md').classList.add('opened');
    remember(li, true);
    const heading = document.getElementById('rule-heading');
    heading?.focus({ preventScroll: true });
    heading?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
  };

  const move = (li, direction) => {
    const list = li.closest('[data-rule-list]');
    htmx.ajax('POST', list.dataset.moveUrl.replace('/0/', `/${li.dataset.rule}/`), {
      source: li, target: '#rules', swap: 'outerHTML', values: { direction, focus: 'option' },
    });
  };

  document.addEventListener('keydown', e => {
    const li = e.target.closest?.('[data-rule-list] > li[role="option"]');
    if (li) {
      const list = li.parentElement;
      const all = options(list);
      const i = all.indexOf(li);
      if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
        e.preventDefault();
        if (e.key === 'ArrowUp' ? i > 0 : i < all.length - 1) move(li, e.key === 'ArrowUp' ? 'up' : 'down');
        return;
      }
      const to = { ArrowUp: i - 1, ArrowDown: i + 1, Home: 0, End: all.length - 1 }[e.key];
      if (to !== undefined) {
        e.preventDefault();
        if (all[to] && all[to] !== li) select(list, all[to]);
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open(list, li);
      }
      return;
    }
    // On the Rule page only the save bar saves; Enter in a field would save with the first button.
    if (e.key === 'Enter' && e.target.matches?.('[data-rule-form] input')) e.preventDefault();
  });

  document.addEventListener('click', e => {
    const li = e.target.closest('[data-rule-list] > li[role="option"]');
    if (li) {
      e.preventDefault();
      open(li.parentElement, li);
      return;
    }
    const back = e.target.closest('[data-rule-back]');
    const list = document.querySelector('[data-rule-list]');
    if (back && list) {
      e.preventDefault();
      list.closest('.md').classList.remove('opened');
      const li = selected(list);
      if (li) {
        remember(li, false);
        li.focus();
      }
      return;
    }
    const keep = e.target.closest('[data-keep-link]');
    if (keep) {
      e.preventDefault();
      keep.closest('[data-confirm-slot]').replaceChildren();
      document.querySelector('#rule-detail [data-confirm-opener]')?.focus();
      return;
    }
    const word = e.target.closest('[data-words] button');
    if (word) widen(word);
  });

  // Drag a Rule to a new place; dropping it posts the new order and which Rule moved.
  let dragged = null;
  let before = '';
  const order = list => options(list).map(li => li.dataset.rule).join();
  document.addEventListener('dragstart', e => {
    dragged = e.target.closest?.('[data-rule-list] > li');
    if (!dragged) return;
    before = order(dragged.parentElement);
    dragged.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  });
  document.addEventListener('dragover', e => {
    const over = e.target.closest?.('[data-rule-list] > li');
    if (!dragged || !over || over === dragged) return;
    e.preventDefault();
    const box = over.getBoundingClientRect();
    over.parentElement.insertBefore(dragged, e.clientY > box.top + box.height / 2 ? over.nextSibling : over);
  });
  document.addEventListener('drop', e => { if (dragged) e.preventDefault(); });
  document.addEventListener('dragend', () => {
    if (!dragged) return;
    const list = dragged.parentElement;
    dragged.classList.remove('dragging');
    const form = document.getElementById('rule-order');
    // The hidden inputs follow their items, so the form posts the order shown.
    if (order(list) !== before) {
      form.elements.moved.value = dragged.dataset.rule;
      htmx.trigger(form, 'submit');
    }
    dragged = null;
  });

  // ---------- The Rule page: the word chips ----------
  const chips = () => [...document.querySelectorAll('[data-words] button')];
  const runText = (words, run) => run ? words.slice(run[0], run[1] + 1).join(' ').replace(/^\*/, '') : '';
  const runOf = (words, text) => {
    for (let i = 0; i < words.length; i++) {
      for (let j = i; j < words.length; j++) if (fold(runText(words, [i, j])) === fold(text)) return [i, j];
    }
    return null;
  };
  const show = run => chips().forEach((b, k) => b.setAttribute('aria-pressed', !!run && k >= run[0] && k <= run[1]));

  // A chip outside the run widens it to that word; one at its end narrows it; one inside starts over from it.
  const widen = word => {
    const all = chips();
    const words = all.map(b => b.textContent);
    const k = all.indexOf(word);
    const field = word.closest('form').elements.description_contains;
    let run = runOf(words, field.value);
    if (!run) run = [k, k];
    else if (k < run[0]) run = [k, run[1]];
    else if (k > run[1]) run = [run[0], k];
    else if (run[0] === run[1]) run = null;
    else if (k === run[0]) run = [k + 1, run[1]];
    else if (k === run[1]) run = [run[0], k - 1];
    else run = [k, k];
    field.value = runText(words, run);
    show(run);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  };
  document.addEventListener('input', e => {
    if (e.target.name !== 'description_contains' || !chips().length) return;
    show(runOf(chips().map(b => b.textContent), e.target.value));
  });
})();
