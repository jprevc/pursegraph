// The sidebar's Manage group: opening or closing it is remembered in this browser, for this Member, and the sidebar
// restores it off Manage's own pages. Only a click on its summary is saved (a key press on it clicks too), not
// `toggle`, which also fires when a page opens the group itself.
document.addEventListener('click', event => {
  const summary = event.target.closest('details.manage > summary');
  if (!summary) return;
  const group = summary.parentElement;
  // The click toggles the group after this handler, so it is about to become the opposite of what it is.
  try { localStorage.setItem(`manage-open:${group.dataset.member}`, group.open ? '0' : '1'); } catch (e) {}
});
