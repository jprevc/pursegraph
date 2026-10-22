// The Review queue's decide box (docs/design/review-queue.md). Every control swaps the queue's region whole and the
// server says where focus goes (swap.js), so this only does what stays on the page:
// - a Category chip shows its Subcategories in place of the chips, and "‹ All Categories" goes back to them;
// - a failed save or Undo keeps the box as it was and says so inside it, naming the outcome, with Try again.
(() => {
  const boxOf = el => el.closest('.decide');

  document.addEventListener('click', e => {
    const chip = e.target.closest('.decide [data-category]');
    if (!chip) return;
    const pick = chip.closest('.pick');
    const key = chip.dataset.category;
    for (const step of pick.querySelectorAll('.pick-step')) step.classList.toggle('shown', step.dataset.step === key);
    pick.classList.toggle('stepped', key !== '');
    if (key) {
      pick.dataset.category = key;
      pick.querySelector(`.pick-step[data-step="${key}"] button[type="submit"]`)?.focus();
    } else {
      pick.querySelector(`.pick-step[data-step=""] [data-category="${pick.dataset.category}"]`)?.focus();
    }
  });

  // A new try takes the last failure's line away.
  document.addEventListener('htmx:beforeRequest', e => {
    const box = e.detail.elt.closest?.('.decide');
    box?.querySelector('.oc-failed')?.remove();
  });

  const fail = e => {
    const form = e.detail.elt.closest?.('.decide-form, form.undo');
    const status = e.detail.xhr?.status;
    // A lost session goes to log in (swap.js).
    if (!form || status === 401 || status === 403) return;
    const submitter = e.detail.requestConfig?.triggeringEvent?.submitter;
    const line = document.createElement('p');
    line.className = 'oc-failed';
    line.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-alert"/></svg>';
    const words = document.createElement('span');
    line.append(words);
    if (form.matches('.decide-form') && submitter) {
      words.textContent = form.dataset.failed.replace('%(outcome)s', submitter.dataset.label);
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'link';
      again.textContent = form.dataset.retry;
      // Focus goes back to the outcome first, so that swap.js gives it back if this try fails too.
      again.addEventListener('click', () => {
        submitter.focus();
        form.requestSubmit(submitter);
      });
      line.append(again);
    } else {
      words.textContent = form.dataset.failed;
    }
    boxOf(form).append(line);
    document.dispatchEvent(new CustomEvent('announce', { detail: { value: words.textContent } }));
  };
  document.addEventListener('htmx:responseError', fail);
  document.addEventListener('htmx:sendError', fail);
})();
