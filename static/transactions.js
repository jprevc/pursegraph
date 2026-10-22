// The Transactions page's facet rail (docs/design/transactions-page.md). Every pick swaps the rail's content out of
// band; HTMX keeps focus on the control used, found again by its id. Two things it can't keep are kept here:
// - what is being typed into an amount field, which a swap answering an earlier keystroke would overwrite;
// - on a phone, focus on the Filter sheet's heading as it opens (it closes back to the Filter button by itself).
(() => {
  document.addEventListener('htmx:oobBeforeSwap', e => {
    const typing = document.activeElement;
    if (!typing?.matches('.between input')) return;
    const twin = e.detail.fragment?.querySelector?.(`#${typing.id}`);
    if (twin) twin.value = typing.value;
  });
  document.addEventListener('toggle', e => {
    if (e.target.id !== 'rail' || e.newState !== 'open') return;
    const heading = e.target.querySelector('#rail-h');
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }, true);
})();
