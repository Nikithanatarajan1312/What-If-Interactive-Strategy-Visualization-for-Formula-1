<script setup>
import { ref, watch } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'

const store = useRaceStore()
const container = ref(null)
const tooltip = useTooltip()

/**
 * Bar fills use the same tokens as `.delta-legend__swatch` (see scoped CSS + main.css).
 */
const COLOR_PIT = 'var(--color-danger)'
const COLOR_TYRE = 'var(--color-warning)'
const COLOR_TRAFFIC = '#818cf8'
const COLOR_NET = 'var(--color-accent)'
const COLOR_NET_STROKE = 'rgba(255, 255, 255, 0.22)'

const margin = { top: 8, right: 8, bottom: 58, left: 6 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

// Full D3 redraw only when breakdown inputs change. Do NOT watch `highlightedDriver` — pit
// heatmap / controls set it on hover, which would re-run this watch and wipe/redraw the SVG
// (visible jitter). Use separate getters (not a fresh object literal) so Vue compares by ref.
watch(
  [
    () => store.activeDrivers,
    () => store.strategyViz,
    () => store.simDelta,
    () => store.showSimulated,
    () => store.simulatedData,
  ],
  () => {
    redraw()
  }
)

function breakdownForDriver(code, viz) {
  if (!viz) return null
  const k = String(code).toUpperCase()
  return viz[k] || viz[code] || null
}

function formatGainSeconds(v) {
  if (v > 0) return `+${v.toFixed(1)}s`
  if (v < 0) return `${v.toFixed(1)}s`
  return '0.0s'
}

function rowMeta(backendLabel) {
  const L = String(backendLabel || '').toLowerCase()
  if (L.includes('pit'))
    return { display: 'Pit timing', fill: COLOR_PIT, key: 'pit' }
  if (L.includes('pace') || L.includes('tyre'))
    return { display: 'Tyre / pace', fill: COLOR_TYRE, key: 'tyre' }
  if (L.includes('traffic'))
    return { display: 'Traffic / rejoin', fill: COLOR_TRAFFIC, key: 'traffic' }
  return { display: backendLabel || 'Effect', fill: 'var(--color-text-secondary)', key: 'other' }
}

const ROW_ORDER = ['pit', 'tyre', 'traffic', 'other']

function orderedComponents(comps) {
  return [...comps].sort((a, b) => {
    const ka = rowMeta(a.label).key
    const kb = rowMeta(b.label).key
    const ia = ROW_ORDER.indexOf(ka) >= 0 ? ROW_ORDER.indexOf(ka) : 99
    const ib = ROW_ORDER.indexOf(kb) >= 0 ? ROW_ORDER.indexOf(kb) : 99
    return ia - ib
  })
}

/** One tooltip per driver: compact lines, signed seconds (matches legend wording). */
function tooltipCompact(delta, showDriverTitle) {
  const lines = orderedComponents(delta.components).map((c) => {
    const meta = rowMeta(c.label)
    return `<div style="display:flex;justify-content:space-between;gap:12px;font-variant-numeric:tabular-nums;"><span style="color:#9aa3b2;">${meta.display}</span><span style="font-weight:700;color:#e8eaef;">${formatGainSeconds(c.value)}</span></div>`
  })
  lines.push(
    `<div style="display:flex;justify-content:space-between;gap:12px;margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.12);font-variant-numeric:tabular-nums;"><span style="font-weight:700;color:var(--color-accent-text,#ff3b33);">Net vs actual</span><span style="font-weight:800;color:#fff;">${formatGainSeconds(delta.total)}</span></div>`
  )
  const head = showDriverTitle
    ? `<div style="font-size:10px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#9aa3b2;margin-bottom:8px;">${delta.driver}</div>`
    : ''
  return `<div style="font-family:system-ui,-apple-system,sans-serif;font-size:12px;line-height:1.55;color:#e8eaef;min-width:200px;">
    ${head}
    ${lines.join('')}
  </div>`
}

function draw() {
  const g = getG()
  const svg = getSvg()
  const w = width.value
  const h = height.value
  if (!g || !svg || w <= 0 || h <= 0) return

  svg.attr('role', 'img').attr(
    'aria-label',
    'Delta breakdown: diverging bars by pit timing, tyre, traffic, and net versus actual finish.'
  )

  const drivers = store.activeDrivers
  if (!drivers.length) return

  const showSim = store.showSimulated && store.simulatedData
  const simCode = store.modifiedStrategy?.driverCode
  const db = store.strategyViz?.delta_breakdown

  const deltas = drivers
    .map((d) => {
      const bd = breakdownForDriver(d.code, db)
      if (!bd?.components || bd.total == null || Math.abs(bd.total) <= 0.05) return null
      return {
        driver: d.code,
        color: d.color,
        components: bd.components,
        total: bd.total,
      }
    })
    .filter(Boolean)

  let simDeltas = []
  if (showSim && simCode && store.simDelta?.code === simCode) {
    const simDriver = store.simulatedData.drivers?.find((d) => d.code === simCode)
    const sd = store.simDelta
    if (simDriver && sd?.components) {
      simDeltas = [
        {
          driver: `${simCode} (sim)`,
          color: simDriver.color,
          components: sd.components,
          total: sd.total,
          isSim: true,
          origCode: simCode,
        },
      ]
    }
  }

  const allDeltas = [...deltas, ...simDeltas]

  if (!allDeltas.length) {
    const msg = !store.strategyViz && store.raceData
      ? 'Loading strategy model…'
      : 'No breakdown — select drivers behind the leader'
    g.append('text')
      .attr('x', w / 2)
      .attr('y', h / 2)
      .attr('text-anchor', 'middle')
      .style('fill', 'var(--color-text-muted)')
      .style('font-size', '15px')
      .style('font-family', 'var(--font-body)')
      .text(msg)
    return
  }

  const AXIS_H = 52
  const plotH = Math.max(40, h - AXIS_H)
  const plotPadY = 8

  const barX0 = 4
  const barRegionW = Math.max(48, w - barX0 - 6)
  const xAxisPad = Math.min(5, Math.max(1, barRegionW * 0.018))

  let maxAbs = 1e-6
  for (const d of allDeltas) {
    maxAbs = Math.max(maxAbs, Math.abs(d.total))
    for (const c of d.components) maxAbs = Math.max(maxAbs, Math.abs(c.value))
  }
  maxAbs *= 1.02

  const r0 = barX0 + xAxisPad
  const r1 = barX0 + barRegionW - xAxisPad
  const x = d3.scaleLinear().domain([-maxAbs, maxAbs]).range(r1 > r0 ? [r0, r1] : [r0, r0 + 1])
  const x0 = x(0)

  const yBand = d3
    .scaleBand()
    .domain(allDeltas.map((d) => d.driver))
    .range([plotPadY, plotH - plotPadY])
    .padding(0.02)

  g.append('g')
    .attr('class', 'axis delta-axis')
    .attr('transform', `translate(0,${plotH})`)
    .call(
      d3
        .axisBottom(x)
        .ticks(6)
        .tickSizeOuter(0)
        .tickFormat((d) => `${d >= 0 ? '+' : ''}${Number(d).toFixed(1)}s`)
    )
    .call((sel) => {
      sel.selectAll('text').attr('font-size', 11).attr('dy', '0.71em').attr('font-family', 'var(--font-display)').attr('fill', 'var(--color-text-secondary)')
      sel.selectAll('path,line').attr('stroke', 'var(--color-border)')
    })

  g.append('text')
    .attr('x', barX0 + barRegionW / 2)
    .attr('y', plotH + 42)
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'hanging')
    .style('font-size', '10px')
    .style('fill', 'var(--color-text-muted)')
    .style('font-family', 'var(--font-body)')
    .text('Seconds vs actual at finish (center = 0)')

  allDeltas.forEach((delta) => {
    const isSim = delta.isSim
    const matchCode = isSim ? delta.origCode : delta.driver

    const yBlock = yBand(delta.driver)
    const bh = yBand.bandwidth()
    const padBottom = 2
    const driverHeaderH = allDeltas.length > 1 ? 20 : 12
    const comps = orderedComponents(delta.components)
    const nRows = comps.length + 1
    const rowArea = Math.max(0, bh - driverHeaderH - padBottom)
    const rowGutter = 14
    const laneH =
      nRows > 0 ? Math.max(0, (rowArea - rowGutter * Math.max(0, nRows - 1)) / nRows) : 0
    // Match StintBar: stint rects use full row bandwidth (`height === bh`). Fill each delta lane
    // the same way (one px inset so strokes don’t clip between gutters).
    const barH = laneH > 2 ? laneH - 1 : Math.max(4, laneH)
    const netBarH = laneH > 2 ? laneH - 1 : Math.max(4, laneH)

    g.append('rect')
      .attr('x', 0)
      .attr('y', yBlock)
      .attr('width', w)
      .attr('height', bh)
      .attr('rx', 10)
      .attr('fill', 'rgba(255,255,255,0.03)')
      .attr('stroke', 'rgba(255,255,255,0.06)')
      .attr('opacity', 1)

    g.append('text')
      .attr('x', 6)
      .attr('y', yBlock + driverHeaderH / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', 'start')
      .style('font-size', '13px')
      .style('font-weight', '800')
      .style('font-family', 'var(--font-display)')
      .style('fill', delta.color)
      .style('opacity', 1)
      .style('font-style', isSim ? 'italic' : 'normal')
      .text(delta.driver)

    function drawRowBar(centerY, v, meta, opts = {}) {
      const thick = opts.net ? netBarH : barH
      const fill = opts.net ? COLOR_NET : meta.fill
      const xL = x(Math.min(0, v))
      const xR = x(Math.max(0, v))
      const wid = Math.max(v === 0 ? 3 : 2, xR - xL)

      const label = formatGainSeconds(v)
      const barTitle = opts.net ? 'Net vs actual' : meta.display
      const bar = g
        .append('rect')
        .attr('x', xL)
        .attr('y', centerY - thick / 2)
        .attr('width', wid)
        .attr('height', thick)
        .attr('rx', 0)
        .attr('ry', 0)
        .attr('fill', fill)
        .attr('fill-opacity', opts.net ? 0.95 : 0.9)
        .attr('stroke', opts.net ? COLOR_NET_STROKE : 'rgba(255,255,255,0.14)')
        .attr('stroke-width', opts.net ? 2 : 1)
        .style('cursor', 'pointer')
        .style('opacity', 1)
      bar.append('title').text(`${barTitle}: ${label}`)

      bar
        .on('mouseover', (event) => {
          tooltip.show(tooltipCompact(delta, allDeltas.length > 1))
          tooltip.move(event)
          store.setHighlightedDriver(matchCode)
        })
        .on('mousemove', (event) => tooltip.move(event))
        .on('mouseout', () => {
          tooltip.hide()
          store.setHighlightedDriver(null)
        })
      const inset = 6
      let tx
      let anchor
      let tFill
      const tyreInside = meta.key === 'tyre' ? '#1a1d26' : '#fff'
      if (Math.abs(v) < 1e-9) {
        tx = x0
        anchor = 'middle'
        tFill = opts.net ? '#fff' : 'var(--color-text)'
      } else if (wid < inset * 2 + 4) {
        tx = (xL + xR) / 2
        anchor = 'middle'
        tFill = opts.net ? '#fff' : tyreInside
      } else if (v > 0) {
        tx = xR - inset
        anchor = 'end'
        tFill = opts.net ? '#fff' : tyreInside
      } else {
        tx = xL + inset
        anchor = 'start'
        tFill = opts.net ? '#fff' : tyreInside
      }

      const valueFontPx = 13

      g.append('text')
        .attr('x', tx)
        .attr('y', centerY)
        .attr('dy', '0.35em')
        .attr('text-anchor', anchor)
        .style('font-size', `${valueFontPx}px`)
        .style('font-weight', '600')
        .style('font-family', 'var(--font-display)')
        .style('font-variant-numeric', 'tabular-nums')
        .style('fill', tFill)
        .style('opacity', 1)
        .style('pointer-events', 'none')
        .style('paint-order', 'stroke fill')
        .style('stroke', 'rgba(0,0,0,0.35)')
        .style('stroke-width', 1.25)
        .text(label)
    }

    const firstRowTop = yBlock + driverHeaderH
    function rowCenterY(i) {
      return firstRowTop + laneH / 2 + i * (laneH + rowGutter)
    }
    comps.forEach((comp, i) => {
      const meta = rowMeta(comp.label)
      const rowY = rowCenterY(i)
      drawRowBar(rowY, comp.value, meta, {})
    })

    const netRowY = rowCenterY(comps.length)
    drawRowBar(netRowY, delta.total, { display: 'Net', fill: COLOR_NET, key: 'net' }, { net: true })
  })

  g.append('line')
    .attr('x1', x0)
    .attr('x2', x0)
    .attr('y1', plotPadY)
    .attr('y2', plotH - plotPadY)
    .attr('stroke', 'var(--color-text)')
    .attr('stroke-width', 1.25)
    .attr('opacity', 0.5)
    .style('pointer-events', 'none')
}
</script>

<template>
  <div class="delta-breakdown">
    <h3 class="panel-title">Delta Breakdown</h3>
    <p v-if="store.raceData && store.strategyViz" class="delta-subtitle">
      Sim vs actual at the flag; each row vs zero at finish.
    </p>
    <ul v-if="store.raceData && store.strategyViz" class="delta-legend" aria-label="Component colors">
      <li><span class="delta-legend__swatch delta-legend__swatch--pit"></span> Pit timing</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--tyre"></span> Tyre / pace</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--traffic"></span> Traffic / rejoin</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--net"></span> Net vs actual</li>
    </ul>
    <div
      ref="container"
      class="chart-container"
      role="figure"
      aria-label="Diverging delta breakdown chart"
    >
      <p v-if="!store.raceData" class="placeholder">Select a race to see the delta breakdown</p>
    </div>
  </div>
</template>

<style scoped>
.delta-breakdown {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  overflow: hidden;
}

.panel-title {
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text);
  margin: 0 0 var(--space-1) 0;
  flex-shrink: 0;
}

