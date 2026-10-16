// PROTOTYPE (#64 Chart styling), throwaway: lives only on prototype/64-chart-styling. Replaces dashboard.js
// while DEBUG is on. Three variants of every Dashboard chart, switchable with ?variant=A|B|C, ← / → or the
// floating bar, which also switches the theme (Light / System / Dark) to show how the charts re-theme.
//   A  Classic axes      — gridlines, legends, axis tooltips, gradient Sankey: the Monarch-ish default.
//   B  Direct labels     — no legends; names and values sit on the marks; diverging cashflow; target-hued Sankey.
//   C  Small multiples   — one small chart per Category, Net bars under In/Out lines, vertical neutral Sankey.
// Spending's donut is settled by #62 (DESIGN.md) and is the same in every variant, as the colour anchor.
(() => {
  const VARIANTS = { A: 'Classic axes', B: 'Direct labels', C: 'Small multiples' };
  const FONT = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif';
  const AWAITING = 'awaiting';
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // DESIGN.md's Locale Figure Rule: "1.234,56 €"; axes drop the cents; tight spaces go compact ("1,2 tis. €").
  const fmt2 = new Intl.NumberFormat('sl-SI', { style: 'currency', currency: 'EUR', useGrouping: 'always' });
  const fmt0 = new Intl.NumberFormat('sl-SI', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0, useGrouping: 'always' });
  const fmtK = new Intl.NumberFormat('sl-SI', { style: 'currency', currency: 'EUR', notation: 'compact', maximumFractionDigits: 1 });
  const eur = v => fmt2.format(v), eur0 = v => fmt0.format(v), eurK = v => fmtK.format(v);
  const signed = (v, f = eur) => (v > 0 ? '+' : v < 0 ? '−' : '') + f(Math.abs(v));
  const pct = v => `${Math.round(v * 100)} %`;

  // The Fixed Hue Rule: cat-((id − 1) mod 10). Income Subcategories ("in:<id>") wear the Income Category's hue;
  // the payload doesn't carry the Income Category's id yet, so the prototype assumes the seeded one (10).
  const INCOME_CATEGORY = 10;
  const isAwaiting = key => key === AWAITING || key === `in:${AWAITING}`;
  const hue = key => {
    if (isAwaiting(key)) return css('--awaiting');
    const id = String(key).startsWith('in:') ? INCOME_CATEGORY : Number(key);
    return css(`--cat-${(id - 1) % 10}`);
  };
  // The Neutral Wait Rule: Awaiting review is grey plus a 45° hatch.
  const HATCH = { symbol: 'rect', dashArrayX: [1, 0], dashArrayY: [3, 3], rotation: Math.PI / 4, color: 'rgba(255,255,255,.45)' };
  const fill = key => ({ color: hue(key), decal: isAwaiting(key) ? HATCH : null });
  const IN = () => hue(`in:0`), OUT = () => css('--muted'), NET = () => css('--ink');

  const text = (size = 12, weight = 400, color = '--ink-2') => ({ fontFamily: FONT, fontSize: size, fontWeight: weight, color: css(color) });
  const base = () => ({
    darkMode: document.documentElement.matches('[data-theme="dark"]') || (document.documentElement.matches('[data-theme="system"]') && matchMedia('(prefers-color-scheme: dark)').matches),
    backgroundColor: 'transparent', textStyle: { fontFamily: FONT, color: css('--ink-2') },
    animationDuration: 600, animationEasing: 'cubicOut',
    aria: { enabled: true },
  });
  const tooltip = extra => ({
    confine: true, backgroundColor: css('--card'), borderColor: css('--line'), borderWidth: 1, padding: [8, 12],
    textStyle: text(13, 400, '--ink'), extraCssText: `box-shadow:${css('--shadow-pop')};border-radius:10px;`, ...extra,
  });
  const dot = (c, hatched) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:${hatched ? `repeating-linear-gradient(45deg,${c} 0 2px,rgba(255,255,255,.55) 2px 3px)` : c}"></span>`;
  // An axis tooltip as a small table: heading, then one line per series, biggest first, figures aligned.
  const table = (title, lines, foot) => `<div style="font-weight:600;margin-bottom:6px">${title}</div>
    <table style="border-spacing:0;font-variant-numeric:tabular-nums">${lines.map(l =>
      `<tr><td style="padding:2px 16px 2px 0;color:${css('--ink-2')}">${dot(l.colour, l.hatched)}${l.name}</td><td style="text-align:right;font-weight:600">${l.value}</td></tr>`).join('')}
    ${foot ? `<tr><td style="padding:6px 16px 0 0;border-top:1px solid ${css('--line')};color:${css('--muted')}">${foot[0]}</td><td style="padding-top:6px;border-top:1px solid ${css('--line')};text-align:right;font-weight:600">${foot[1]}</td></tr>` : ''}</table>`;
  const valueAxis = (extra = {}) => ({
    type: 'value', axisLabel: { ...text(12, 400, '--muted'), formatter: v => eur0(v) },
    splitLine: { lineStyle: { color: css('--line') } }, axisLine: { show: false }, axisTick: { show: false }, ...extra,
  });
  const categoryAxis = (data, extra = {}) => ({
    type: 'category', data, axisLine: { lineStyle: { color: css('--line-strong') } }, axisTick: { show: false },
    axisLabel: text(12, 400, '--muted'), ...extra,
  });
  const legend = extra => ({ top: 0, left: 0, type: 'scroll', icon: 'circle', itemWidth: 8, itemHeight: 8, itemGap: 16,
    textStyle: text(12, 500, '--ink-2'), pageTextStyle: text(12, 400, '--muted'), inactiveColor: css('--line-strong'), ...extra });
  const narrow = el => el.clientWidth < 520;

  // ---------- Spending: the settled donut (DESIGN.md), same in every variant ----------
  const donut = (data, el) => {
    const total = data.bars.reduce((s, b) => s + b.value, 0);
    const n = narrow(el);
    const labelled = b => !isAwaiting(b.key) && (!n || b.value / total >= 0.05);
    return {
      ...base(),
      tooltip: tooltip({ trigger: 'item', formatter: p => `${dot(p.color)}${p.name}<br><b style="font-variant-numeric:tabular-nums">${eur(p.value)}</b> · ${Math.round(p.percent)} %` }),
      title: { text: eur(total), subtext: 'Spent', left: 'center', top: 'center', itemGap: 2,
        textStyle: { ...text(n ? 17 : 22, 600, '--ink'), letterSpacing: -0.4 }, subtextStyle: text(13, 400, '--muted') },
      series: [{
        type: 'pie', cursor: 'pointer', radius: n ? ['47%', '66%'] : ['56%', '78%'], padAngle: 1.5, itemStyle: { borderRadius: 5 },
        label: { ...text(n ? 11 : 12, 500), formatter: p => labelled(data.bars[p.dataIndex]) ? p.name : '' },
        labelLine: { length: 8, length2: 10, lineStyle: { color: css('--line-strong') } },
        emphasis: { scale: true, scaleSize: 6 },
        data: data.bars.map(b => ({ name: b.name, value: b.value, key: b.key, itemStyle: fill(b.key), labelLine: { show: labelled(b) } })),
      }],
    };
  };

  // ---------- Variant A: Classic axes ----------
  const A = {
    spending: donut,
    cashflow: data => {
      const marks = (values, side) => values.map((value, i) => ({ value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      const series = [
        { name: data.labels.in, type: 'bar', cursor: 'pointer', data: marks(data.in, 'in'), itemStyle: { color: IN(), borderRadius: [4, 4, 0, 0] }, barGap: '10%', barMaxWidth: 22 },
        { name: data.labels.out, type: 'bar', cursor: 'pointer', data: marks(data.out, 'out'), itemStyle: { color: OUT(), borderRadius: [4, 4, 0, 0] }, barMaxWidth: 22 },
        { name: data.labels.net, type: 'line', cursor: 'pointer', data: marks(data.net), symbol: 'circle', symbolSize: 7, lineStyle: { width: 2, color: NET() }, itemStyle: { color: NET(), borderColor: css('--card'), borderWidth: 2 }, z: 3 },
        ...(data.others ? [{ name: data.labels.others, type: 'line', cursor: 'pointer', data: marks(data.others, 'others'), symbol: 'circle', symbolSize: 7, lineStyle: { width: 2, type: 'dashed', color: css('--ink-2') }, itemStyle: { color: css('--ink-2') } }] : []),
      ];
      return {
        ...base(), legend: legend(),
        tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: css('--hover'), opacity: 0.6 } },
          formatter: ps => table(ps[0].axisValue, ps.map(p => ({ name: p.seriesName, colour: p.color, value: p.seriesType === 'line' ? signed(p.value) : eur(p.value) }))) }),
        grid: { left: 4, right: 8, top: 40, bottom: 4, containLabel: true },
        xAxis: categoryAxis(data.months), yAxis: valueAxis(), series,
      };
    },
    trends: data => ({
      ...base(), legend: legend(),
      tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: css('--line-strong') } },
        formatter: ps => {
          const sorted = [...ps].sort((a, b) => b.value - a.value);
          return table(ps[0].axisValue, sorted.map(p => ({ name: p.seriesName, colour: p.color, hatched: isAwaiting(data.lines[p.seriesIndex].key), value: eur(p.value) })),
            ['Total', eur(ps.reduce((s, p) => s + p.value, 0))]);
        } }),
      grid: { left: 4, right: 32, top: 40, bottom: 4, containLabel: true },
      xAxis: categoryAxis(data.months, { boundaryGap: false }), yAxis: valueAxis(),
      series: data.lines.map(line => ({
        name: line.name, type: 'line', cursor: 'pointer', showSymbol: false, symbol: 'circle', symbolSize: 7,
        emphasis: { focus: 'series' }, blur: { lineStyle: { opacity: 0.15 } },
        data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
        lineStyle: { width: 2, color: hue(line.key), type: isAwaiting(line.key) ? 'dashed' : 'solid' }, itemStyle: { color: hue(line.key) },
      })),
    }),
    per_member: data => ({
      ...base(), legend: legend(),
      tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: css('--hover'), opacity: 0.6 } },
        formatter: ps => table(ps[0].axisValue, ps.filter(p => p.value).sort((a, b) => b.value - a.value).map(p => ({ name: p.seriesName, colour: p.color, hatched: isAwaiting(data.segments[p.seriesIndex].key), value: eur(p.value) })),
          ['Total', eur(ps.reduce((s, p) => s + (p.value || 0), 0))]) }),
      grid: { left: 4, right: 16, top: 40, bottom: 4, containLabel: true },
      xAxis: valueAxis({ splitNumber: 4 }),
      yAxis: categoryAxis(data.members, { inverse: true, axisLine: { show: false }, axisLabel: text(13, 600, '--ink') }),
      series: data.segments.map(segment => ({
        name: segment.name, type: 'bar', stack: 'spent', barMaxWidth: 28, cursor: 'pointer', data: segment.data,
        itemStyle: { ...fill(segment.key), borderColor: css('--card'), borderWidth: 1.5 },
        emphasis: { focus: 'series' }, blur: { itemStyle: { opacity: 0.25 } },
      })),
    }),
    money_flow: (data, el) => sankey(data, el, {
      links: { color: 'gradient', opacity: 0.3 }, emphasisLinks: { opacity: 0.6 }, nodeWidth: 12, nodeGap: 10,
      label: (p, labels) => `{name|${labels[p.data.name]}}  {amount|${eur0(p.value)}}`,
    }),
  };

  // One Sankey builder; the variants differ in links, node size, orientation and labels.
  const sankeyNode = n => n.name === 'household' ? css('--ink-2') : n.name === 'saved' || n.name === 'from_savings' || n.name === 'others' ? css('--muted') : hue(n.key);
  const sankey = (data, el, o) => {
    const labels = Object.fromEntries(data.nodes.map(n => [n.name, n.label]));
    const moneyIn = data.links.filter(l => l.target === 'household').reduce((s, l) => s + l.value, 0);
    const vertical = o.orient === 'vertical';
    return {
      ...base(),
      tooltip: tooltip({ trigger: 'item', formatter: p => p.dataType === 'edge'
        ? `${labels[p.data.source]} → ${labels[p.data.target]}<br><b style="font-variant-numeric:tabular-nums">${eur(p.value)}</b> · ${pct(p.value / moneyIn)} of money in`
        : `${dot(p.color)}${labels[p.data.name]}<br><b style="font-variant-numeric:tabular-nums">${eur(p.value)}</b>` }),
      series: [{
        type: 'sankey', orient: o.orient || 'horizontal', draggable: false, nodeAlign: 'justify',
        left: vertical ? 16 : (narrow(el) ? 96 : 150), right: vertical ? 16 : (narrow(el) ? 96 : 150), top: vertical ? 40 : 28, bottom: vertical ? 56 : 8,
        labelLayout: { hideOverlap: true },
        nodeGap: o.nodeGap, nodeWidth: o.nodeWidth, layoutIterations: 32,
        emphasis: { focus: 'adjacency', lineStyle: o.emphasisLinks }, blur: { lineStyle: { opacity: 0.08 }, itemStyle: { opacity: 0.3 } },
        lineStyle: { curveness: 0.5, ...o.links },
        itemStyle: { borderWidth: 0, borderRadius: 2 },
        label: {
          ...text(12, 500, '--ink-2'), formatter: p => o.label(p, labels, moneyIn),
          rich: { name: text(12, 500, '--ink-2'), amount: { ...text(12, 400, '--muted') }, share: text(11, 400, '--muted') },
          ...(vertical ? { position: 'bottom', distance: 6, align: 'center' } : {}),
        },
        data: data.nodes.map(n => {
          const source = data.links.some(l => l.source === n.name && l.target === 'household');
          const share = (data.links.find(l => l.source === n.name || l.target === n.name)?.value ?? 0) / moneyIn;
          const label = n.name === 'household' ? { position: vertical ? 'inside' : 'top', color: vertical ? '#fff' : undefined, distance: 6 }
            : source ? { position: vertical ? 'top' : 'left' } : {};
          // Vertical nodes are narrow: only the bigger ones can carry a name.
          if (vertical && n.name !== 'household' && share < 0.06) label.show = false;
          return { ...n, cursor: n.key ? 'pointer' : 'default', label, itemStyle: { color: sankeyNode(n), decal: isAwaiting(n.key) ? HATCH : null } };
        }),
        // Target-hued links would paint all income in Household's grey, so what flows in wears its source's hue.
        links: o.links.color === 'target' ? data.links.map(l => l.target === 'household' ? { ...l, lineStyle: { color: 'source' } } : l) : data.links,
      }],
    };
  };

  // ---------- Variant B: Direct labels ----------
  const B = {
    spending: donut,
    // Diverging: money in rises above zero, money out hangs below it, Net is a labelled dot. No legend; the
    // card's own key line says which is which.
    cashflow: data => {
      const marks = (values, side, sign = 1) => values.map((value, i) => ({ value: sign * value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      return {
        ...base(),
        title: { text: `▲ ${data.labels.in}    ▼ ${data.labels.out}    ● ${data.labels.net}`, left: 0, top: 0, textStyle: text(12, 500, '--muted') },
        tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: css('--hover'), opacity: 0.6 } },
          formatter: ps => table(ps[0].axisValue, ps.map(p => ({ name: p.seriesName, colour: p.color, value: p.seriesType === 'bar' ? eur(Math.abs(p.value)) : signed(p.value) }))) }),
        grid: { left: 4, right: 8, top: 36, bottom: 4, containLabel: true },
        xAxis: categoryAxis(data.months, { axisLine: { show: false }, position: 'bottom', offset: 0 }),
        yAxis: valueAxis({ axisLabel: { ...text(12, 400, '--muted'), formatter: v => v === 0 ? '0' : eurK(Math.abs(v)) },
          splitLine: { lineStyle: { color: css('--line'), type: [2, 4] } } }),
        series: [
          { name: data.labels.in, type: 'bar', stack: 'flow', cursor: 'pointer', data: marks(data.in, 'in'), itemStyle: { color: IN(), borderRadius: [4, 4, 0, 0] }, barMaxWidth: 26,
            markLine: { silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: css('--ink-2'), type: 'solid', width: 1 }, data: [{ yAxis: 0 }] } },
          { name: data.labels.out, type: 'bar', stack: 'flow', cursor: 'pointer', data: marks(data.out, 'out', -1), itemStyle: { color: OUT(), borderRadius: [0, 0, 4, 4] }, barMaxWidth: 26 },
          { name: data.labels.net, type: 'scatter', cursor: 'pointer', data: marks(data.net), symbolSize: 9, z: 4,
            itemStyle: { color: NET(), borderColor: css('--card'), borderWidth: 2 },
            label: { show: true, position: 'top', ...text(11, 600, '--ink'), formatter: p => signed(p.value, eur0) }, labelLayout: { hideOverlap: true } },
          ...(data.others ? [{ name: data.labels.others, type: 'line', cursor: 'pointer', data: marks(data.others, 'others'), symbolSize: 6, lineStyle: { width: 1.5, type: 'dashed', color: css('--ink-2') }, itemStyle: { color: css('--ink-2') } }] : []),
        ],
      };
    },
    // Each line names itself at its end; hover isolates it.
    trends: (data, el) => {
      const n = narrow(el);
      const sums = data.lines.map(l => l.data.reduce((s, v) => s + v, 0)), all = sums.reduce((s, v) => s + v, 0);
      return {
        ...base(),
        tooltip: tooltip({ trigger: 'item', formatter: p => `${dot(p.color)}${p.seriesName} · ${p.name}<br><b style="font-variant-numeric:tabular-nums">${eur(p.value)}</b>` }),
        grid: { left: 4, right: n ? 96 : 170, top: 12, bottom: 4, containLabel: true },
        xAxis: categoryAxis(data.months, { boundaryGap: false }),
        yAxis: valueAxis({ axisLabel: { ...text(12, 400, '--muted'), formatter: v => eurK(v) }, splitLine: { lineStyle: { color: css('--line'), type: [2, 4] } } }),
        series: data.lines.map(line => ({
          name: line.name, type: 'line', cursor: 'pointer', symbol: 'circle', symbolSize: 6, showSymbol: false,
          emphasis: { focus: 'series', lineStyle: { width: 3 } }, blur: { lineStyle: { opacity: 0.12 }, endLabel: { opacity: 0.3 } },
          data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
          lineStyle: { width: 2, color: hue(line.key), type: isAwaiting(line.key) ? 'dashed' : 'solid' }, itemStyle: { color: hue(line.key) },
          endLabel: { show: sums[data.lines.indexOf(line)] / all >= 0.04, ...text(12, 500, '--ink-2'), distance: 8,
            formatter: p => n ? line.name : `${line.name}  {v|${eurK(p.value)}}`, rich: { v: text(12, 400, '--muted') } },
          labelLayout: { moveOverlap: 'shiftY' },
        })),
      };
    },
    // Segments name themselves where they're wide enough; each bar ends in its total.
    per_member: data => {
      const totals = data.members.map((_, i) => data.segments.reduce((s, seg) => s + (seg.data[i]?.value ?? seg.data[i] ?? 0), 0));
      const max = Math.max(...totals);
      return {
        ...base(),
        tooltip: tooltip({ trigger: 'item', formatter: p => `${dot(p.color)}${p.seriesName} · ${p.name}<br><b style="font-variant-numeric:tabular-nums">${eur(p.value)}</b> · ${pct(p.value / totals[p.dataIndex])} of ${p.name}` }),
        grid: { left: 4, right: 96, top: 4, bottom: 4, containLabel: true },
        xAxis: { type: 'value', show: false, max },
        yAxis: categoryAxis(data.members, { inverse: true, axisLine: { show: false }, axisLabel: text(13, 600, '--ink') }),
        series: [
          ...data.segments.map(segment => ({
            name: segment.name, type: 'bar', stack: 'spent', barWidth: '56%', cursor: 'pointer', data: segment.data,
            itemStyle: { ...fill(segment.key), borderColor: css('--card'), borderWidth: 2, borderRadius: 3 },
            label: { show: true, position: 'insideLeft', ...text(11, 600, '--ink'), color: '#111827', formatter: p => p.value / max > 0.08 ? `${segment.name}\n{v|${eurK(p.value)}}` : '', rich: { v: { fontFamily: FONT, fontSize: 11, color: '#111827cc' } } },
            labelLayout: { hideOverlap: true },
            emphasis: { focus: 'series' }, blur: { itemStyle: { opacity: 0.25 } },
          })),
          { type: 'bar', stack: 'spent', silent: true, data: totals.map(() => 0), label: { show: true, position: 'right', ...text(13, 600, '--ink'), formatter: p => eur0(totals[p.dataIndex]) } },
        ],
      };
    },
    money_flow: (data, el) => sankey(data, el, {
      links: { color: 'target', opacity: 0.4 }, emphasisLinks: { opacity: 0.75 }, nodeWidth: 18, nodeGap: 14,
      label: (p, labels) => `{name|${labels[p.data.name]}}\n{amount|${eur0(p.value)}}`,
    }),
  };

  // ---------- Variant C: Small multiples ----------
  const C = {
    spending: donut,
    // Net is the bar (above or below zero, never red/green); In and Out are the lines it's the gap between.
    cashflow: data => {
      const marks = (values, side) => values.map((value, i) => ({ value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      const area = c => ({ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: c + '40' }, { offset: 1, color: c + '00' }]) });
      return {
        ...base(), legend: legend({ top: 'auto', bottom: 0, left: 'center' }),
        tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: css('--line-strong') } },
          formatter: ps => table(ps[0].axisValue, ps.filter(p => p.seriesType === 'line').map(p => ({ name: p.seriesName, colour: p.color, value: eur(p.value) })),
            [ps.find(p => p.seriesType === 'bar').seriesName, signed(ps.find(p => p.seriesType === 'bar').value)]) }),
        grid: { left: 4, right: 8, top: 12, bottom: 36, containLabel: true },
        xAxis: categoryAxis(data.months), yAxis: valueAxis(),
        series: [
          { name: data.labels.net, type: 'bar', cursor: 'pointer', data: marks(data.net), barMaxWidth: 18, itemStyle: { color: css('--line-strong'), borderRadius: 3 } },
          { name: data.labels.in, type: 'line', cursor: 'pointer', data: marks(data.in, 'in'), smooth: 0.3, smoothMonotone: 'x', symbol: 'circle', symbolSize: 6, showSymbol: data.months.length === 1, lineStyle: { width: 2.5, color: IN() }, itemStyle: { color: IN() }, areaStyle: area(IN()) },
          { name: data.labels.out, type: 'line', cursor: 'pointer', data: marks(data.out, 'out'), smooth: 0.3, smoothMonotone: 'x', symbol: 'circle', symbolSize: 6, showSymbol: data.months.length === 1, lineStyle: { width: 2.5, color: OUT() }, itemStyle: { color: OUT() }, areaStyle: area(OUT()) },
          ...(data.others ? [{ name: data.labels.others, type: 'line', cursor: 'pointer', data: marks(data.others, 'others'), showSymbol: false, lineStyle: { width: 1.5, type: 'dashed', color: css('--ink-2') }, itemStyle: { color: css('--ink-2') } }] : []),
        ],
      };
    },
    // One small area chart per Category, sharing one scale so heights compare honestly.
    trends: (data, el) => {
      const cols = el.clientWidth < 520 ? 1 : el.clientWidth < 900 ? 2 : 3;
      const rows = Math.ceil(data.lines.length / cols), cellH = 128, gapX = 28, gapY = 44, top = 30;
      el.classList.add('multiples');
      el.style.height = `${top + rows * (cellH + gapY)}px`;
      const max = Math.max(...data.lines.flatMap(l => l.data));
      const w = `${(100 - (cols - 1) * 2.4) / cols}%`;
      const at = i => ({ left: `${(i % cols) * (100 / cols)}%`, top: top + Math.floor(i / cols) * (cellH + gapY) });
      return {
        ...base(), animation: false,
        tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: css('--line-strong') } },
          formatter: ps => `${dot(ps[0].color, isAwaiting(data.lines[ps[0].seriesIndex].key))}${ps[0].seriesName} · ${ps[0].axisValue}<br><b style="font-variant-numeric:tabular-nums">${eur(ps[0].value)}</b>` }),
        title: data.lines.map((line, i) => ({
          text: line.name, subtext: eur0(line.data.reduce((s, v) => s + v, 0)), left: at(i).left, top: at(i).top - 28,
          textStyle: text(13, 600, '--ink'), subtextStyle: text(12, 400, '--muted'), itemGap: 2, padding: 0,
        })),
        grid: data.lines.map((_, i) => ({ left: at(i).left, top: at(i).top + 8, width: w, height: cellH - 28, containLabel: false })),
        xAxis: data.lines.map((_, i) => ({ ...categoryAxis(data.months, { boundaryGap: false }), gridIndex: i,
          axisLabel: { ...text(10, 400, '--muted'), interval: i => i === 0 || i === data.months.length - 1, alignMinLabel: 'left', alignMaxLabel: 'right' } })),
        yAxis: data.lines.map((_, i) => ({ type: 'value', gridIndex: i, max, show: true, splitNumber: 1, axisLabel: { show: false },
          splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false } })),
        series: data.lines.map((line, i) => {
          const c = hue(line.key);
          return {
            name: line.name, type: 'line', xAxisIndex: i, yAxisIndex: i, cursor: 'pointer', showSymbol: false, symbol: 'circle', symbolSize: 6, smooth: 0.25,
            data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
            lineStyle: { width: 2, color: c, type: isAwaiting(line.key) ? 'dashed' : 'solid' }, itemStyle: { color: c },
            areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: c + '55' }, { offset: 1, color: c + '05' }]) },
          };
        }),
        axisPointer: { link: [{ xAxisIndex: 'all' }] },
      };
    },
    // Members side by side per Category: who spends what where, the biggest Category first. Members are told
    // apart by neutral shades (and Joint by the hatch), since only Categories wear hues.
    per_member: data => {
      const shades = [css('--ink-2'), css('--muted'), css('--faint'), css('--line-strong')];
      const cats = data.segments.map(s => ({ ...s, total: s.data.reduce((t, d) => t + (d?.value ?? d ?? 0), 0) })).sort((a, b) => b.total - a.total);
      return {
        ...base(), legend: legend({ data: data.members }),
        tooltip: tooltip({ trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: css('--hover'), opacity: 0.6 } },
          formatter: ps => table(ps[0].axisValue, ps.map(p => ({ name: p.seriesName, colour: p.color, value: eur(p.value || 0) })), ['Total', eur(ps.reduce((s, p) => s + (p.value || 0), 0))]) }),
        grid: { left: 4, right: 16, top: 36, bottom: 4, containLabel: true },
        xAxis: valueAxis({ splitNumber: 4 }),
        yAxis: categoryAxis(cats.map(c => c.name), { inverse: true, axisLine: { show: false },
          axisLabel: { ...text(12, 500, '--ink-2'), formatter: (v, i) => `{d${i}|●} ${v}`, rich: Object.fromEntries(cats.map((c, i) => [`d${i}`, { color: hue(c.key), fontSize: 12 }])) } }),
        series: data.members.map((member, m) => ({
          name: member, type: 'bar', barGap: '15%', barMaxWidth: 10, cursor: 'pointer',
          data: cats.map(c => { const d = c.data[m]; return typeof d === 'object' && d ? d : { value: d ?? 0 }; }),
          itemStyle: { color: shades[m % shades.length], borderRadius: [0, 3, 3, 0], decal: /joint/i.test(member) ? HATCH : null },
        })),
      };
    },
    money_flow: (data, el) => sankey(data, el, {
      orient: 'vertical', links: { color: css('--line-strong'), opacity: 0.55 }, emphasisLinks: { color: 'target', opacity: 0.8 }, nodeWidth: 14, nodeGap: 12,
      label: (p, labels, moneyIn) => p.data.name === 'household' ? `${labels[p.data.name]}  ${eur0(p.value)}` : `{name|${labels[p.data.name]}}\n{share|${pct(p.value / moneyIn)}}`,
    }),
  };

  const SETS = { A, B, C };
  const current = () => {
    const q = new URLSearchParams(location.search).get('variant');
    if (q && SETS[q]) return q;
    try { return SETS[localStorage.getItem('proto64-variant')] ? localStorage.getItem('proto64-variant') : 'A'; } catch { return 'A'; }
  };

  // ---------- Mounting (as dashboard.js, plus a redraw for theme and variant changes) ----------
  const charts = new Map();
  const draw = (el, animate) => {
    const { chart, data } = charts.get(el);
    el.classList.remove('multiples'); el.style.height = '';
    const option = SETS[current()][el.dataset.chart](data, el);
    chart.setOption({ ...option, animation: option.animation !== false && animate && !reduced }, { notMerge: true });
    chart.resize();
  };
  const mount = el => {
    if (echarts.getInstanceByDom(el)) return;
    const data = JSON.parse(document.getElementById(el.dataset.source).textContent);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    charts.set(el, { chart, data, width: el.clientWidth });
    draw(el, true);
    chart.on('click', p => { if (p.data?.key) htmx.ajax('GET', data.drill + encodeURIComponent(p.data.key), '#drill'); });
    // Width changes can change the layout (labels, columns), so redraw rather than only resize.
    const observer = new ResizeObserver(() => {
      const entry = charts.get(el);
      if (entry && Math.abs(entry.width - el.clientWidth) > 8) { entry.width = el.clientWidth; draw(el, false); } else chart.resize();
    });
    observer.observe(el);
    charts.get(el).observer = observer;
  };
  const unmount = el => {
    charts.get(el)?.observer.disconnect();
    charts.delete(el);
    echarts.getInstanceByDom(el)?.dispose();
  };
  const redrawAll = () => charts.forEach((_, el) => el.isConnected ? draw(el, false) : unmount(el));
  const all = root => root.querySelectorAll('[data-chart]');

  document.addEventListener('DOMContentLoaded', () => { all(document).forEach(mount); bar(); });
  document.addEventListener('htmx:beforeSwap', e => all(e.detail.target).forEach(unmount));
  document.addEventListener('htmx:afterSettle', e => all(e.detail.elt).forEach(mount));
  document.addEventListener('htmx:historyRestore', () => all(document).forEach(mount));
  document.addEventListener('htmx:afterRequest', e => {
    const outcome = /^\/transactions\/\d+\/outcome\/$/.test(e.detail.requestConfig.path);
    if (e.detail.successful && outcome && document.getElementById('numbers')) {
      htmx.ajax('GET', location.href, { target: '#numbers', select: '#numbers', swap: 'outerHTML' });
    }
  });

  // ---------- Theme: data-theme on <html>; charts rebuild from the tokens on every change ----------
  const root = document.documentElement;
  try { root.dataset.theme = localStorage.getItem('theme') || 'system'; } catch { root.dataset.theme = 'system'; }
  new MutationObserver(redrawAll).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);
  const setTheme = t => { root.dataset.theme = t; try { localStorage.setItem('theme', t); } catch {} paintBar(); };

  // ---------- The floating switcher ----------
  const keys = Object.keys(VARIANTS);
  const setVariant = v => {
    try { localStorage.setItem('proto64-variant', v); } catch {}
    const url = new URL(location.href); url.searchParams.set('variant', v); history.replaceState(history.state, '', url);
    paintBar(); redrawAll();
  };
  const step = d => setVariant(keys[(keys.indexOf(current()) + d + keys.length) % keys.length]);
  let el;
  const paintBar = () => {
    if (!el) return;
    el.querySelector('.label').textContent = `${current()} · ${VARIANTS[current()]}`;
    el.querySelectorAll('[data-theme-set]').forEach(b => b.setAttribute('aria-pressed', b.dataset.themeSet === root.dataset.theme));
  };
  const bar = () => {
    el = document.createElement('div');
    el.className = 'proto-bar';
    el.innerHTML = `<button data-step="-1" aria-label="Previous variant">←</button><span class="label"></span><button data-step="1" aria-label="Next variant">→</button>
      <span class="sep"></span><button data-theme-set="light">Light</button><button data-theme-set="system">System</button><button data-theme-set="dark">Dark</button>`;
    el.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.step) step(+b.dataset.step); else setTheme(b.dataset.themeSet);
    });
    document.body.append(el);
    paintBar();
  };
  document.addEventListener('keydown', e => {
    if (e.target.closest('input, textarea, select, [contenteditable]') || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'ArrowLeft') step(-1);
    if (e.key === 'ArrowRight') step(1);
  });
})();
