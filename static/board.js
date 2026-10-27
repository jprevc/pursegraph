// The Accounts board (docs/design/import.md), on Import and on Accounts. HTMX swaps the board for an edit or a delete;
// here, what stays in the page:
// - the row's disclosures (its Statements, an import's counts), which show open without JS;
// - an inline confirmation's Keep it, which closes it and gives the focus back to the control that opened it.
(() => {
  const openers = new WeakMap();
  document.addEventListener('htmx:beforeRequest', e => {
    const opener = e.detail.elt.closest('[data-confirm-opener]');
    const slot = opener && document.querySelector(opener.getAttribute('hx-target'));
    if (slot) openers.set(slot, opener);
  });

  document.addEventListener('click', e => {
    const target = e.target.closest('button');
    if (!target) return;
    if (target.matches('[data-disclose]')) {
      const open = target.getAttribute('aria-expanded') !== 'true';
      target.setAttribute('aria-expanded', open);
      document.getElementById(target.getAttribute('aria-controls'))?.classList.toggle('open', open);
    } else if (target.matches('[data-keep]')) {
      const slot = target.closest('[data-confirm-slot]');
      const opener = openers.get(slot);
      slot.replaceChildren();
      opener?.focus();
    }
  });
})();
