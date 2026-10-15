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

  const mount = el => {
    if (el.dataset.mounted) return;
    el.dataset.mounted = 'yes';
    const data = JSON.parse(document.getElementById(el.dataset.source).textContent);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(options[el.dataset.chart](data));
    chart.on('click', p => htmx.ajax('GET', `${data.drill}&category=${encodeURIComponent(p.data.key)}`, '#drill'));
    new ResizeObserver(() => chart.resize()).observe(el);
  };
  const mountAll = root => root.querySelectorAll('[data-chart]').forEach(mount);

  document.addEventListener('DOMContentLoaded', () => mountAll(document));
  document.addEventListener('htmx:afterSettle', e => mountAll(e.detail.elt));
})();
