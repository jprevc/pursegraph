// The swap convention (docs/design/swap-feedback.md and loading.md), kept here for every HTMX swap so that templates
// don't patch it per page. Swaps are instant. By the kind of swap:
// - a page change (into `main`) focuses the new <h1> and scrolls to the top;
// - something that opens (a target marked `data-opens`) focuses its heading or first control and scrolls into view,
//   and when it empties again focus goes back to the control that opened it;
// - anything else is in place: focus stays on the control used, or goes to the region's heading if it's gone.
// The server names the new state through `HX-Trigger: {"announce": "…"}` (pursegraph.htmx.announce), read out by the
// shell's one polite live region. Loading dims the old content after 300 ms; an action (`data-action`) dims nothing
// but its button. A failed swap keeps the old content with a quiet "Couldn't load." line and a Try again button.
(() => {
  const live = document.getElementById('announcer');
  if (!live || !window.htmx) return;
  const strings = live.dataset;
  const BUSY_AFTER = 300;
  const FOCUSABLE = 'a[href], button:not(:disabled), input:not(:disabled, [type="hidden"]), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

  htmx.config.defaultSettleDelay = 0;

  // Cleared first, so that the same message twice is still read out.
  const say = message => {
    live.textContent = '';
    setTimeout(() => { live.textContent = message; }, 100);
  };
  document.addEventListener('announce', e => say(e.detail.value));

  const focus = el => {
    if (!el) return;
    if (!el.matches(FOCUSABLE) && !el.hasAttribute('tabindex')) el.tabIndex = -1;
    el.focus({ preventScroll: true });
  };
  const heading = region => region.querySelector('h1, h2, h3');
  const pageHeading = () => document.querySelector('main h1');
  const toTop = () => window.scrollTo({ top: 0, behavior: 'instant' });
  // The control used, found again in content swapped in without its id: the same kind, named the same.
  const nameOf = el => el.getAttribute('name') || el.getAttribute('aria-label') || el.textContent.trim();
  const twin = (old, region) => [...region.querySelectorAll(old.tagName)].find(el => nameOf(el) === nameOf(old));

  // Each request's swap, from its start to its settle.
  const swaps = new WeakMap();
  const regionOf = detail => detail.target || detail.elt;
  const isPage = region => region.matches('main');
  const opener = new WeakMap();

  const settle = (s, region) => {
    if (isPage(region)) {
      focus(pageHeading() || region);
      toTop();
    } else if (region.matches('[data-opens]')) {
      if (region.children.length) {
        if (s.focused !== document.body && !region.contains(s.focused)) opener.set(region, s.focused);
        focus(heading(region) || region.querySelector(FOCUSABLE));
        region.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      } else if (opener.get(region)?.isConnected) {
        focus(opener.get(region));
      }
    } else if (s.focused !== document.body && document.activeElement === document.body) {
      // The control used went with the old content (HTMX keeps it when the new content has it by id).
      focus(twin(s.focused, region) || heading(region) || pageHeading());
    }
    if (s.elt.closest('[data-scroll-top]')) region.scrollIntoView({ block: 'start', behavior: 'instant' });
  };

  // Busy: aria-busy at once; after 300 ms the dim and the line, or for an action its button's busy label.
  const start = e => {
    const { elt, xhr } = e.detail;
    const region = regionOf(e.detail);
    const action = elt.closest('[data-action]');
    const submitter = e.detail.requestConfig?.triggeringEvent?.submitter;
    const button = action && (submitter || (elt.matches('button') ? elt : null));
    const s = { elt, xhr, region, action, button, focused: document.activeElement };
    swaps.set(xhr, s);
    if (button) {
      s.label = button.textContent;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      s.timer = setTimeout(() => { button.textContent = button.dataset.busyLabel || strings.saving; }, BUSY_AFTER);
    } else if (action) {
      action.setAttribute('aria-busy', 'true');
    } else {
      region.setAttribute('aria-busy', 'true');
      region.busy = xhr;
      s.timer = setTimeout(() => { if (region.busy === xhr) region.classList.add('busy'); }, BUSY_AFTER);
    }
  };

  const stop = s => {
    clearTimeout(s.timer);
    s.action?.removeAttribute('aria-busy');
    if (s.button?.isConnected) {
      s.button.disabled = false;
      s.button.removeAttribute('aria-busy');
      s.button.textContent = s.label;
    }
    if (s.region.busy === s.xhr) {
      s.region.removeAttribute('aria-busy');
      s.region.classList.remove('busy');
      delete s.region.busy;
    }
  };

  // A failed swap keeps what is shown, and the controls go back to it; a lost session goes to log in.
  const fail = e => {
    const s = swaps.get(e.detail.xhr);
    if (!s) return;
    const status = e.detail.xhr.status;
    if (status === 401 || status === 403) {
      location.assign(`${strings.login}?next=${encodeURIComponent(location.pathname + location.search)}`);
      return;
    }
    s.elt.closest('form')?.reset();
    const path = e.detail.pathInfo?.finalRequestPath;
    if (s.action || !path || !s.region.id || e.detail.requestConfig?.verb !== 'get') {
      say(s.action ? strings.saveFailed : strings.loadFailed);
      return;
    }
    s.region.querySelector(':scope > .swap-failed')?.remove();
    const line = document.createElement('p');
    line.className = 'swap-failed';
    line.append(strings.loadFailed, ' ');
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'link';
    retry.textContent = strings.retry;
    retry.setAttribute('hx-get', path);
    retry.setAttribute('hx-target', `#${s.region.id}`);
    for (const attr of ['hx-swap', 'hx-push-url', 'hx-select']) {
      const value = s.elt.closest(`[${attr}]`)?.getAttribute(attr);
      if (value) retry.setAttribute(attr, value);
    }
    line.append(retry);
    s.region.prepend(line);
    htmx.process(retry);
    say(strings.loadFailed);
  };

  document.addEventListener('htmx:beforeRequest', start);
  document.addEventListener('htmx:afterRequest', e => {
    const s = swaps.get(e.detail.xhr);
    if (s) stop(s);
  });
  document.addEventListener('htmx:responseError', fail);
  document.addEventListener('htmx:sendError', fail);
  // Settling fires once for each element swapped in, out-of-band ones too; the convention runs once, for the region.
  document.addEventListener('htmx:afterSettle', e => {
    const s = swaps.get(e.detail.xhr);
    if (!s || s.settled) return;
    s.settled = true;
    // A region swapped outerHTML is found again by its id.
    const region = s.region.isConnected ? s.region : (s.region.id && document.getElementById(s.region.id)) || e.detail.elt;
    settle(s, region);
  });
  document.addEventListener('htmx:historyRestore', () => focus(pageHeading()));
})();
