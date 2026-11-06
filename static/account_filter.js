// The Dashboard's Account filter closes like the other dropdowns (DESIGN.md › Page header): on a press or focus outside
// it, or on Escape, which gives focus back to its trigger. Only Apply applies it, so however it closes, every box goes
// back to the filter the view shows (the boxes the server rendered checked) and the trigger's label stays true.
// The filter bar is swapped with each view, so every handler is on the document.
(() => {
  const FILTER = '.filter-bar details.accounts';
  const openFilter = () => document.querySelector(`${FILTER}[open]`);
  const discard = filter => filter.querySelectorAll('input[name="account"]').forEach(box => { box.checked = box.defaultChecked; });
  const close = filter => { filter.open = false; discard(filter); };

  // On the press rather than the click, and captured: a tap on the page's background sends no click on iOS, and a
  // collapsing Category stops its click's propagation (dashboard.js).
  document.addEventListener('pointerdown', e => {
    const filter = openFilter();
    if (filter && !filter.contains(e.target)) close(filter);
  }, true);
  document.addEventListener('focusout', e => {
    const filter = e.target.closest?.(`${FILTER}[open]`);
    // Focus going nowhere, or to an ancestor such as `main`, is a press on something unfocusable (a label, the page),
    // which the press handles: closing on the press would hide a label mid-click.
    const next = e.relatedTarget;
    if (filter && next && !filter.contains(next) && !next.contains(filter)) close(filter);
  });
  // Closing from its own trigger. On its click, since the `toggle` events of a quick close and reopen merge into one.
  document.addEventListener('click', e => {
    const filter = e.target.closest(`${FILTER}[open] > summary`)?.parentElement;
    if (filter) discard(filter);
  });
  document.addEventListener('keydown', e => {
    const filter = openFilter();
    if (e.key !== 'Escape' || !filter) return;
    close(filter);
    filter.querySelector('summary').focus();
  });
  // A Member change submits the filter form, so unapplied boxes are discarded first: captured, before HTMX's own
  // listener on the form, whatever way the select was reached.
  document.addEventListener('change', e => {
    const filter = e.target.matches('.filter-bar select[name="member"]') && openFilter();
    if (filter) close(filter);
  }, true);
})();
