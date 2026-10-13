// PROTOTYPE: the same five views as charts_echarts.js, rendered with Plotly, for the library comparison.
const INK2 = '#52514e', MUTED = '#898781', GRID = '#e1e0d9';
const layout = (extra = {}) => ({
  font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', color: INK2, size: 12 },
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  margin: { l: 8, r: 16, t: 28, b: 8 }, hoverlabel: { bgcolor: '#fff' },
  legend: { orientation: 'h', x: 0, y: 1.15 },
  ...extra,
});
const yval = { tickprefix: '€', gridcolor: GRID, zeroline: false, automargin: true, tickformat: ',.0f' };
const cfg = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] };
const hov = '%{y}: €%{x:,.2f}<extra></extra>';

const PG = {
  spending(el, d) {
    const cats = d.byCategory;
    Plotly.newPlot(el, [{
      type: 'bar', orientation: 'h', y: cats.map(c => c.name), x: cats.map(c => c.value),
      marker: { color: cats.map(c => c.color) }, text: cats.map(c => eur(c.value)), textposition: 'outside', cliponaxis: false,
      customdata: cats.map(c => c.subs.map(s => `${s.name} ${eur(s.value, 2)}`).join('<br>')),
      hovertemplate: '<b>%{y}</b> €%{x:,.2f}<br>%{customdata}<extra></extra>',
    }], layout({ yaxis: { autorange: 'reversed', automargin: true }, xaxis: { ...yval } }), cfg);
    el.on('plotly_click', e => drill({ category: e.points[0].y }));
  },

  cashflow(el, d) {
    const cf = d.cashflow;
    Plotly.newPlot(el, [
      { type: 'bar', name: 'Money in', x: cf.months, y: cf.in, marker: { color: '#1baf7a' }, hovertemplate: '€%{y:,.2f}' },
      { type: 'bar', name: 'Money out', x: cf.months, y: cf.out, marker: { color: '#eb6834' }, hovertemplate: '€%{y:,.2f}' },
      { type: 'scatter', mode: 'lines+markers', name: 'Net', x: cf.months, y: cf.net, line: { color: '#0b0b0b', width: 2 }, marker: { size: 8 }, hovertemplate: '€%{y:,.2f}' },
    ], layout({ barmode: 'group', hovermode: 'x unified', yaxis: yval, xaxis: { automargin: true } }), cfg);
    el.on('plotly_click', e => {
      const p = e.points[0];
      drill({ month: cf.keys[p.pointIndex], kind: { 'Money in': 'in', 'Money out': 'out' }[p.data.name] || '' });
    });
  },

  trends(el, d) {
    const t = d.trends;
    Plotly.newPlot(el, t.series.map(s => ({
      type: 'scatter', mode: 'lines', name: s.name, x: t.months, y: s.data, line: { color: s.color, width: 2 }, hovertemplate: '€%{y:,.2f}',
    })), layout({ hovermode: 'x unified', yaxis: yval, legend: { orientation: 'h', x: 0, y: 1.3 }, margin: { l: 8, r: 16, t: 48, b: 8 } }), cfg);
    el.on('plotly_click', e => { const p = e.points[0]; drill({ month: t.keys[p.pointIndex], category: p.data.name }); });
  },

  members(el, d) {
    const m = d.members;
    Plotly.newPlot(el, m.series.map(s => ({
      type: 'bar', orientation: 'h', name: s.name, y: m.names, x: s.data, marker: { color: s.color, line: { color: '#fcfcfb', width: 1 } },
      hovertemplate: `${s.name}: €%{x:,.2f}<extra></extra>`,
    })), layout({ barmode: 'stack', yaxis: { autorange: 'reversed', automargin: true }, xaxis: yval, legend: { orientation: 'h', x: 0, y: 1.3 }, margin: { l: 8, r: 16, t: 48, b: 8 } }), cfg);
    el.on('plotly_click', e => { const p = e.points[0]; drill({ member: p.y, category: p.data.name }); });
  },

  sankey(el, d) {
    const names = d.sankey.nodes.map(n => n.name);
    const color = n => n.color || (n.name === 'Saved' ? '#1baf7a' : n.name === 'From savings' ? '#e34948' : '#52514e');
    Plotly.newPlot(el, [{
      type: 'sankey', arrangement: 'snap', valueformat: ',.0f', valuesuffix: ' €',
      node: { label: names, color: d.sankey.nodes.map(color), pad: 10, thickness: 12, line: { width: 0 } },
      link: {
        source: d.sankey.links.map(l => names.indexOf(l.source)),
        target: d.sankey.links.map(l => names.indexOf(l.target)),
        value: d.sankey.links.map(l => l.value),
        color: d.sankey.links.map(l => color(d.sankey.nodes[names.indexOf(l.target === 'Household' ? l.source : l.target)]) + '55'),
      },
    }], layout({ margin: { l: 8, r: 8, t: 8, b: 8 } }), cfg);
    el.on('plotly_click', e => {
      const p = e.points[0];
      if (p.label && !['Household', 'Saved', 'From savings'].includes(p.label)) drill({ category: p.label });
    });
  },
};
