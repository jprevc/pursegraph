// The admin pages (docs/design/admin.md): Categories, Suggestions and Members. HTMX swaps their regions; here, what
// stays in the page:
// - an inline confirmation's Keep it, which closes it and gives the focus back to the control that opened it;
// - Members' dialogs, shown modal when swapped in (or open without JS), the focus going back to their opener on close,
//   and the link dialog's Copy link;
// - Categorizers' info toggles, whose text shows open without JS;
// - the auto-accept threshold, its slider and number kept in step, moving the chart's line and recolouring its bars
//   live, with Save naming what saving does.
(() => {
  const say = message => document.dispatchEvent(new CustomEvent('announce', { detail: { value: message } }));
  const heading = () => document.querySelector('main h1');

  // Inline confirmations.
  const openers = new WeakMap();
  document.addEventListener('htmx:beforeRequest', e => {
    const opener = e.detail.elt.closest('[data-confirm-opener]');
    const slot = opener && document.querySelector(opener.getAttribute('hx-target'));
    if (slot) openers.set(slot, opener);
  });

  // Dialogs. Their opener may be swapped out meanwhile (a new Member's row), so it's found again by what it requests.
  let dialogOpener = null;
  const requestOf = el => el && (el.getAttribute('hx-get') || el.getAttribute('hx-post'));
  document.addEventListener('htmx:beforeRequest', e => {
    const { elt, target } = e.detail;
    if (target?.id === 'dialog-slot' && !target.contains(elt)) dialogOpener = requestOf(elt);
  });
  const showModal = dialog => {
    // A response with an out-of-band swap reaches here twice.
    if (dialog.matches(':modal')) return;
    // Open without JS: reopened modal, without the `close` that would remove it.
    dialog.removeAttribute('open');
    dialog.showModal();
    (dialog.querySelector('[data-focus]') || dialog.querySelector('input, button'))?.focus();
  };
  document.addEventListener('htmx:afterSwap', e => {
    const dialog = e.detail.target?.id === 'dialog-slot' && e.detail.target.querySelector('dialog[data-modal]');
    if (dialog) showModal(dialog);
  });
  document.querySelectorAll('dialog[data-modal][open]').forEach(showModal);
  // `close` doesn't bubble.
  document.addEventListener('close', e => {
    const dialog = e.target;
    if (!(dialog instanceof HTMLDialogElement) || !dialog.matches('[data-modal]')) return;
    // A dialog replaced by the next one (Create and get the link) is closed by being removed: nothing to restore.
    if (!dialog.isConnected) return;
    dialog.remove();
    const opener = dialogOpener && [...document.querySelectorAll('[hx-get], [hx-post]')].find(el => requestOf(el) === dialogOpener);
    const control = opener?.matches('form') ? opener.querySelector('button') : opener;
    (control || heading())?.focus();
    dialogOpener = null;
  }, true);

  document.addEventListener('click', e => {
    const keep = e.target.closest('[data-keep]');
    if (keep) {
      const slot = keep.closest('[data-confirm-slot]');
      if (!slot) return;
      e.preventDefault();
      const opener = openers.get(slot);
      slot.replaceChildren();
      (opener?.isConnected ? opener : heading())?.focus();
      return;
    }
    const close = e.target.closest('[data-close-dialog]');
    if (close) {
      e.preventDefault();
      close.closest('dialog')?.close();
      return;
    }
    const disclose = e.target.closest('[data-disclose]');
    if (disclose) {
      const open = disclose.getAttribute('aria-expanded') !== 'true';
      disclose.setAttribute('aria-expanded', open);
      document.getElementById(disclose.getAttribute('aria-controls'))?.classList.toggle('open', open);
      return;
    }
    const copy = e.target.closest('[data-copy]');
    if (copy) copyLink(copy);
  });

  // The selection is copied as the click happens: over plain HTTP on the LAN there's no clipboard API.
  const copyLink = button => {
    const field = document.getElementById(button.dataset.copy);
    field.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (error) { /* the clipboard API below */ }
    if (!copied) navigator.clipboard?.writeText(field.value).catch(() => {});
    button.querySelector('use')?.setAttribute('href', '#i-tick');
    button.querySelector('span').textContent = button.dataset.copied;
    say(button.dataset.copied);
    button.focus();
  };

  // The auto-accept threshold.
  const form = document.querySelector('form.thr');
  if (!form) return;
  const range = form.querySelector('[data-range]');
  const number = form.querySelector('[data-number]');
  const save = form.querySelector('[data-save]');
  const keep = form.querySelector('[data-keep-threshold]');
  const line = document.querySelector('[data-line]');
  const lineLabel = document.querySelector('[data-line-label]');
  const bars = [...document.querySelectorAll('[data-hist] .hbar')];
  const current = Number(form.dataset.threshold);
  const clearing = JSON.parse(form.dataset.clearing);
  const fill = (text, values) => text.replace(/%\((\w+)\)s/g, (_, key) => values[key]).replace('%%', '%');

  const show = value => {
    const valid = Number.isInteger(value) && value >= 50 && value <= 100 && value % 5 === 0;
    if (valid) {
      range.value = value;
      range.setAttribute('aria-valuetext', fill(form.dataset.said, { percent: value }));
      line.style.setProperty('--at', `${value}%`);
      lineLabel.textContent = `${value} %`;
      bars.forEach(bar => bar.classList.toggle('over', Number(bar.dataset.start) >= value));
    }
    const changed = valid && value !== current;
    keep.hidden = !changed;
    save.disabled = !changed;
    // Lowering it lets queued suggestions through: saving offers them.
    const through = changed && value < current ? clearing[value] - clearing[current] : 0;
    save.textContent = through > 0
      ? fill(form.dataset.reviewLabel, { count: through })
      : fill(form.dataset.saveLabel, { percent: valid ? value : current });
  };
  range.addEventListener('input', () => { number.value = range.value; show(Number(range.value)); });
  number.addEventListener('input', () => show(Number(number.value)));
  keep.addEventListener('click', () => {
    number.value = current;
    show(current);
    number.focus();
  });
  // A value the server refused stays to be corrected; otherwise Save waits for a change.
  if (number.getAttribute('aria-invalid') !== 'true') show(Number(number.value));
})();
