// The Dashboard's Account filter closes like the other dropdowns: on a click or focus outside it, or on Escape,
// which gives focus back to its trigger. Only Apply applies it, so however it closes, every box goes back to the
// filter the view shows (the boxes the server rendered checked) and the trigger's label stays true.
// The filter bar is swapped with each view, so every handler is on the document.
(() => {
  const open = () => document.querySelector('.filter-bar details.accounts[open]');
  const discard = filter => filter.querySelectorAll('input[name="account"]').forEach(box => { box.checked = box.defaultChecked; });
  // Discarding at once, rather than on `toggle`, which comes later: focus leaving for the Member select must not let
  // its change submit the unapplied boxes.
  const close = filter => { filter.open = false; discard(filter); };

  document.addEventListener('click', e => {
    const filter = open();
    if (filter && !filter.contains(e.target)) close(filter);
  });
  document.addEventListener('focusout', e => {
    const filter = e.target.closest?.('.filter-bar details.accounts[open]');
    // Focus going nowhere, or to an ancestor such as `main`, is a press on something unfocusable (a label, the page),
    // which the click handles: closing on the press would hide a label mid-click.
    const to = e.relatedTarget;
    if (filter && to && !filter.contains(to) && !to.contains(filter)) close(filter);
  });
  document.addEventListener('keydown', e => {
    const filter = open();
    if (e.key !== 'Escape' || !filter) return;
    close(filter);
    filter.querySelector('summary').focus();
  });
  // Closed from its own trigger.
  document.addEventListener('toggle', e => {
    if (e.target.matches?.('.filter-bar details.accounts') && !e.target.open) discard(e.target);
  }, true);
})();
