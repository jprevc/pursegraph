// Mounts the dashboard's ECharts charts: on page load, and whenever HTMX swaps a view in.
// Each chart reads its data from the JSON script named by `data-source`; clicking a mark loads its Transactions into #drill.
// Colours come from the CSS tokens, so a chart is rebuilt on `themechange` (static/theme.js).
// On Spending, the donut and the Category list light each other's Category, and the drill-down's Category is the
// open one in both: #drill's card names it (`data-mark`), so whatever opens or closes it, they follow.
(() => {
  const AWAITING = 'awaiting';
  const { money, moneyWhole, moneySigned, share } = window.Figures;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  // Awaiting review's hatch (the Neutral Wait Rule): 45° white stripes at 45 %.
  const HATCH = { symbol: 'rect', dashArrayX: [1, 0], dashArrayY: [3, 3], rotation: Math.PI / 4, color: 'rgba(255, 255, 255, .45)' };
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
    // The donut: segments labelled directly (only those of 5 % or more when narrow), Awaiting review hatched and
    // unlabelled, and every segment but the open Category's dimmed while one is open. It sweeps in once.
    spending: (data, { TEXT, tooltip, INK2, LINE_STRONG, colour }, { narrow, open, animate }) => {
      const total = data.total;
      const labelled = s => s.key !== AWAITING && (!narrow || s.value / total >= 0.05);
      const html = echarts.format.encodeHTML;
      return {
        textStyle: TEXT,
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
  const build = (chart, el, animate = false) => chart.setOption(
    options[el.dataset.chart](dataOf(el), theme(), { narrow: el.clientWidth < 420, open: el.dataset.open, animate }),
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
