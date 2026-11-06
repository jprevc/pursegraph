// The Transactions page's facet rail (docs/design/transactions-page.md). Every pick swaps the rail's content out of
// band; HTMX keeps focus on the control used, found again by its id. What it can't keep is kept here:
// - what is being typed into an amount field, which a swap answering an earlier keystroke would overwrite;
// - whether Decided by's notes are shown, which its info toggle sets;
// - on a phone, focus on the Filter sheet's heading as it opens (it closes back to the Filter button by itself).
(() => {
  const showNotes = (toggle, open) => {
    toggle.setAttribute('aria-expanded', open);
    toggle.closest('.facet')?.classList.toggle('notes-open', open);
  };
  document.addEventListener('click', e => {
    const toggle = e.target.closest('[data-notes]');
    if (toggle) showNotes(toggle, toggle.getAttribute('aria-expanded') !== 'true');
  });
  document.addEventListener('htmx:oobBeforeSwap', e => {
    const fragment = e.detail.fragment;
    document.querySelectorAll('[data-notes][aria-expanded="true"]').forEach(toggle => {
      const twin = fragment?.querySelector?.(`[data-notes][aria-controls="${toggle.getAttribute('aria-controls')}"]`);
      if (twin) showNotes(twin, true);
    });
    const typing = document.activeElement;
    if (!typing?.matches('.between input')) return;
    const twin = fragment?.querySelector?.(`#${typing.id}`);
    if (twin) twin.value = typing.value;
  });
  document.addEventListener('toggle', e => {
    if (e.target.id !== 'rail' || e.newState !== 'open') return;
    const heading = e.target.querySelector('#rail-h');
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }, true);
})();
