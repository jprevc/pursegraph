// Mounts the dashboard's ECharts charts: on page load, and whenever HTMX swaps a view in.
// Each chart reads its data from the JSON script named by `data-source`; clicking a mark loads its Transactions into #drill.
// Colours come from the CSS tokens, so a chart is rebuilt on `themechange` (static/theme.js).
(() => {
  const AWAITING = 'awaiting';
  const { money, moneyWhole, moneySigned } = window.Figures;
  const token = name => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

  // The options' building blocks in the current theme's colours.
  const theme = () => {
    const INK = token('ink'), INK2 = token('ink-2'), MUTED = token('muted'), LINE = token('line'), LINE_STRONG = token('line-strong');
    // A Category keeps its hue in every view: cat-((id − 1) mod 10). Awaiting review is always its neutral grey.
    const colour = key => key === AWAITING ? token('awaiting') : token(`cat-${(Number(key) - 1) % 10}`);
    return {
      INK, INK2, MUTED, LINE, LINE_STRONG, CARD: token('card'), colour,
      TEXT: { fontFamily: token('font'), color: INK2 },
      tooltip: { backgroundColor: token('card'), borderColor: LINE, borderRadius: 10, extraCssText: `box-shadow: ${token('shadow-pop')}`, textStyle: { color: INK } },
      valueAxis: { type: 'value', axisLabel: { color: MUTED, formatter: v => moneyWhole(v) }, splitLine: { lineStyle: { color: LINE } } },
      categoryAxis: (data, extra = {}) => ({ type: 'category', data, axisLine: { lineStyle: { color: LINE_STRONG } }, axisTick: { show: false }, axisLabel: { color: MUTED }, ...extra }),
      legend: { top: 0, left: 0, type: 'scroll', textStyle: { color: INK2 }, icon: 'circle', itemWidth: 8, itemHeight: 8, inactiveColor: LINE_STRONG },
    };
  };

  const options = {
    spending: (data, { TEXT, tooltip, MUTED, LINE, LINE_STRONG, INK2, colour }) => ({
      textStyle: TEXT,
      tooltip: { ...tooltip, trigger: 'item', confine: true, valueFormatter: money },
      grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
      xAxis: { type: 'value', splitNumber: 3, axisLabel: { color: MUTED, formatter: v => moneyWhole(v) }, splitLine: { lineStyle: { color: LINE } } },
      yAxis: { type: 'category', inverse: true, data: data.bars.map(b => b.name), axisLine: { lineStyle: { color: LINE_STRONG } }, axisTick: { show: false }, axisLabel: { color: INK2 } },
      series: [{
        type: 'bar', barMaxWidth: 18, cursor: 'pointer',
        data: data.bars.map(b => ({
          value: b.value, key: b.key,
          itemStyle: { color: colour(b.key), borderRadius: [0, 4, 4, 0] },
        })),
        label: { show: true, position: 'right', color: INK2, formatter: p => moneyWhole(p.value) },
      }],
    }),

    cashflow: (data, { TEXT, tooltip, legend, valueAxis, categoryAxis, INK, INK2, MUTED, CARD, colour }) => {
      const IN = data.in_key ? colour(data.in_key) : INK2, OUT = MUTED, NET = INK, OTHERS = INK2;
      const marks = (values, side) => values.map((value, i) => ({ value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      return {
        textStyle: TEXT, legend,
        tooltip: { ...tooltip, trigger: 'axis', confine: true, valueFormatter: money },
        grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
        xAxis: categoryAxis(data.months), yAxis: valueAxis,
        series: [
          { name: data.labels.in, type: 'bar', cursor: 'pointer', data: marks(data.in, 'in'), itemStyle: { color: IN, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 22, barGap: '10%' },
          { name: data.labels.out, type: 'bar', cursor: 'pointer', data: marks(data.out, 'out'), itemStyle: { color: OUT, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 22 },
          { name: data.labels.net, type: 'line', cursor: 'pointer', data: marks(data.net), symbol: 'circle', symbolSize: 7, lineStyle: { width: 2, color: NET }, itemStyle: { color: NET, borderColor: CARD, borderWidth: 1.5 }, tooltip: { valueFormatter: moneySigned } },
          // Under a Member filter: what Transfers moved to (below zero) or from other Members.
          ...(data.others ? [{ name: data.labels.others, type: 'line', cursor: 'pointer', data: marks(data.others, 'others'), symbol: 'circle', symbolSize: 7, lineStyle: { width: 2, type: 'dashed', color: OTHERS }, itemStyle: { color: OTHERS, borderColor: CARD, borderWidth: 1.5 }, tooltip: { valueFormatter: moneySigned } }] : []),
        ],
      };
    },

    // Clicking a Category in the legend hides its line.
    trends: (data, { TEXT, tooltip, legend, valueAxis, categoryAxis, colour }) => ({
      textStyle: TEXT, legend,
      tooltip: { ...tooltip, trigger: 'axis', confine: true, order: 'valueDesc', valueFormatter: money },
      grid: { left: 8, right: 32, top: 36, bottom: 8, containLabel: true },
      xAxis: categoryAxis(data.months, { boundaryGap: false }), yAxis: valueAxis,
      series: data.lines.map(line => ({
        name: line.name, type: 'line', cursor: 'pointer', symbolSize: 8, emphasis: { focus: 'series' },
        data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
        lineStyle: { width: 2, color: colour(line.key) }, itemStyle: { color: colour(line.key) },
      })),
    }),

    per_member: (data, { TEXT, tooltip, legend, valueAxis, categoryAxis, INK, CARD, colour }) => ({
      textStyle: TEXT, legend,
      tooltip: { ...tooltip, trigger: 'item', confine: true, valueFormatter: money },
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      xAxis: { ...valueAxis, splitNumber: 3 },
      yAxis: categoryAxis(data.members, { inverse: true, axisLabel: { color: INK, fontWeight: 600 } }),
      series: data.segments.map(segment => ({
        name: segment.name, type: 'bar', stack: 'spent', barMaxWidth: 28, cursor: 'pointer', data: segment.data,
        itemStyle: { color: colour(segment.key), borderColor: CARD, borderWidth: 1.5 },
      })),
    }),

    // Node names are unique keys; what a node shows is its label.
    money_flow: (data, { TEXT, tooltip, INK2, MUTED, colour }) => {
      const labels = Object.fromEntries(data.nodes.map(n => [n.name, n.label]));
      return {
        textStyle: TEXT,
        tooltip: {
          ...tooltip, trigger: 'item', confine: true,
          formatter: p => p.dataType === 'edge'
            ? `${labels[p.data.source]} → ${labels[p.data.target]}: ${money(p.value)}`
            : `${p.data.label}: ${money(p.value)}`,
        },
        series: [{
          type: 'sankey', left: 8, right: 160, top: 8, bottom: 8, nodeGap: 10, nodeWidth: 12, draggable: false,
          emphasis: { focus: 'adjacency', lineStyle: { opacity: 0.6 } }, lineStyle: { color: 'gradient', opacity: 0.3 },
          label: { color: INK2, fontWeight: 500, formatter: p => `${p.data.label}  ${moneyWhole(p.value)}` },
          data: data.nodes.map(n => ({
            ...n, cursor: n.key ? 'pointer' : 'default',
            itemStyle: { color: ['saved', 'from_savings', 'others'].includes(n.name) ? MUTED : n.name === 'household' ? INK2 : n.key.startsWith('in:') ? colour(data.in_key) : colour(n.key) },
          })),
          links: data.links,
        }],
      };
    },
  };

  const observers = new WeakMap();

  const dataOf = el => JSON.parse(document.getElementById(el.dataset.source).textContent);
  // ECharts has no live theme switch, and a narrow chart lays out differently: rebuild the options from the tokens.
  const build = (chart, el) => chart.setOption(options[el.dataset.chart](dataOf(el), theme()), { notMerge: true });

  const mount = el => {
    // A page restored from history has the element but not its chart.
    if (echarts.getInstanceByDom(el)) return;
    const data = dataOf(el);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    build(chart, el);
    // Every mark that names Transactions carries its key: a bar, a point, a segment or a Sankey node.
    chart.on('click', p => {
      if (p.data?.key) htmx.ajax('GET', data.drill + encodeURIComponent(p.data.key), '#drill');
    });
    const observer = new ResizeObserver(() => { chart.resize(); build(chart, el); });
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
  // A view swapped in brings the sidebar's view links along, marking its own as current.
  document.addEventListener('htmx:afterSettle', e => charts(e.detail.elt).forEach(mount));
  document.addEventListener('htmx:historyRestore', () => charts(document).forEach(mount));
  const retheme = () => charts(document).forEach(el => {
    const chart = echarts.getInstanceByDom(el);
    if (chart) build(chart, el);
  });
  // Also sent when the system scheme changes under System.
  document.addEventListener('themechange', retheme);

  // An outcome changed in the drill-down moves money between the bars: refetch the numbers, keeping the drill-down open.
  document.addEventListener('htmx:afterRequest', e => {
    // The row is swapped out by now, so the request's path says what it was rather than its (detached) form.
    const outcome = /^\/transactions\/\d+\/outcome\/$/.test(e.detail.requestConfig.path);
    if (e.detail.successful && outcome && document.getElementById('numbers')) {
      htmx.ajax('GET', location.href, { target: '#numbers', select: '#numbers', swap: 'outerHTML' });
    }
  });
})();
