// Mounts the dashboard's ECharts charts: on page load, and whenever HTMX swaps a view in.
// Each chart reads its data from the JSON script named by `data-source`; clicking a mark loads its Transactions into #drill.
(() => {
  const INK2 = '#52514e', MUTED = '#898781', GRID = '#e1e0d9', AXIS = '#c3c2b7';
  const PALETTE = ['#2a78d6', '#1baf7a', '#eb6834', '#8a5cd0', '#d4a72c', '#d0457a', '#2fa3b5', '#7a8a2e', '#a0643c'];
  const AWAITING = 'awaiting';
  const eur = (v, digits = 0) => v.toLocaleString(undefined, { style: 'currency', currency: 'EUR', minimumFractionDigits: digits, maximumFractionDigits: digits });

  const TEXT = { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: INK2 };
  const IN = '#1baf7a', OUT = '#eb6834', NET = '#0b0b0b';
  const valueAxis = { type: 'value', axisLabel: { color: MUTED, formatter: v => eur(v) }, splitLine: { lineStyle: { color: GRID } } };
  const categoryAxis = (data, extra = {}) => ({ type: 'category', data, axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false }, axisLabel: { color: MUTED }, ...extra });
  const legend = { top: 0, left: 0, type: 'scroll', textStyle: { color: INK2 }, icon: 'roundRect' };
  // A Category keeps its colour in every view, picked by its key (its id); Awaiting review is always grey.
  const colour = key => key === AWAITING ? MUTED : PALETTE[Number(key) % PALETTE.length];

  const options = {
    spending: data => ({
      textStyle: TEXT,
      tooltip: { trigger: 'item', confine: true, valueFormatter: v => eur(v, 2) },
      grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: 'value', splitNumber: 3, axisLabel: { color: MUTED, formatter: v => eur(v) }, splitLine: { lineStyle: { color: GRID } } },
      yAxis: { type: 'category', inverse: true, data: data.bars.map(b => b.name), axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false }, axisLabel: { color: INK2 } },
      series: [{
        type: 'bar', barMaxWidth: 18, cursor: 'pointer',
        data: data.bars.map(b => ({
          value: b.value, key: b.key,
          itemStyle: { color: colour(b.key), borderRadius: [0, 4, 4, 0] },
        })),
        label: { show: true, position: 'right', color: INK2, formatter: p => eur(p.value) },
      }],
    }),

    cashflow: data => {
      const marks = (values, side) => values.map((value, i) => ({ value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      return {
        textStyle: TEXT, legend,
        tooltip: { trigger: 'axis', confine: true, valueFormatter: v => eur(v, 2) },
        grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
        xAxis: categoryAxis(data.months), yAxis: valueAxis,
        series: [
          { name: data.labels.in, type: 'bar', cursor: 'pointer', data: marks(data.in, 'in'), itemStyle: { color: IN, borderRadius: [4, 4, 0, 0] }, barGap: '8%' },
          { name: data.labels.out, type: 'bar', cursor: 'pointer', data: marks(data.out, 'out'), itemStyle: { color: OUT, borderRadius: [4, 4, 0, 0] } },
          { name: data.labels.net, type: 'line', cursor: 'pointer', data: marks(data.net), symbolSize: 8, lineStyle: { width: 2, color: NET }, itemStyle: { color: NET } },
        ],
      };
    },

    // Clicking a Category in the legend hides its line.
    trends: data => ({
      textStyle: TEXT, legend,
      tooltip: { trigger: 'axis', confine: true, order: 'valueDesc', valueFormatter: v => eur(v, 2) },
      grid: { left: 8, right: 32, top: 36, bottom: 8, containLabel: true },
      xAxis: categoryAxis(data.months, { boundaryGap: false }), yAxis: valueAxis,
      series: data.lines.map(line => ({
        name: line.name, type: 'line', cursor: 'pointer', symbolSize: 8, emphasis: { focus: 'series' },
        data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
        lineStyle: { width: 2, color: colour(line.key) }, itemStyle: { color: colour(line.key) },
      })),
    }),

    per_member: data => ({
      textStyle: TEXT, legend,
      tooltip: { trigger: 'item', confine: true, valueFormatter: v => eur(v, 2) },
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      xAxis: { ...valueAxis, splitNumber: 3 },
      yAxis: categoryAxis(data.members, { inverse: true, axisLabel: { color: INK2, fontWeight: 600 } }),
      series: data.segments.map(segment => ({
        name: segment.name, type: 'bar', stack: 'spent', barMaxWidth: 28, cursor: 'pointer', data: segment.data,
        itemStyle: { color: colour(segment.key), borderColor: '#fcfcfb', borderWidth: 1 },
      })),
    }),

    // Node names are unique keys; what a node shows is its label.
    money_flow: data => {
      const labels = Object.fromEntries(data.nodes.map(n => [n.name, n.label]));
      return {
        textStyle: TEXT,
        tooltip: {
          trigger: 'item', confine: true,
          formatter: p => p.dataType === 'edge'
            ? `${labels[p.data.source]} → ${labels[p.data.target]}: ${eur(p.value, 2)}`
            : `${p.data.label}: ${eur(p.value, 2)}`,
        },
        series: [{
          type: 'sankey', left: 8, right: 160, top: 8, bottom: 8, nodeGap: 10, nodeWidth: 12, draggable: false,
          emphasis: { focus: 'adjacency' }, lineStyle: { color: 'gradient', opacity: 0.35 },
          label: { color: INK2, formatter: p => `${p.data.label}  ${eur(p.value)}` },
          data: data.nodes.map(n => ({
            ...n, cursor: n.key ? 'pointer' : 'default',
            itemStyle: { color: n.name === 'saved' ? IN : n.name === 'from_savings' ? OUT : n.name === 'household' ? INK2 : colour(n.key.replace(/^in:/, '')) },
          })),
          links: data.links,
        }],
      };
    },
  };

  const observers = new WeakMap();

  const mount = el => {
    // A page restored from history has the element but not its chart.
    if (echarts.getInstanceByDom(el)) return;
    const data = JSON.parse(document.getElementById(el.dataset.source).textContent);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption(options[el.dataset.chart](data));
    // Every mark that names Transactions carries its key: a bar, a point, a segment or a Sankey node.
    chart.on('click', p => {
      if (p.data?.key) htmx.ajax('GET', data.drill + encodeURIComponent(p.data.key), '#drill');
    });
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
  document.addEventListener('htmx:afterSettle', e => {
    charts(e.detail.elt).forEach(mount);
    // A view swapped in from the sidebar becomes its current item.
    if (e.detail.elt.id === 'view' && e.detail.requestConfig) {
      const path = new URL(e.detail.requestConfig.path, location.href).pathname;
      document.querySelectorAll('aside a.nav').forEach(a => a.classList.toggle('on', a.getAttribute('href') === path));
    }
  });
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
