// Mounts the dashboard's ECharts charts: on page load, and whenever HTMX swaps a view in.
// Each chart reads its data from the JSON script named by `data-source`; clicking a mark loads its Transactions into #drill.
// Colours come from the CSS tokens, so a chart is rebuilt on `themechange` (static/theme.js).
// On Spending, the donut and the Category list light each other's Category, and the drill-down's Category is the
// open one in both: #drill's card names it (`data-mark`), so whatever opens or closes it, they follow.
(() => {
  const AWAITING = 'awaiting', HOUSEHOLD = 'household';
  const { money, moneyWhole, moneySigned, share } = window.Figures;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  // Awaiting review's hatch (the Neutral Wait Rule): 45° white stripes at 45 %.
  const HATCH = { symbol: 'rect', dashArrayX: [1, 0], dashArrayY: [3, 3], rotation: Math.PI / 4, color: 'rgba(255, 255, 255, .45)' };
  const token = name => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

  // The options' building blocks in the current theme's colours: the parts every chart shares (docs/design/charts.md).
  const theme = () => {
    const INK = token('ink'), INK2 = token('ink-2'), MUTED = token('muted'), FAINT = token('faint'), LINE = token('line'), LINE_STRONG = token('line-strong'), CARD = token('card');
    // A Category keeps its hue in every view: cat-((id − 1) mod 10). Awaiting review is always its neutral grey.
    const colour = key => key === AWAITING ? token('awaiting') : token(`cat-${(Number(key) - 1) % 10}`);
    const text = (fontSize, fontWeight, color) => ({ fontFamily: token('font'), fontSize, fontWeight, color });
    const shadow = { type: 'shadow', shadowStyle: { color: token('hover'), opacity: 0.6 } };
    return {
      INK, INK2, MUTED, FAINT, LINE, LINE_STRONG, CARD, colour, text,
      // The entrance, once on mount: not on a rebuild, and never under reduced motion. The chart's description is
      // its element's label, rather than ECharts' own (English) one.
      base: ({ animate, label }) => ({
        textStyle: text(12, 400, INK2), aria: { enabled: true, label: { description: label } },
        animation: animate && !reducedMotion.matches, animationDuration: 600, animationEasing: 'cubicOut',
      }),
      tooltip: {
        confine: true, backgroundColor: CARD, borderColor: LINE, borderWidth: 1, padding: [8, 12], textStyle: text(13, 400, INK),
        extraCssText: `border-radius: 10px; box-shadow: ${token('shadow-pop')}`,
      },
      // Bars point with a shaded band, lines with a hairline.
      pointer: { bar: shadow, line: { type: 'line', lineStyle: { color: LINE_STRONG } } },
      valueAxis: {
        type: 'value', axisLabel: { ...text(12, 400, MUTED), formatter: v => moneyWhole(v) },
        splitLine: { lineStyle: { color: LINE } }, axisLine: { show: false }, axisTick: { show: false },
      },
      categoryAxis: (data, extra = {}) => ({
        type: 'category', data, axisLine: { lineStyle: { color: LINE_STRONG } }, axisTick: { show: false },
        axisLabel: text(12, 400, MUTED), ...extra,
      }),
      legend: {
        top: 0, left: 0, type: 'scroll', icon: 'circle', itemWidth: 8, itemHeight: 8, itemGap: 16,
        textStyle: text(12, 500, INK2), pageTextStyle: text(12, 400, MUTED), inactiveColor: LINE_STRONG,
        pageIconColor: INK2, pageIconInactiveColor: LINE_STRONG,
      },
      // Hovering a series focuses it: the other lines fade to 15 %, the other bars to 25 %.
      focus: { emphasis: { focus: 'series' }, blur: { lineStyle: { opacity: 0.15 }, itemStyle: { opacity: 0.25 } } },
    };
  };

  const html = echarts.format.encodeHTML;

  // ---- Period completeness (docs/design/period-completeness.md): each month of a chart over months has a state ----
  const BANDED = ['partial', 'partly_tracked', 'in_progress'];
  const stateOf = (data, i) => data.states?.[i] || 'complete';
  // The month axis: a Not tracked month's label is Faint, and the running month's reads "Oct (so far)".
  const monthAxis = (data, { categoryAxis, text, MUTED, FAINT }, extra = {}) => categoryAxis(data.months, {
    ...extra,
    axisLabel: {
      ...text(12, 400, MUTED),
      color: (_value, i) => stateOf(data, i) === 'not_tracked' ? FAINT : MUTED,
      formatter: (value, i) => stateOf(data, i) === 'in_progress' ? data.words.so_far.replace('%(month)s', value) : value,
    },
  });
  // A full-height band in Hover behind each Partial, Partly tracked and In progress month, labelled at its top. The
  // bands are bars on hidden axes of their own: a markArea from a month to itself has no width on a category axis,
  // and on the shared axes they would join Cash flow's bar groups. Hiding a legend entry never hides them.
  const BANDS = 'bands';
  // Months in a row in one state make one wide band, labelled once, its label breaking to the band's width.
  const bands = (data, { text, MUTED }, { width }) => data.states?.some(s => BANDED.includes(s)) ? {
    xAxis: [{ type: 'category', data: data.months, show: false, boundaryGap: true, axisPointer: { show: false } }],
    yAxis: [{ type: 'value', show: false, min: 0, max: 1 }],
    series: [{
      id: BANDS, type: 'bar', xAxisIndex: 1, yAxisIndex: 1, z: 0, barWidth: '100%', silent: true, tooltip: { show: false },
      itemStyle: { color: token('hover') }, emphasis: { disabled: true },
      label: { position: 'insideTop', distance: 6, ...text(11, 500, MUTED), overflow: 'break', lineHeight: 14 },
      data: data.states.map((s, i) => {
        if (!BANDED.includes(s)) return null;
        if (data.states[i - 1] === s) return { value: 1, label: { show: false } };
        let run = 1;
        while (data.states[i + run] === s) run++;
        // The grid's width less the value axis' labels, shared by the months. A band too narrow for the label's longest
        // word (about 6px a letter at 11px) goes unlabelled, on a phone: the table's qualifiers and the tooltip say it.
        const room = (width - 64) / data.states.length * run - 8;
        const word = Math.max(...data.words[s].split(' ').map(w => w.length)) * 6;
        return { value: 1, label: { show: room >= word, formatter: data.words[s], width: room } };
      }),
    }],
  } : { xAxis: [], yAxis: [], series: [] };
  // What an axis tooltip says first about its month: why it is incomplete, if it is.
  const reasonOf = (data, i) => data.reasons?.[i] ? `<p class="tip-reason">${html(data.reasons[i])}</p>` : '';
  // An axis tooltip for a month: a Not tracked one says only why; the others open with the reason above their table.
  const monthTip = (data, ps, tip) => {
    ps = ps.filter(p => p.seriesId !== BANDS);
    if (!ps.length) return '';
    const i = ps[0].dataIndex;
    if (stateOf(data, i) === 'not_tracked') return `<p class="tip-head">${html(ps[0].axisValue)}</p>${reasonOf(data, i)}`;
    return tip(ps).replace('</p>', `</p>${reasonOf(data, i)}`);
  };
  const dot = (colour, hatched) => `<i class="dot${hatched ? ' awaiting' : ''}" style="--hue: ${colour}"></i>`;
  // An axis tooltip: the month (or Bucket), then one row per series (dot, name, amount), and a Total under a hairline.
  const table = (title, rows, total) => `<p class="tip-head">${html(title)}</p><table class="tip">${rows.map(r =>
    `<tr><td>${dot(r.colour, r.hatched)}${html(r.name)}</td><td>${r.value}</td></tr>`).join('')}${
    total ? `<tfoot><tr><td>${html(total[0])}</td><td>${total[1]}</td></tr></tfoot>` : ''}</table>`;
  // Category series in a tooltip, biggest first, with their Total.
  const ranked = (ps, words, awaiting) => {
    const shown = ps.filter(p => p.value).sort((a, b) => b.value - a.value);
    return table(ps[0].axisValue, shown.map(p => ({ name: p.seriesName, colour: p.color, hatched: awaiting(p), value: money(p.value) })),
      [words.total, money(ps.reduce((sum, p) => sum + (p.value || 0), 0))]);
  };

  // The Money in bar wears the Income Category's hue, darkened until it stands 3:1 off the card (WCAG 1.4.11).
  const rgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const luminance = c => {
    const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  const standingOff = (hex, ground, toward) => {
    const from = rgb(hex), card = rgb(ground), to = rgb(toward);
    for (let t = 0; t <= 1; t += 0.05) {
      const mixed = from.map((v, i) => Math.round(v + (to[i] - v) * t));
      if (contrast(mixed, card) >= 3) return `rgb(${mixed.join(', ')})`;
    }
    return toward;
  };

  const options = {
    // The donut: segments labelled directly (only those of 5 % or more when narrow), Awaiting review hatched and
    // unlabelled, and every segment but the open Category's dimmed while one is open. It sweeps in once.
    spending: (data, { text, tooltip, INK2, LINE_STRONG, colour }, { narrow, open, animate }) => {
      const total = data.total;
      const labelled = s => s.key !== AWAITING && (!narrow || s.value / total >= 0.05);
      return {
        textStyle: text(12, 400, INK2),
        animation: animate && !reducedMotion.matches, animationDuration: 700, animationEasing: 'cubicOut',
        tooltip: { ...tooltip, trigger: 'item', confine: true, formatter: p => `${html(p.name)}<br><b>${money(p.value)}</b> · ${share(p.value / total)}` },
        series: [{
          type: 'pie', radius: narrow ? ['47%', '66%'] : ['56%', '78%'], padAngle: 1.5, cursor: 'pointer',
          itemStyle: { borderRadius: 5 },
          label: {
            color: INK2, fontWeight: 500, fontSize: narrow ? 11 : 12, overflow: 'none',
            alignTo: narrow ? 'edge' : 'none', edgeDistance: 2, formatter: p => labelled(p.data) ? p.name : '',
          },
          labelLine: { length: 8, length2: 10, lineStyle: { color: LINE_STRONG } },
          emphasis: { scale: true, scaleSize: 6 },
          data: data.segments.map(s => ({
            name: s.name, value: s.value, key: s.key, labelLine: { show: labelled(s) },
            itemStyle: { color: !open || open === s.key ? colour(s.key) : LINE_STRONG, decal: s.key === AWAITING ? HATCH : null },
          })),
        }],
      };
    },

    // Grouped Money in and Money out bars (Money out is Muted: spending as a whole is no Category), and Net as an Ink line.
    cashflow: (data, look, view) => {
      const { base, tooltip, pointer, legend, valueAxis, focus, INK, INK2, MUTED, CARD, colour } = look;
      const band = bands(data, look, view);
      const IN = data.in_key ? standingOff(colour(data.in_key), CARD, INK) : INK2;
      const marks = (values, side) => values.map((value, i) => ({ value, key: side ? `${data.keys[i]}:${side}` : data.keys[i] }));
      const bar = (name, values, side, color) => ({
        name, type: 'bar', cursor: 'pointer', data: marks(values, side), barMaxWidth: 22, barGap: '10%',
        itemStyle: { color, borderRadius: [4, 4, 0, 0] }, ...focus,
      });
      const line = (name, values, side, color, type) => ({
        name, type: 'line', cursor: 'pointer', data: marks(values, side), z: 3, symbol: 'circle', symbolSize: 7,
        lineStyle: { width: 2, color, type }, itemStyle: { color, borderColor: CARD, borderWidth: 2 }, ...focus,
      });
      return {
        ...base(view), legend,
        tooltip: {
          ...tooltip, trigger: 'axis', axisPointer: pointer.bar,
          formatter: ps => monthTip(data, ps, ps => table(ps[0].axisValue, ps.map(p => ({
            name: p.seriesName, colour: p.color, value: p.seriesType === 'line' ? moneySigned(p.value) : money(p.value),
          })))),
        },
        grid: { left: 4, right: 8, top: 40, bottom: 4, containLabel: true },
        xAxis: [monthAxis(data, look), ...band.xAxis], yAxis: [valueAxis, ...band.yAxis],
        series: [
          ...band.series,
          bar(data.labels.in, data.in, 'in', IN),
          bar(data.labels.out, data.out, 'out', MUTED),
          line(data.labels.net, data.net, null, INK, 'solid'),
          // Under a Member filter: what Transfers moved to (below zero) or from other Members.
          ...(data.others ? [line(data.labels.others, data.others, 'others', INK2, 'dashed')] : []),
        ],
      };
    },

    // One line per Category in its hue, points only on hover; Awaiting review dashed, as a line can't carry the hatch.
    // Clicking a Category in the legend hides its line. Points sit at month centres, so that each month is a column a
    // band can fill.
    trends: (data, look, view) => {
      const { base, tooltip, pointer, legend, valueAxis, focus, colour } = look;
      const band = bands(data, look, view);
      const lines = data.lines.map(line => line.key);
      return {
        ...base(view), legend,
        tooltip: {
          ...tooltip, trigger: 'axis', axisPointer: pointer.line,
          formatter: ps => monthTip(data, ps, ps => ranked(ps, data.words, p => lines[p.seriesIndex - band.series.length] === AWAITING)),
        },
        grid: { left: 4, right: 32, top: 40, bottom: 4, containLabel: true },
        xAxis: [monthAxis(data, look, { boundaryGap: true }), ...band.xAxis], yAxis: [valueAxis, ...band.yAxis],
        series: [...band.series, ...data.lines.map(line => ({
          name: line.name, type: 'line', cursor: 'pointer', showSymbol: false, symbol: 'circle', symbolSize: 7, ...focus,
          data: line.data.map((value, j) => ({ value, key: line.keys[j] })),
          lineStyle: { width: 2, color: colour(line.key), type: line.key === AWAITING ? 'dashed' : 'solid' }, itemStyle: { color: colour(line.key) },
        }))],
      };
    },

    // A stacked bar per Bucket, segments in Category hues and Awaiting review hatched. A Category that nets to a
    // Refund draws its segment below zero.
    per_member: (data, { base, tooltip, pointer, legend, valueAxis, categoryAxis, focus, INK, CARD, text, colour }, view) => ({
      ...base(view), legend,
      tooltip: { ...tooltip, trigger: 'axis', axisPointer: pointer.bar, formatter: ps => ranked(ps, data.words, p => data.segments[p.seriesIndex].key === AWAITING) },
      // Room for half the last axis label, which sits centred on the grid's edge.
      grid: { left: 4, right: 28, top: 40, bottom: 4, containLabel: true },
      xAxis: { ...valueAxis, splitNumber: 4 },
      yAxis: categoryAxis(data.members, { inverse: true, axisLabel: text(13, 600, INK) }),
      series: data.segments.map(segment => ({
        name: segment.name, type: 'bar', stack: 'spent', barMaxWidth: 28, cursor: 'pointer', data: segment.data, ...focus,
        itemStyle: { color: colour(segment.key), decal: segment.key === AWAITING ? HATCH : null, borderColor: CARD, borderWidth: 1.5 },
      })),
    }),

    // Income on the left, labelled to the left; Household in the middle, labelled above; the rest on the right. Each
    // node wears its Category's hue; Household is Ink 2, and what no Category names is Muted. Node names are unique
    // keys; what a node shows is its label.
    money_flow: (data, { base, tooltip, text, INK2, MUTED, colour }, view) => {
      const labels = Object.fromEntries(data.nodes.map(n => [n.name, n.label]));
      const into = data.links.filter(l => l.target === HOUSEHOLD);
      const moneyIn = into.reduce((sum, l) => sum + l.value, 0);
      const incoming = new Set(into.map(l => l.source));
      const side = n => n.name === HOUSEHOLD ? { position: 'top', distance: 6 } : incoming.has(n.name) ? { position: 'left' } : {};
      // Narrow, the labels take 11px and most of the width, and Household's (crowded between the columns) only its name.
      const size = view.narrow ? 11 : 12;
      const nameOnly = n => view.narrow && n === HOUSEHOLD ? `{name|${labels[n]}}` : null;
      return {
        ...base(view),
        tooltip: {
          ...tooltip, trigger: 'item',
          formatter: p => p.dataType === 'edge'
            ? `${html(labels[p.data.source])} → ${html(labels[p.data.target])}<br><b class="fig">${money(p.value)}</b> · ${
              html(data.words.of_money_in.replace('%(share)s', share(p.value / moneyIn)))}`
            : `${dot(p.color, p.data.category === AWAITING)}${html(labels[p.data.name])}<br><b class="fig">${money(p.value)}</b>`,
        },
        series: [{
          type: 'sankey', draggable: false, nodeAlign: 'justify', layoutIterations: 32,
          left: view.narrow ? 92 : 150, right: view.narrow ? 124 : 150, top: 28, bottom: 8, nodeGap: 10, nodeWidth: 12,
          emphasis: { focus: 'adjacency', lineStyle: { opacity: 0.6 } }, blur: { lineStyle: { opacity: 0.08 }, itemStyle: { opacity: 0.3 } },
          lineStyle: { color: 'gradient', opacity: 0.3, curveness: 0.5 }, itemStyle: { borderWidth: 0, borderRadius: 2 },
          labelLayout: { hideOverlap: true },
          label: {
            ...text(size, 500, INK2), formatter: p => nameOnly(p.data.name) ?? `{name|${labels[p.data.name]}}  {amount|${moneyWhole(p.value)}}`,
            rich: { name: text(size, 500, INK2), amount: text(size, 400, MUTED) },
          },
          // Built afresh, as a node's `label` would be read as its label's style.
          data: data.nodes.map(n => ({
            name: n.name, key: n.key, category: n.category, cursor: n.key ? 'pointer' : 'default', label: side(n),
            itemStyle: { color: n.category ? colour(n.category) : n.name === HOUSEHOLD ? INK2 : MUTED, decal: n.category === AWAITING ? HATCH : null },
          })),
          links: data.links,
        }],
      };
    },
  };

  const observers = new WeakMap();

  const dataOf = el => JSON.parse(document.getElementById(el.dataset.source).textContent);
  // ECharts has no live theme switch, and a narrow chart lays out differently: rebuild the options from the tokens.
  const build = (chart, el, animate = false) => chart.setOption(
    options[el.dataset.chart](dataOf(el), theme(), { narrow: el.clientWidth < 420, width: el.clientWidth, open: el.dataset.open, animate, label: el.getAttribute('aria-label') }),
    { notMerge: true },
  );
  // `quiet` for the numbers refetched after an outcome changed: the same view, so its donut doesn't sweep in again.
  const mount = (el, quiet = false) => {
    // A page restored from history has the element but not its chart.
    if (echarts.getInstanceByDom(el)) return;
    const data = dataOf(el);
    const chart = echarts.init(el, null, { renderer: 'svg' });
    el.dataset.open = openMark() || '';
    build(chart, el, !quiet);
    // Every mark that names Transactions carries its key: a bar, a point, a segment or a Sankey node.
    // The open Category's segment closes it again, as its row does.
    chart.on('click', p => {
      if (!p.data?.key) return;
      if (p.data.key === openMark()) close();
      else htmx.ajax('GET', data.drill + encodeURIComponent(p.data.key), '#drill');
    });
    if (el.dataset.chart === 'spending') {
      chart.on('mouseover', p => light(p.data.key, true));
      chart.on('mouseout', p => light(p.data.key, false));
    }
    // Only a change of size: the first observation would cut the sweep short.
    let size = `${el.clientWidth}x${el.clientHeight}`;
    const observer = new ResizeObserver(() => {
      const now = `${el.clientWidth}x${el.clientHeight}`;
      if (now === size) return;
      size = now;
      chart.resize();
      build(chart, el);
    });
    observer.observe(el);
    observers.set(el, observer);
  };
  const unmount = el => {
    observers.get(el)?.disconnect();
    echarts.getInstanceByDom(el)?.dispose();
  };
  const charts = root => root.querySelectorAll('[data-chart]');

  // ---- Spending: the donut, the Category list and the drill-down in step ----
  const donut = () => document.querySelector('[data-chart="spending"]');
  const categories = () => document.querySelectorAll('.cats .cat');
  const openMark = () => document.querySelector('#drill .drill-card')?.dataset.mark;

  // A Category hovered or focused, in the list or on the donut: its row and segment light up, and the centre shows it.
  const light = (key, on) => {
    const el = donut();
    let named;
    categories().forEach(row => {
      const me = on && row.dataset.key === key;
      row.classList.toggle('hot', me);
      if (me) named = row;
    });
    const chart = el && echarts.getInstanceByDom(el);
    if (chart) {
      const index = dataOf(el).segments.findIndex(s => s.key === key);
      if (index >= 0) chart.dispatchAction({ type: on ? 'highlight' : 'downplay', seriesIndex: 0, dataIndex: index });
    }
    const value = document.querySelector('[data-centre-value]'), name = document.querySelector('[data-centre-name]');
    if (!value) return;
    value.dataset.total ??= value.textContent;
    name.dataset.total ??= name.textContent;
    value.textContent = named ? named.querySelector('.amt').textContent : value.dataset.total;
    name.textContent = named ? named.querySelector('.cat-open').textContent : name.dataset.total;
  };

  // The drill-down's Category is the open one: its row takes the wash and shows its Subcategories, and the donut
  // dims the others.
  const follow = () => {
    const key = openMark();
    categories().forEach(row => {
      const open = row.dataset.key === key;
      row.classList.toggle('open', open);
      row.querySelector('.cat-open')?.setAttribute('aria-expanded', open);
      const subs = row.querySelector('.subs');
      if (subs) subs.hidden = !open;
    });
    const el = donut(), chart = el && echarts.getInstanceByDom(el);
    if (chart && el.dataset.open !== (key || '')) {
      el.dataset.open = key || '';
      build(chart, el);
    }
  };

  // Closing the drill-down gives focus back to what opened it, or else to its Category's row.
  let opener;
  const close = () => {
    const drill = document.getElementById('drill');
    const key = openMark();
    drill.replaceChildren();
    follow();
    const row = [...categories()].find(r => r.dataset.key === key)?.querySelector('.cat-open');
    (opener?.isConnected ? opener : row)?.focus();
  };

  document.addEventListener('click', e => {
    if (e.target.closest('#drill [data-close]')) close();
    const control = e.target.closest('[aria-controls="drill"]');
    if (!control) return;
    // An open Category closes again, rather than reloading (captured, so that HTMX never sends it).
    if (control.getAttribute('aria-expanded') === 'true') {
      e.preventDefault();
      e.stopPropagation();
      opener = control;
      close();
    } else {
      opener = control;
    }
  }, true);
  for (const [type, on] of [['mouseover', true], ['mouseout', false], ['focusin', true], ['focusout', false]]) {
    document.addEventListener(type, e => {
      const row = e.target.closest?.('.cats .cat');
      // Moving within a row neither lights nor unlights it.
      if (!row || row.contains(e.relatedTarget)) return;
      light(row.dataset.key, on);
    });
  }
  // The header line's "and 2 more" expands the rest of its Accounts in place, and focus moves on to the first of them.
  document.addEventListener('click', e => {
    const more = e.target.closest('.completeness [data-more]');
    if (!more) return;
    const wrap = more.parentElement, rest = wrap.nextElementSibling;
    rest.hidden = false;
    wrap.remove();
    rest.querySelector('a')?.focus();
  });
  document.addEventListener('keydown', e => {
    // From the drill-down, or from the list or table that opened it.
    const from = document.activeElement;
    if (e.key === 'Escape' && openMark() && from.closest('#drill, .cats, .view-table')) close();
  });

  document.addEventListener('DOMContentLoaded', () => charts(document).forEach(el => mount(el)));
  // Not for a failed response, which keeps the old content and its charts (swap.js).
  document.addEventListener('htmx:beforeSwap', e => { if (e.detail.shouldSwap) charts(e.detail.target).forEach(unmount); });
  // A view swapped in brings the sidebar's view links along, marking its own as current.
  document.addEventListener('htmx:afterSettle', e => {
    const quiet = e.detail.elt.id === 'numbers';
    charts(e.detail.elt).forEach(el => mount(el, quiet));
    follow();
  });
  document.addEventListener('htmx:historyRestore', () => { charts(document).forEach(el => mount(el)); follow(); });
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
