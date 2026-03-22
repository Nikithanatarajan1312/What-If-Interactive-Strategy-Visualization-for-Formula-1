<script setup>
import { ref, watch } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'

const COMPOUND_COLORS = {
  SOFT: '#ff3333',
  MEDIUM: '#ffd700',
  HARD: '#e8e8e8',
  INTERMEDIATE: '#3cc54e',
  WET: '#3388ee',
}

const store = useRaceStore()
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 24, bottom: 36, left: 52 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [store.activeDrivers, store.hoveredLap, store.modifiedStrategy, store.simulatedData, store.showSimulated],
  () => { redraw() },
  { deep: true }
)

function getDriverStrategy(driver) {
  if (store.modifiedStrategy && store.modifiedStrategy.driverCode === driver.code) {
    return store.modifiedStrategy.pitStops
  }
  return driver.pitStops
}

function buildStints(driver, pitStops, totalLaps) {
  const stints = []
  let stintStart = 1

  for (const pit of pitStops) {
    const startLapData = driver.laps.find(l => l.lap === stintStart)
    stints.push({
      startLap: stintStart,
      endLap: pit.lap - 1,
      compound: pit.fromCompound || startLapData?.compound || 'MEDIUM',
    })
    stintStart = pit.lap
  }

  const lastPit = pitStops[pitStops.length - 1]
  stints.push({
    startLap: stintStart,
    endLap: totalLaps,
    compound: lastPit?.toCompound || driver.laps.find(l => l.lap === stintStart)?.compound || 'HARD',
  })

  return stints
}