.delta-subtitle {
  margin: 0 0 var(--space-2) 0;
  font-size: var(--text-xs);
  line-height: 1.35;
  color: var(--color-text-secondary);
  font-family: var(--font-body);
  max-width: 100%;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  flex-shrink: 0;
}

.delta-legend {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: var(--space-2) var(--space-3);
  list-style: none;
  margin: 0 0 var(--space-1) 0;
  padding: 0;
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text);
  flex-shrink: 0;
  max-height: 2rem;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.delta-legend li {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.delta-legend__swatch {
  width: 12px;
  height: 12px;
  border-radius: 4px;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
}

.delta-legend__swatch--pit {
  background: var(--color-danger);
}

.delta-legend__swatch--tyre {
  background: var(--color-warning);
}

.delta-legend__swatch--traffic {
  background: #818cf8;
}

.delta-legend__swatch--net {
  background: var(--color-accent);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.15), 0 2px 6px rgba(0, 0, 0, 0.4);
}

.chart-container {
  flex: 1 1 0;
  position: relative;
  min-height: 0;
  min-width: 0;
  max-height: 100%;
  overflow: hidden;
  contain: strict;
}

.chart-container :deep(svg) {
  display: block;
  max-width: 100%;
  /* Height/width set in px by useChart from container — do not override or layout can fight flex. */
}

.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: var(--text-base);
  text-align: center;
  padding: var(--space-4);
}
</style>
