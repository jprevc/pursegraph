// Mounts the dashboard's ECharts charts: on page load, and whenever HTMX swaps a view in.
// Each chart reads its data from the JSON script named by `data-source`; clicking a mark loads its Transactions into #drill.
(() => {
  const INK2 = '#52514e', MUTED = '#898781', GRID = '#e1e0d9', AXIS = '#c3c2b7';
  const PALETTE = ['#2a78d6', '#1baf7a', '#eb6834', '#8a5cd0', '#d4a72c', '#d0457a', '#2fa3b5', '#7a8a2e', '#a0643c'];
  const AWAITING = 'awaiting';
  const eur = (v, digits = 0) => v.toLocaleString(undefined, { style: 'currency', currency: 'EUR', minimumFractionDigits: digits, maximumFractionDigits: digits });

  const options = {
    spending: data => ({
      textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: INK2 },
      tooltip: { trigger: 'item', confine: true, valueFormatter: v => eur(v, 2) },
      grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: 'value', splitNumber: 3, axisLabel: { color: MUTED, formatter: v => eur(v) }, splitLine: { lineStyle: { color: GRID } } },
      yAxis: { type: 'category', inverse: true, data: data.bars.map(b => b.name), axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false }, axisLabel: { color: INK2 } },
      series: [{
        type: 'bar', barMaxWidth: 18, cursor: 'pointer',
        data: data.bars.map((b, i) => ({
          value: b.value, key: b.key,
          itemStyle: { color: b.key === AWAITING ? MUTED : PALETTE[i % PALETTE.length], borderRadius: [0, 4, 4, 0] },
        })),
        label: { show: true, position: 'right', color: INK2, formatter: p => eur(p.value) },
      }],
    }),
  };

  const observers = new WeakMap();

  const mount = el => {
    // A page restored from history has the element but not its chart.
    if (echarts.getInstanceByDom(el)) return;
    const data = JSON.parse(document.getElementById(el.dataset.source).textContent);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(options[el.dataset.chart](data));
    chart.on('click', p => htmx.ajax('GET', data.drill + encodeURIComponent(p.data.key), '#drill'));
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    observers.set(el, observer);
  };
  const unmount = el => {
    observers.get(el)?.disconnect();
    echarts.getInstanceByDom(el)?.dispose();
  };
  const charts = root => root.querySelectorAll('[data-chart]');

  document.addEventListener('DOMContentLoaded', () => charts(document).forEach(mount));
  document.addEventListener('htmx:beforeSwap', e => charts(e.detail.target).forEach(unmount));
  document.addEventListener('htmx:afterSettle', e => charts(e.detail.elt).forEach(mount));
  document.addEventListener('htmx:historyRestore', () => charts(document).forEach(mount));

  // An outcome changed in the drill-down moves money between the bars: refetch the numbers, keeping the drill-down open.
  document.addEventListener('htmx:afterRequest', e => {
    // The row is swapped out by now, so the request's path says what it was rather than its (detached) form.
    const outcome = /^\/transactions\/\d+\/outcome\/$/.test(e.detail.requestConfig.path);
    if (e.detail.successful && outcome && document.getElementById('numbers')) {
      htmx.ajax('GET', location.href, { target: '#numbers', select: '#numbers', swap: 'outerHTML' });
    }
  });
})();
