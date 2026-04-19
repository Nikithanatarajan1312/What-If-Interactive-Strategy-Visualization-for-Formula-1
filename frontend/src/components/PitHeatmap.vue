<script setup>
import { ref, watch } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'

const store = useRaceStore()
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 16, bottom: 36, left: 52 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [store.activeDrivers, store.strategyViz, store.hoveredLap, store.brushedLapRange, store.highlightedDriver, store.simulatedData, store.showSimulated],
  () => { redraw() },
  { deep: true }
)

/** Pit-window cells from ``POST /api/strategy-viz`` (same model as delta breakdown). */
function pitWindowCellsForDrivers(drivers) {
  const pw = store.strategyViz?.pit_window
  if (!pw) return []
  const out = []
  for (const d of drivers) {
    const key = d.code?.toUpperCase?.() || String(d.code)
    const rows = pw[key] || pw[d.code]
    if (!rows?.length) continue
    for (const cell of rows) {
      out.push({ lap: cell.lap, driver: d.code, value: cell.value })
    }
  }
  return out
}

function draw() {
  const g = getG()
  const svg = getSvg()
  const w = width.value
  const h = height.value
  if (!g || !svg || w <= 0 || h <= 0) return

  svg.attr('role', 'img')
    .attr('aria-label', 'Pit window heatmap. Green means pitting gains time, red means pitting loses time.')

  const drivers = store.activeDrivers
  if (!drivers.length) return

  const allCells = pitWindowCellsForDrivers(drivers)
  if (!allCells.length) return

  const brushRange = store.brushedLapRange
  const highlighted = store.highlightedDriver

  const filteredCells = brushRange
    ? allCells.filter(c => c.lap >= brushRange[0] && c.lap <= brushRange[1])
    : allCells

  const laps = [...new Set(filteredCells.map(c => c.lap))].sort((a, b) => a - b)
  const driverCodes = drivers.map(d => d.code)
  if (!laps.length) return

  const cellW = Math.max(2, w / laps.length)
  const cellH = Math.max(8, Math.min(28, (h - 10) / driverCodes.length - 4))

  const x = d3.scaleLinear()
    .domain([d3.min(laps), d3.max(laps)])
    .range([0, w - cellW])
  const yBand = d3.scaleBand()
    .domain(driverCodes).range([0, h]).padding(0.15)

  const maxAbsRaw = d3.max(filteredCells, c => Math.abs(c.value)) || 0
  const maxAbs = Math.max(1, Math.min(6, maxAbsRaw))
  const colorScale = d3.scaleDiverging()
    .domain([-maxAbs, 0, maxAbs])
    .interpolator(d3.interpolateRgbBasis(['#c6423a', '#f6f1df', '#2f8f4e']))

  g.append('g').attr('class', 'axis')
    .attr('transform', `translate(${cellW / 2},${h})`)
    .call(d3.axisBottom(x).ticks(Math.min(w / 60, 15)).tickFormat(d => `L${d}`))

  driverCodes.forEach(code => {
    const driver = drivers.find(d => d.code === code)
    g.append('text').attr('x', -8)
      .attr('y', yBand(code) + yBand.bandwidth() / 2)
      .attr('dy', '0.35em').attr('text-anchor', 'end')
      .style('font-size', 'var(--text-xs)').style('font-weight', '700')
      .style('font-family', 'var(--font-display)')
      .style('fill', driver?.color || 'var(--color-text)')
      .style('opacity', highlighted && highlighted !== code ? 0.3 : 1)
      .text(code)
  })

  filteredCells.forEach(cell => {
    const cx = x(cell.lap)
    const cy = yBand(cell.driver)
    if (cy == null) return

    const dimmed = highlighted && highlighted !== cell.driver

    const valueClamped = Math.max(-maxAbs, Math.min(maxAbs, cell.value))
    g.append('rect')
      .attr('x', cx).attr('y', cy)
      .attr('width', cellW).attr('height', yBand.bandwidth())
      .attr('fill', colorScale(valueClamped)).attr('rx', 1)
      .attr('opacity', dimmed ? 0.15 : 1)
      .on('mouseover', (event) => {
        const sign = cell.value >= 0 ? '+' : ''
        const label = cell.value >= 0 ? 'Pit gain' : 'Pit loss'
        tooltip.show(`<strong>${cell.driver}</strong> Lap ${cell.lap}<br/>
          ${label}: <span style="color:${cell.value >= 0 ? 'var(--color-success)' : 'var(--color-danger)'}; font-weight:700">${sign}${cell.value.toFixed(1)}s</span>`)
        tooltip.move(event)
        store.setHighlightedDriver(cell.driver)
      })
      .on('mousemove', (event) => tooltip.move(event))
      .on('mouseout', () => {
        tooltip.hide()
        store.setHighlightedDriver(null)
      })
  })

  if (store.showSimulated && store.simulatedData) {
    const simCode = store.modifiedStrategy?.driverCode
    const simDriver = store.simulatedData.drivers?.find(d => d.code === simCode)
    if (simDriver && yBand(simCode) != null) {
      const simY = yBand(simCode) + yBand.bandwidth() / 2

      simDriver.pitStops.forEach(pit => {
        if (pit.lap >= d3.min(laps) && pit.lap <= d3.max(laps)) {
          g.append('line')
            .attr('x1', x(pit.lap) + cellW / 2).attr('x2', x(pit.lap) + cellW / 2)
            .attr('y1', yBand(simCode) - 2).attr('y2', yBand(simCode) + yBand.bandwidth() + 2)
            .attr('stroke', '#fff').attr('stroke-width', 2)
            .attr('stroke-dasharray', '4,2')

          g.append('circle')
            .attr('cx', x(pit.lap) + cellW / 2).attr('cy', yBand(simCode) - 4)
            .attr('r', 4).attr('fill', 'var(--color-accent)')
            .attr('stroke', '#fff').attr('stroke-width', 1.5)

          g.append('text')
            .attr('x', x(pit.lap) + cellW / 2).attr('y', yBand(simCode) - 10)
            .attr('text-anchor', 'middle')
            .style('font-size', '8px').style('font-weight', '700')
            .style('font-family', 'var(--font-display)')
            .style('fill', 'var(--color-accent-text, #ff3333)')
            .text('SIM')
        }
      })
    }
  }

  if (store.hoveredLap != null) {
    const hLap = store.hoveredLap
    if (hLap >= d3.min(laps) && hLap <= d3.max(laps)) {
      const hx = x(hLap) + cellW / 2
      g.append('line')
        .attr('x1', hx).attr('x2', hx).attr('y1', 0).attr('y2', h)
        .attr('stroke', 'var(--color-text-muted)').attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,3').attr('opacity', 0.5)
    }
  }

  const legendW = Math.min(120, w * 0.25)
  const legendH = 8
  const defs = g.append('defs')
  const gradientId = 'heatmap-gradient'
  const gradient = defs.append('linearGradient').attr('id', gradientId)
  gradient.append('stop').attr('offset', '0%').attr('stop-color', colorScale(-maxAbs))
  gradient.append('stop').attr('offset', '50%').attr('stop-color', colorScale(0))
  gradient.append('stop').attr('offset', '100%').attr('stop-color', colorScale(maxAbs))

  g.append('rect')
    .attr('x', w - legendW).attr('y', -12)
    .attr('width', legendW).attr('height', legendH).attr('rx', 2)
    .attr('fill', `url(#${gradientId})`)
  g.append('text').attr('x', w - legendW).attr('y', -14)
    .style('font-size', '9px').style('fill', 'var(--color-text-secondary)')
    .style('font-family', 'var(--font-display)').style('font-weight', '600')
    .text('Loss')
  g.append('text').attr('x', w).attr('y', -14).attr('text-anchor', 'end')
    .style('font-size', '9px').style('fill', 'var(--color-text-secondary)')
    .style('font-family', 'var(--font-display)').style('font-weight', '600')
    .text('Gain')
}
</script>

<template>
  <div class="pit-heatmap">
    <h3 class="panel-title">Pit Window <span class="panel-title__sub">Heatmap</span></h3>
    <div ref="container" class="chart-container" role="figure" aria-label="Pit window gain/loss heatmap">
      <p class="placeholder" v-if="!store.raceData">Select a race to view pit windows</p>
      <p class="placeholder" v-else-if="store.raceData && !store.strategyViz">Loading strategy model…</p>
    </div>
  </div>
</template>

<style scoped>
.pit-heatmap {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text);
  margin: 0 0 var(--space-2) 0;
}

.panel-title__sub {
  font-weight: 400;
  color: var(--color-text-muted);
}

.chart-container {
  flex: 1;
  position: relative;
  min-height: 0;
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
}
</style>
