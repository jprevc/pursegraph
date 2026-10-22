# ECharts custom build

`echarts.min.js` is Apache ECharts **5.6.0** built with only what the Dashboard draws (`static/dashboard.js`), rather than the full bundle: 569 KB (197 KB gzipped) instead of 1.03 MB (335 KB gzipped). It is built once and vendored; nothing builds it at runtime.

Stay on 5.6.0 unless upgrading is deliberate: the theme switch relies on `setOption(…, { notMerge: true })` (issue #65).

## What it registers

- **Charts:** bar, line, pie (the Spending donut), sankey (Money flow).
- **Components:** grid (with the axes), tooltip (with the axis pointer), legend (plain and scroll), aria (chart labels and the decal Awaiting review's hatch uses; decals themselves are in core).
- **Features:** label layout, for the Sankey's `labelLayout.hideOverlap`.
- **Renderer:** SVG only; `dashboard.js` inits every chart with `renderer: 'svg'`.

A chart type or component the Dashboard starts using must be added here and the bundle rebuilt; `tests/test_dashboard.py` checks the chart types.

## Rebuild

From the repository root, with Node:

```sh
mkdir -p /tmp/echarts-build && cd /tmp/echarts-build
npm init -y >/dev/null
npm install --no-audit --no-fund echarts@5.6.0 esbuild@0.24.2
cat > entry.js <<'EOF'
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart, SankeyChart } from 'echarts/charts';
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { LabelLayout } from 'echarts/features';
import { SVGRenderer } from 'echarts/renderers';

echarts.use([BarChart, LineChart, PieChart, SankeyChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, LabelLayout, SVGRenderer]);

export * from 'echarts/core';
EOF
npx esbuild entry.js --bundle --minify --format=iife --global-name=echarts --target=es2017 \
  --define:process.env.NODE_ENV='"production"' \
  --banner:js='/*! Apache ECharts 5.6.0 (Apache-2.0), custom build: see static/vendor/echarts.md */' \
  --outfile="$OLDPWD/static/vendor/echarts.min.js"
```

`export * from 'echarts/core'` keeps the global `echarts` the full bundle had: `init`, `getInstanceByDom`, `format.encodeHTML`.
