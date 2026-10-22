// Import (docs/design/import.md). Statements dropped anywhere on the page, or chosen, are staged in the drop strip and
// posted at once by HTMX, which swaps the #import region in; swap.js then focuses and announces the result. Here:
// - staging: the chosen files listed with their size and a remove button, kept in the form's file input;
// - progress: the upload's share, then "Checking and importing", as the view checks every file before importing;
// - a Gap's slot names the Statement it needs above the strip and sends focus to Choose files;
// - the board's disclosures (a row's Statements, an import's counts), which show open without JS.
(() => {
  let staged = [];
  const form = () => document.querySelector('[data-import]');
  const input = () => form()?.querySelector('input[type="file"]');
  const say = message => document.dispatchEvent(new CustomEvent('announce', { detail: { value: message } }));
  // The form's strings, one or many of something: "%(count)s" is the number.
  const counted = (key, n) => {
    const strings = form().dataset;
    return (n === 1 ? strings[`${key}One`] : strings[`${key}Many`]).replace('%(count)s', n);
  };
  const lang = document.documentElement.lang || undefined;
  const size = bytes => bytes < 1e6
    ? new Intl.NumberFormat(lang, { style: 'unit', unit: 'kilobyte', maximumFractionDigits: 0 }).format(Math.max(1, bytes / 1e3))
    : new Intl.NumberFormat(lang, { style: 'unit', unit: 'megabyte', maximumFractionDigits: 1 }).format(bytes / 1e6);
  const svg = name => `<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;

  const render = () => {
    const f = form();
    if (!f) return;
    const box = new DataTransfer();
    staged.forEach(file => box.items.add(file));
    input().files = box.files;
    f.classList.toggle('staging', staged.length > 0);
    f.querySelector('[data-staging]').hidden = !staged.length;
    const list = f.querySelector('[data-staged]');
    list.replaceChildren(...staged.map((file, i) => {
      const row = document.createElement('li');
      row.innerHTML = `${svg('file')}<span class="file-name"></span><span class="size"></span><span class="state"></span>`
        + `<button type="button" class="ghost icon-button" data-unstage="${i}">${svg('x')}</button>`;
      row.querySelector('.file-name').textContent = file.name;
      row.querySelector('.size').textContent = size(file.size);
      row.querySelector('.state').textContent = f.dataset.ready;
      row.querySelector('button').setAttribute('aria-label', f.dataset.remove.replace('%(name)s', file.name));
      return row;
    }));
    f.querySelector('[data-submit]').textContent = counted('import', staged.length);
  };

  const stage = files => {
    const key = file => `${file.size}/${file.name}`;
    const keys = new Set(staged.map(key));
    staged.push(...[...files].filter(file => !keys.has(key(file))));
    render();
  };

  // The request's stages: uploading, with its share, then checking and importing, each file with a spinner.
  const progress = (step, percent = 0) => {
    const f = form();
    const n = staged.length;
    const line = f.querySelector('[data-progress]');
    const bar = f.querySelector('[data-bar]');
    line.hidden = false;
    f.querySelector('[data-staged-foot]').hidden = true;
    f.querySelectorAll('[data-unstage]').forEach(button => { button.hidden = true; });
    const checking = step === 'checking';
    f.querySelector('[data-progress-label]').textContent = counted(checking ? 'checking' : 'uploading', n);
    f.querySelector('[data-progress-detail]').hidden = !checking;
    f.querySelector('[data-progress-percent]').textContent = checking ? '' : `${percent} %`;
    bar.classList.toggle('indeterminate', checking);
    if (checking) {
      bar.removeAttribute('aria-valuenow');
      f.querySelectorAll('.staged .state').forEach(state => { state.innerHTML = '<span class="spinner" aria-hidden="true"></span>'; });
    } else {
      bar.setAttribute('aria-valuenow', percent);
      bar.style.setProperty('--done', `${percent}%`);
    }
  };

  const resetProgress = () => {
    const f = form();
    if (!f) return;
    f.querySelector('[data-progress]').hidden = true;
    f.querySelector('[data-staged-foot]').hidden = false;
    render();
  };

  document.addEventListener('click', e => {
    const target = e.target.closest('button');
    if (!target) return;
    if (target.matches('[data-choose-files]')) input()?.click();
    else if (target.matches('[data-unstage]')) {
      staged.splice(Number(target.dataset.unstage), 1);
      render();
      (form().querySelector('[data-unstage]') || document.querySelector('[data-choose-files]')).focus();
    } else if (target.matches('[data-cancel]')) {
      staged = [];
      render();
      document.querySelector('[data-choose-files]').focus();
    } else if (target.matches('.stretch.gap')) {
      const notice = document.querySelector('[data-gap-notice]');
      notice.querySelector('span').textContent = target.dataset.notice;
      notice.hidden = false;
      document.querySelector('[data-choose-files]').focus();
    } else if (target.matches('[data-gap-dismiss]')) {
      target.closest('[data-gap-notice]').hidden = true;
      document.querySelector('[data-choose-files]').focus();
    } else if (target.matches('[data-disclose]')) {
      const open = target.getAttribute('aria-expanded') !== 'true';
      target.setAttribute('aria-expanded', open);
      document.getElementById(target.getAttribute('aria-controls'))?.classList.toggle('open', open);
    }
  });

  document.addEventListener('change', e => {
    if (e.target === input() && e.target.files.length) stage(e.target.files);
  });

  // The whole page is the drop target.
  const carriesFiles = e => [...(e.dataTransfer?.types || [])].includes('Files');
  let depth = 0;
  document.addEventListener('dragenter', e => {
    if (!form() || !carriesFiles(e)) return;
    depth += 1;
    document.documentElement.classList.add('dragging');
  });
  document.addEventListener('dragleave', e => {
    if (!form() || !carriesFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (!depth) document.documentElement.classList.remove('dragging');
  });
  document.addEventListener('dragover', e => {
    if (form() && carriesFiles(e)) e.preventDefault();
  });
  document.addEventListener('drop', e => {
    if (!form() || !carriesFiles(e)) return;
    e.preventDefault();
    depth = 0;
    document.documentElement.classList.remove('dragging');
    stage(e.dataTransfer.files);
    form().querySelector('[data-submit]').focus();
  });

  // Only the upload form's own request; the Choose-the-Account forms post without staging. The form it was sent
  // from is gone once the result is swapped in.
  let sending = null;
  let uploaded = false;
  document.addEventListener('htmx:beforeRequest', e => {
    if (e.detail.elt !== form() || !staged.length) return;
    sending = e.detail.elt;
    uploaded = false;
    progress('uploading');
    say(counted('uploading', staged.length));
  });
  // HTMX reports the response's download as progress too; once the upload is done, that is ignored.
  document.addEventListener('htmx:xhr:progress', e => {
    if (e.detail.elt !== sending || uploaded || !e.detail.lengthComputable) return;
    const percent = Math.round((e.detail.loaded / e.detail.total) * 100);
    if (percent < 100) {
      progress('uploading', percent);
      return;
    }
    uploaded = true;
    progress('checking');
    say(sending.dataset.uploaded);
  });
  // A swapped-in result starts a new strip; a failed request leaves the files staged (swap.js says what happened).
  document.addEventListener('htmx:afterRequest', e => {
    if (e.detail.elt !== sending) return;
    sending = null;
    if (e.detail.successful) staged = [];
    else resetProgress();
  });
})();
