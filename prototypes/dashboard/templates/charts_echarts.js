// PROTOTYPE: the five dashboard views rendered with Apache ECharts. Every chart drills down on click.
const INK2 = '#52514e', MUTED = '#898781', GRID = '#e1e0d9', AXIS = '#c3c2b7';
const base = {
  textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: INK2 },
  tooltip: { confine: true, valueFormatter: v => eur(v, 2) },
  grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
};
const valAxis = { type: 'value', axisLabel: { color: MUTED, formatter: v => eur(v) }, splitLine: { lineStyle: { color: GRID } } };
const catAxis = (data, extra = {}) => ({ type: 'category', data, axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false }, axisLabel: { color: MUTED }, ...extra });

function mount(el, option) {
  const c = echarts.init(el, null, { renderer: 'svg' });
  c.setOption({ ...base, ...option });
  new ResizeObserver(() => c.resize()).observe(el);
  return c;
}

const PG = {
  spending(el, d, { donut = false } = {}) {
    const cats = d.byCategory;
    const c = donut
      ? mount(el, {
          tooltip: { ...base.tooltip, trigger: 'item' },
          series: [{
            type: 'pie', radius: ['55%', '85%'], padAngle: 1, itemStyle: { borderRadius: 4 },
            label: { show: false },
            data: cats.map(x => ({ name: x.name, value: x.value, itemStyle: { color: x.color } })),
          }],
        })
      : mount(el, {
          tooltip: { ...base.tooltip, trigger: 'item',
            formatter: p => `<b>${p.name}</b> ${eur(p.value, 2)}<br>` +
              cats[p.dataIndex].subs.map(s => `<span style="color:${MUTED}">${s.name}</span> ${eur(s.value, 2)}`).join('<br>') },
          xAxis: { ...valAxis, splitNumber: 3 },
          yAxis: catAxis(cats.map(x => x.name), { inverse: true, axisLabel: { color: INK2 } }),
          series: [{
            type: 'bar', barMaxWidth: 18,
            data: cats.map(x => ({ value: x.value, itemStyle: { color: x.color, borderRadius: [0, 4, 4, 0] } })),
            label: { show: true, position: 'right', color: INK2, formatter: p => eur(p.value) },
          }],
        });
    c.on('click', p => drill({ category: p.name }));
    return c;
  },

  cashflow(el, d) {
    const cf = d.cashflow;
    const c = mount(el, {
      tooltip: { ...base.tooltip, trigger: 'axis' },
      legend: { top: 0, left: 0, textStyle: { color: INK2 }, icon: 'roundRect' },
      xAxis: catAxis(cf.months),
      yAxis: valAxis,
      series: [
        { name: 'Money in', type: 'bar', data: cf.in, itemStyle: { color: '#1baf7a', borderRadius: [4, 4, 0, 0] }, barGap: '8%' },
        { name: 'Money out', type: 'bar', data: cf.out, itemStyle: { color: '#eb6834', borderRadius: [4, 4, 0, 0] } },
        { name: 'Net', type: 'line', data: cf.net, symbolSize: 8, lineStyle: { width: 2, color: '#0b0b0b' }, itemStyle: { color: '#0b0b0b' } },
      ],
    });
    c.on('click', p => drill({ month: cf.keys[p.dataIndex], kind: { 'Money in': 'in', 'Money out': 'out' }[p.seriesName] || '' }));
    return c;
  },

  trends(el, d) {
    const t = d.trends;
    const c = mount(el, {
      tooltip: { ...base.tooltip, trigger: 'axis', order: 'valueDesc' },
      legend: { top: 0, left: 0, type: 'scroll', textStyle: { color: INK2 }, icon: 'roundRect' },
      grid: { ...base.grid, top: 36 },
      xAxis: catAxis(t.months, { boundaryGap: false }),
      yAxis: valAxis,
      series: t.series.map(s => ({ name: s.name, type: 'line', data: s.data, symbolSize: 8, showSymbol: false,
        lineStyle: { width: 2, color: s.color }, itemStyle: { color: s.color }, emphasis: { focus: 'series' } })),
    });
    c.on('click', p => drill({ month: t.keys[p.dataIndex], category: p.seriesName }));
    return c;
  },

  members(el, d) {
    const m = d.members;
    const c = mount(el, {
      tooltip: { ...base.tooltip, trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { top: 0, left: 0, type: 'scroll', textStyle: { color: INK2 }, icon: 'roundRect' },
      grid: { ...base.grid, top: 36 },
      xAxis: { ...valAxis, splitNumber: 3 },
      yAxis: catAxis(m.names, { inverse: true, axisLabel: { color: INK2, fontWeight: 600 } }),
      series: m.series.map(s => ({ name: s.name, type: 'bar', stack: 'x', data: s.data, barMaxWidth: 28,
        itemStyle: { color: s.color, borderColor: '#fcfcfb', borderWidth: 1 } })),
    });
    c.on('click', p => drill({ member: p.name, category: p.seriesName }));
    return c;
  },

  // one Category's 12 months as a small-multiple panel (variant C)
  sparkline(el, d, s) {
    const t = d.trends;
    const c = mount(el, {
      tooltip: { ...base.tooltip, trigger: 'axis' },
      grid: { left: 0, right: 0, top: 6, bottom: 0 },
      xAxis: { type: 'category', data: t.months, show: false, boundaryGap: false },
      yAxis: { type: 'value', show: false, min: 0 },
      series: [{ type: 'line', data: s.data, showSymbol: false, symbolSize: 8, lineStyle: { width: 2, color: s.color }, itemStyle: { color: s.color },
        areaStyle: { color: s.color, opacity: 0.08 }, markPoint: { symbol: 'circle', symbolSize: 8, label: { show: false }, data: [{ coord: [t.months.length - 1, s.data.at(-1)] }] } }],
    });
    c.on('click', p => drill({ month: t.keys[p.dataIndex], category: s.name }));
    return c;
  },

  sankey(el, d) {
    const c = mount(el, {
      tooltip: { ...base.tooltip, trigger: 'item' },
      series: [{
        type: 'sankey', left: 8, right: 150, top: 8, bottom: 8, nodeGap: 10, nodeWidth: 12, draggable: false,
        emphasis: { focus: 'adjacency' }, lineStyle: { color: 'gradient', opacity: 0.35 },
        label: { color: INK2, formatter: p => `${p.name}  ${eur(p.value)}` },
        data: d.sankey.nodes.map(n => ({ ...n, itemStyle: { color: n.color || (n.name === 'Saved' ? '#1baf7a' : n.name === 'From savings' ? '#e34948' : '#52514e') } })),
        links: d.sankey.links,
      }],
    });
    c.on('click', p => { if (p.dataType === 'node' && p.name !== 'Household' && p.name !== 'Saved' && p.name !== 'From savings') drill({ category: p.name }); });
    return c;
  },
};