function draw() {
  const g = getG()
  const svg = getSvg()
  const w = width.value
  const h = height.value
  if (!g || !svg || w <= 0 || h <= 0) return

  svg.attr('role', 'img')
    .attr('aria-label', 'Stint history showing tyre strategies. Drag pit markers to modify strategy.')

  const drivers = store.activeDrivers
  if (!drivers.length) return

  const totalLaps = store.totalLaps || d3.max(drivers.flatMap(d => d.laps), l => l.lap)

  const x = d3.scaleLinear().domain([1, totalLaps]).range([0, w])
  const yBand = d3.scaleBand()
    .domain(drivers.map(d => d.code)).range([0, h]).padding(0.25)

  g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(Math.min(w / 60, 20)).tickFormat(d => `L${d}`))
  g.append('g').attr('class', 'grid').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).tickSize(-h).tickFormat(''))

  drivers.forEach(driver => {
    const pitStops = getDriverStrategy(driver)
    const stints = buildStints(driver, pitStops, totalLaps)
    const yPos = yBand(driver.code)
    const bh = yBand.bandwidth()
    const isModified = store.modifiedStrategy?.driverCode === driver.code

    g.append('text')
      .attr('x', -8).attr('y', yPos + bh / 2).attr('dy', '0.35em')
      .attr('text-anchor', 'end')
      .style('font-size', 'var(--text-xs)').style('font-weight', '700')
      .style('font-family', 'var(--font-display)')
      .style('fill', driver.color)
      .text(driver.code + (isModified ? ' ●' : ''))

    stints.forEach(stint => {
      const sx = x(stint.startLap)
      const ex = x(stint.endLap)
      const bw = Math.max(2, ex - sx)

      g.append('rect')
        .attr('x', sx).attr('y', yPos)
        .attr('width', bw).attr('height', bh).attr('rx', 3)
        .attr('fill', COMPOUND_COLORS[stint.compound] || '#888')
        .attr('fill-opacity', isModified ? 0.9 : 0.75)
        .attr('stroke', isModified ? '#fff' : driver.color)
        .attr('stroke-width', isModified ? 1.5 : 1)
        .attr('stroke-dasharray', isModified ? '4,2' : 'none')
        .on('mouseover', (event) => {
          tooltip.show(`<strong style="color:${driver.color}">${driver.code}</strong>
            ${isModified ? '<em>(modified)</em>' : ''}<br/>
            ${stint.compound} · Laps ${stint.startLap}–${stint.endLap}
            (${stint.endLap - stint.startLap + 1} laps)`)
          tooltip.move(event)
        })
        .on('mousemove', (event) => tooltip.move(event))
        .on('mouseout', () => tooltip.hide())

      if (bw > 40) {
        g.append('text')
          .attr('x', sx + bw / 2).attr('y', yPos + bh / 2).attr('dy', '0.35em')
          .attr('text-anchor', 'middle')
          .style('font-size', '9px').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', '#1a1a1a')
          .style('pointer-events', 'none').text(stint.compound[0])
      }
    })

    pitStops.forEach((pit, pitIdx) => {
      const px = x(pit.lap)

      g.append('line')
        .attr('x1', px).attr('x2', px)
        .attr('y1', yPos - 2).attr('y2', yPos + bh + 2)
        .attr('stroke', '#fff').attr('stroke-width', 2)
        .attr('stroke-dasharray', '3,2')

      const dragCircle = g.append('circle')
        .attr('cx', px).attr('cy', yPos - 6).attr('r', 5)
        .attr('fill', isModified ? 'var(--color-accent)' : '#fff')
        .attr('stroke', driver.color).attr('stroke-width', 2)
        .style('cursor', 'ew-resize')
        .attr('tabindex', 0)
        .attr('role', 'slider')
        .attr('aria-label', `${driver.code} pit stop at lap ${pit.lap}. Drag to move.`)
        .attr('aria-valuemin', 2)
        .attr('aria-valuemax', totalLaps - 1)
        .attr('aria-valuenow', pit.lap)

      const drag = d3.drag()
        .on('start', function () {
          d3.select(this).attr('r', 7).attr('fill', 'var(--color-accent)')
        })
        .on('drag', function (event) {
          const newX = Math.max(0, Math.min(w, event.x))
          d3.select(this).attr('cx', newX)
        })
        .on('end', function (event) {
          const newX = Math.max(0, Math.min(w, event.x))
          const newLap = Math.round(x.invert(newX))
          const clampedLap = Math.max(2, Math.min(totalLaps - 1, newLap))
          d3.select(this).attr('r', 5)
          const currentPits = [...pitStops.map(p => ({ ...p }))]
          currentPits[pitIdx] = { ...currentPits[pitIdx], lap: clampedLap }
          currentPits.sort((a, b) => a.lap - b.lap)
          const strategy = {
            driverCode: driver.code,
            pitStops: currentPits,
          }
          // Invalidate old sim + call API so race trace / overlays update (Pinia-friendly).
          void store.applyPitStrategyChange(strategy)
        })

      dragCircle.call(drag)

      dragCircle
        .on('mouseover', (event) => {
          tooltip.show(`<strong style="color:${driver.color}">${driver.code}</strong>
            Pit Lap ${pit.lap}<br/>
            ${pit.fromCompound} → ${pit.toCompound} · ${pit.duration_s.toFixed(1)}s<br/>
            <em style="color:var(--color-text-muted)">Drag to move pit stop</em>`)
          tooltip.move(event)
        })
        .on('mousemove', (event) => tooltip.move(event))
        .on('mouseout', () => tooltip.hide())
    })
  })

  if (store.showSimulated && store.simulatedData) {
    const simCode = store.modifiedStrategy?.driverCode
    const simDriver = store.simulatedData.drivers?.find(d => d.code === simCode)
    const origDriver = drivers.find(d => d.code === simCode)
    if (simDriver && origDriver) {
      const yPos = yBand(simCode)
      if (yPos != null) {
        const bh = yBand.bandwidth()
        const simStints = buildStints(simDriver, simDriver.pitStops, totalLaps)
        const simY = yPos + bh + 3
        const simH = Math.max(6, bh * 0.45)

        g.append('text')
          .attr('x', -8).attr('y', simY + simH / 2).attr('dy', '0.35em')
          .attr('text-anchor', 'end')
          .style('font-size', '8px').style('font-weight', '600')
          .style('font-family', 'var(--font-display)')
          .style('fill', 'var(--color-text-muted)')
          .style('font-style', 'italic')
          .text('sim')

        simStints.forEach(stint => {
          const sx = x(stint.startLap)
          const ex = x(stint.endLap)
          const bw = Math.max(2, ex - sx)
          g.append('rect')
            .attr('x', sx).attr('y', simY)
            .attr('width', bw).attr('height', simH).attr('rx', 2)
            .attr('fill', COMPOUND_COLORS[stint.compound] || '#888')
            .attr('fill-opacity', 0.6)
            .attr('stroke', origDriver.color)
            .attr('stroke-width', 1)
            .attr('stroke-dasharray', '3,2')
        })

        simDriver.pitStops.forEach(pit => {
          const px = x(pit.lap)
          g.append('line')
            .attr('x1', px).attr('x2', px)
            .attr('y1', simY - 1).attr('y2', simY + simH + 1)
            .attr('stroke', '#fff').attr('stroke-width', 1.5)
            .attr('stroke-dasharray', '2,2')
        })
      }
    }
  }

  if (store.hoveredLap != null) {
    g.append('line')
      .attr('x1', x(store.hoveredLap)).attr('x2', x(store.hoveredLap))
      .attr('y1', 0).attr('y2', h)
      .attr('stroke', 'var(--color-text-muted)').attr('stroke-width', 1)
      .attr('stroke-dasharray', '4,3').attr('opacity', 0.5)
  }
}
</script>

<template>
  <div class="stint-bar">
    <div class="panel-header">
      <h3 class="panel-title">
        Stint History
        <span class="panel-hint">Drag pit markers to change strategy</span>
      </h3>
      <span
        class="modified-badge"
        v-if="store.modifiedStrategy"
        role="status"
        aria-live="polite"
      >Strategy Modified</span>
    </div>
    <div ref="container" class="chart-container" role="figure" aria-label="Tyre stint bars per driver">
      <p class="placeholder" v-if="!store.raceData">Select a race to view stints</p>
    </div>
  </div>
</template>

<style scoped>
.stint-bar {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.panel-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text);
  margin: 0;
}

.panel-hint {
  font-family: var(--font-body);
  font-weight: 400;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: none;
  letter-spacing: normal;
  margin-left: var(--space-2);
}

.modified-badge {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-accent-text);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  padding: 1px var(--space-2);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
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
