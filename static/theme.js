// The theme switch: Light, System or Dark, remembered per browser. base.html's inline script applies the saved
// choice before first paint; this keeps every switch on the page in step, applies a new choice and rewrites the
// theme-color metas, and dispatches `themechange` on document whenever the colours change, so charts can rebuild.
(() => {
  const THEMES = ['light', 'system', 'dark'];
  const root = document.documentElement;
  const dark = matchMedia('(prefers-color-scheme: dark)');
  // Each meta's ground colour for its own scheme, which System restores.
  const metas = [...document.querySelectorAll('meta[name="theme-color"]')].map(meta => [meta, meta.content]);

  const current = () => THEMES.includes(root.dataset.theme) ? root.dataset.theme : 'system';
  const radios = () => document.querySelectorAll('.theme-switch input[type="radio"]');

  const sync = () => {
    const theme = current();
    radios().forEach(radio => { radio.checked = radio.value === theme; });
    document.querySelectorAll('.theme-switch[hidden]').forEach(s => { s.hidden = false; });
  };

  // Under Light or Dark, every meta takes that theme's ground, whatever the system's scheme.
  const paintMetas = () => {
    const theme = current();
    const ground = getComputedStyle(root).getPropertyValue('--ground').trim();
    metas.forEach(([meta, own]) => { meta.content = theme === 'system' ? own : ground; });
  };

  const apply = theme => {
    root.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch (e) { /* not remembered, but still applied */ }
    paintMetas();
    sync();
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
  };

  document.addEventListener('change', e => {
    if (e.target.matches('.theme-switch input[type="radio"]') && THEMES.includes(e.target.value)) apply(e.target.value);
  });
  dark.addEventListener('change', () => {
    if (current() === 'system') document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: 'system' } }));
  });

  paintMetas();
  sync();
  // A swap can bring a fresh switch (the navigation comes along out of band), and history restores an old one.
  document.addEventListener('htmx:afterSettle', sync);
  document.addEventListener('htmx:historyRestore', sync);
})();
