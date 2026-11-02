// A Member's first steps card: Hide removes it in this browser, for this Member. base.html applies a saved Hide
// before first paint, so the card never flashes in on a later page or swap.
document.addEventListener('click', event => {
  const hide = event.target.closest('[data-hide-first-steps]');
  if (!hide) return;
  const card = hide.closest('.first-steps');
  try { localStorage.setItem(`first-steps-hidden:${card.dataset.member}`, '1'); } catch (e) {}
  document.documentElement.classList.add('first-steps-hidden');
  // The card is gone, so focus goes to the top of the page rather than to nothing.
  document.querySelector('main h1')?.focus();
});
