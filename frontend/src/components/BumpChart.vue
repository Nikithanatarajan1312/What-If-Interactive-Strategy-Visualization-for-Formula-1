<script setup>
import { ref, watch, computed } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'
import { chartVizLayers, useSimHoldPreview } from '../composables/useSimHoldPreview'

const store = useRaceStore()
const { onSimHoldPointerDown } = useSimHoldPreview(store, 'bumpChart')
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 44, bottom: 36, left: 40 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [
    store.activeDrivers,
    store.hoveredLap,
    store.brushedLapRange,
    store.highlightedDriver,
    store.savedSimulations,
    store.simulatedData,
    store.showSimulated,
    store.vizCompareMode,
    store.vizShowSimLayer,
    store.vizShowActualLayer,
    store.simHoldChartId,
    store.focusDriverCode,
  ],
  () => { redraw() },
  { deep: true }
)

function lineOpacity(code) {
  const f = store.focusDriverCode
  if (f && f !== code) return 0.18
  const hi = store.highlightedDriver
  if (hi && hi !== code) return 0.15
  return 0.9
}

const chartDescription = computed(() => {
  const n = store.activeDrivers.length
  return n ? `Position flow chart for ${n} drivers. P1 at top. Circles mark overtakes.` : 'No data loaded'
})

/** Lap is on track with a real classification position (not DNF / retired / placeholder). */
function isValidRacePosition(p) {
  if (p == null || Number.isNaN(Number(p))) return false
  const n = Number(p)
  return n >= 1
}

/**
 * Laps in lap order until first invalid position (crash/retire): chart stops there — no P0 / P-1.
 */
function lapsUntilRetirement(lapsInRange) {
  const sorted = [...lapsInRange].sort((a, b) => a.lap - b.lap)
  const out = []
  for (const l of sorted) {
    if (!isValidRacePosition(l.position)) break
    out.push(l)
  }
  return out
}

function draw() {
  const g = getG()
  const svg = getSvg()
  const w = width.value
  const h = height.value
  if (!g || !svg || w <= 0 || h <= 0) return

  svg.attr('role', 'img').attr('aria-label', chartDescription.value)

  const drivers = store.activeDrivers
  if (!drivers.length) return

  const allLaps = drivers.flatMap(d => d.laps)
  const fullLapExtent = d3.extent(allLaps, l => l.lap)
  const lapExtent = store.brushedLapRange || fullLapExtent

  const { showActual, showSim: showSimLayer } = chartVizLayers(store, 'bumpChart')
  const showSim = showSimLayer && store.simulatedData?.drivers?.length
  const split = store.vizCompareMode === 'split' && showActual && showSim

  const visibleLaps = allLaps.filter(
    l => l.lap >= lapExtent[0] && l.lap <= lapExtent[1] && isValidRacePosition(l.position)
  )
  const positionValues = visibleLaps.map(l => l.position)
  let minPos = positionValues.length ? d3.min(positionValues) : 1
  let maxPos = positionValues.length ? d3.max(positionValues) : 20

  let minPosS = minPos
  let maxPosS = maxPos
  if (showSim && store.simulatedData?.drivers?.length) {
    const pv = []
    for (const simD of store.simulatedData.drivers) {
      const simVis = simD.laps.filter(
        (l) => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      for (const l of simVis) {
        if (isValidRacePosition(l.position)) pv.push(l.position)
        if (l.posP5 != null && Number.isFinite(l.posP5)) pv.push(l.posP5)
        if (l.posP95 != null && Number.isFinite(l.posP95)) pv.push(l.posP95)
      }
    }
    if (pv.length) {
      minPosS = d3.min(pv)
      maxPosS = d3.max(pv)
    }
  }

  if (!split && showActual && showSim) {
    minPos = Math.min(minPos, minPosS)
    maxPos = Math.max(maxPos, maxPosS)
  } else if (!showActual && showSim) {
    minPos = minPosS
    maxPos = maxPosS
  }

  const bandGap = split ? 10 : 0
  const hTop = split ? (h - bandGap) / 2 : h
  const hBot = split ? (h - bandGap) / 2 : 0

  const x = d3.scaleLinear().domain(lapExtent).range([0, w])
  let y
  let ySim = null
  if (split) {
    y = d3.scaleLinear().domain([minPos - 0.5, maxPos + 0.5]).range([0, hTop])
    ySim = d3.scaleLinear().domain([minPosS - 0.5, maxPosS + 0.5]).range([hTop + bandGap, h])
  } else {
    y = d3.scaleLinear().domain([minPos - 0.5, maxPos + 0.5]).range([0, h])
  }

  const yForAct = (p) => y(p)
  const yForSim = (p) => (split && ySim ? ySim(p) : y(p))

  if (split) {
    g.append('g').attr('class', 'grid')
      .call(d3.axisLeft(y).tickValues(d3.range(minPos, maxPos + 1)).tickSize(-w).tickFormat(''))
    g.append('g').attr('class', 'grid')
      .attr('transform', `translate(0,${hTop + bandGap})`)
      .call(
        d3.axisLeft(ySim).tickValues(d3.range(minPosS, maxPosS + 1)).tickSize(-w).tickFormat('')
      )
    g.append('line')
      .attr('x1', 0).attr('x2', w).attr('y1', hTop + bandGap / 2).attr('y2', hTop + bandGap / 2)
      .attr('stroke', 'var(--color-border)').attr('stroke-dasharray', '4,3')
    g.append('text').attr('x', 4).attr('y', 12)
      .style('font-size', '10px').style('fill', 'var(--color-text-muted)')
      .style('font-family', 'var(--font-display)').style('font-weight', '700')
      .text('Actual')
    g.append('text').attr('x', 4).attr('y', hTop + bandGap + 12)
      .style('font-size', '10px').style('fill', 'var(--color-text-muted)')
      .style('font-family', 'var(--font-display)').style('font-weight', '700')
      .text('Simulated')
  } else {
    g.append('g').attr('class', 'grid')
      .call(d3.axisLeft(y).tickValues(d3.range(minPos, maxPos + 1)).tickSize(-w).tickFormat(''))
  }

  g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(Math.min(w / 60, 20)).tickFormat(d => `L${d}`))

  if (split) {
    g.append('g').attr('class', 'axis')
      .call(d3.axisLeft(y).tickValues(d3.range(minPos, maxPos + 1)).tickFormat(d => `P${d}`))
    g.append('g').attr('class', 'axis')
      .attr('transform', `translate(0,${hTop + bandGap})`)
      .call(d3.axisLeft(ySim).tickValues(d3.range(minPosS, maxPosS + 1)).tickFormat(d => `P${d}`))
  } else {
    g.append('g').attr('class', 'axis')
      .call(d3.axisLeft(y).tickValues(d3.range(minPos, maxPos + 1)).tickFormat(d => `P${d}`))
  }

  const line = d3.line()
    .x(d => x(d.lap)).y(d => yForAct(d.position))
    .curve(d3.curveMonotoneX)

  if (showActual) {
    drivers.forEach(driver => {
      const inBrush = driver.laps.filter(
        l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      const nonPitLaps = lapsUntilRetirement(inBrush)
      const opacity = lineOpacity(driver.code)
      const dimmed = opacity < 0.5

      g.append('path').datum(nonPitLaps).attr('d', line)
        .attr('fill', 'none').attr('stroke', driver.color)
        .attr('stroke-width', dimmed ? 1.5 : 2.5)
        .attr('stroke-opacity', opacity)

      if (!dimmed) {
        for (let i = 1; i < nonPitLaps.length; i++) {
          const prev = nonPitLaps[i - 1]
          const curr = nonPitLaps[i]
          if (!isValidRacePosition(prev.position) || !isValidRacePosition(curr.position)) continue
          if (curr.position !== prev.position) {
            const gained = curr.position < prev.position
            g.append('circle')
              .attr('cx', x(curr.lap)).attr('cy', yForAct(curr.position)).attr('r', 4)
              .attr('fill', gained ? 'var(--color-success)' : 'var(--color-danger)')
              .attr('stroke', driver.color).attr('stroke-width', 1.5)
              .style('cursor', 'pointer')
              .on('mouseover', (event) => {
                tooltip.show(`<strong style="color:${driver.color}">${driver.code}</strong>
                Lap ${curr.lap}: P${prev.position} → P${curr.position}
                ${gained ? '(gained)' : '(lost)'}`)
                tooltip.move(event)
              })
              .on('mousemove', (event) => tooltip.move(event))
              .on('mouseout', () => tooltip.hide())
          }
        }
      }

      const lastLap = nonPitLaps[nonPitLaps.length - 1]
      if (lastLap) {
        g.append('text')
          .attr('x', x(lastLap.lap) + 6).attr('y', yForAct(lastLap.position))
          .attr('dy', '0.35em')
          .style('font-size', 'var(--text-xs)').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', driver.color)
          .style('opacity', Math.max(0.25, opacity))
          .text(driver.code)
      }
    })
  }

  if (showSim && store.simulatedData?.drivers?.length) {
    store.simulatedData.drivers.forEach((simDriver, simIdx) => {
      const simCode = simDriver.code
      const simColor = simDriver.color || '#fff'
      const simInBrush = simDriver.laps.filter(
        l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      const simLaps = lapsUntilRetirement(simInBrush)
      const opS = lineOpacity(simCode)

      const simLine = d3.line()
        .defined(d => isValidRacePosition(d.position))
        .x(d => x(d.lap)).y(d => yForSim(d.position))
        .curve(d3.curveMonotoneX)

      g.append('path').datum(simLaps).attr('d', simLine)
        .attr('fill', 'none').attr('stroke', simColor)
        .attr('stroke-width', 2.5).attr('stroke-dasharray', split ? '8,4' : '6,3')
        .attr('stroke-opacity', opS)

      if (!split) {
        const simBandRows = simLaps.filter(
          l => isValidRacePosition(l.position)
            && l.posP5 != null && Number.isFinite(l.posP5)
            && l.posP95 != null && Number.isFinite(l.posP95)
            && Math.abs(l.posP95 - l.posP5) > 1e-3
        )
        if (simBandRows.length) {
          const bandArea = d3.area()
            .x(d => x(d.lap))
            .y0(d => yForSim(d.posP95))
            .y1(d => yForSim(d.posP5))
            .curve(d3.curveMonotoneX)
          g.append('path').datum(simBandRows)
            .attr('d', bandArea)
            .attr('fill', simColor).attr('fill-opacity', 0.1 * opS)
        }
      }

      const simLast = [...simLaps].reverse().find((l) => isValidRacePosition(l.position))
      if (simLast) {
        const labelDy = split ? 0 : (-12 - simIdx * 14)
        g.append('text')
          .attr('x', x(simLast.lap) + 6).attr('y', yForSim(simLast.position) + labelDy)
          .attr('dy', '0.35em')
          .style('font-size', 'var(--text-xs)').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', simColor).style('font-style', 'italic')
          .style('opacity', opS)
          .text(`${simCode} (sim)`)
      }
    })
  }

  const crosshairLine = g.append('line')
    .attr('y1', 0).attr('y2', h)
    .attr('stroke', 'var(--color-text-muted)').attr('stroke-width', 1)
    .attr('stroke-dasharray', '4,3').attr('opacity', 0)
  const crosshairDots = g.append('g')

  g.append('rect').attr('width', w).attr('height', h)
    .attr('fill', 'none').attr('pointer-events', 'all')
    .on('mousemove', (event) => {
      const [mx] = d3.pointer(event)
      const lap = Math.round(x.invert(mx))
      const clampedLap = Math.max(lapExtent[0], Math.min(lapExtent[1], lap))
      store.setHoveredLap(clampedLap)

      crosshairLine.attr('x1', x(clampedLap)).attr('x2', x(clampedLap)).attr('opacity', 0.6)
      crosshairDots.selectAll('*').remove()

      let html = `<strong>Lap ${clampedLap}</strong><br/>`
      if (showActual) {
        drivers.forEach(driver => {
          const lapData = driver.laps.find(l => l.lap === clampedLap && !l.isPitLap)
          if (!lapData || !isValidRacePosition(lapData.position)) return
          crosshairDots.append('circle')
            .attr('cx', x(clampedLap)).attr('cy', yForAct(lapData.position))
            .attr('r', 4).attr('fill', driver.color)
            .attr('stroke', '#fff').attr('stroke-width', 1.5)
          html += `<span style="color:${driver.color};font-weight:700">${driver.code}</span> P${lapData.position}<br/>`
        })
      }

      if (showSim && store.simulatedData?.drivers?.length) {
        for (const simDriver of store.simulatedData.drivers) {
          const simLap = simDriver.laps.find(l => l.lap === clampedLap && !l.isPitLap)
          if (simLap && isValidRacePosition(simLap.position)) {
            const simCode = simDriver.code
            const c = simDriver.color || '#fff'
            crosshairDots.append('circle')
              .attr('cx', x(clampedLap)).attr('cy', yForSim(simLap.position))
              .attr('r', 4).attr('fill', c)
              .attr('stroke', '#fff').attr('stroke-width', 1.5)
              .attr('stroke-dasharray', '2,2')
            html += `<span style="color:${simDriver.color};font-weight:700;font-style:italic">${simCode} (sim)</span> P${simLap.position}`
            if (simLap.posP5 != null) html += ` <span style="color:var(--color-text-muted)">[P${simLap.posP5}–P${simLap.posP95}]</span>`
            html += `<br/>`
          }
        }
      }

      tooltip.show(html)
      tooltip.move(event)
    })
    .on('mouseout', () => {
      store.setHoveredLap(null)
      crosshairLine.attr('opacity', 0)
      crosshairDots.selectAll('*').remove()
      tooltip.hide()
    })
}
</script>

<template>
  <div class="bump-chart">
    <div class="panel-header">
      <h3 class="panel-title">Position Flow</h3>
      <div class="panel-header-actions">
        <button
          type="button"
          class="panel-expand panel-sim-hold"
          :disabled="!store.hasSavedSimulations"
          title="Hold to preview this chart with simulated data only"
          aria-label="Hold to preview position flow with simulated data only"
          @pointerdown="onSimHoldPointerDown"
          @click.prevent
        >
          Sim
        </button>
        <button
          type="button"
          class="panel-expand"
          :aria-expanded="store.expandedPanelId === 'bumpChart'"
          aria-label="Expand position flow panel"
          @click="store.toggleExpandedPanel('bumpChart')"
        >
          Expand
        </button>
      </div>
    </div>
    <div ref="container" class="chart-container" role="figure" aria-label="Position changes over laps">
      <p class="placeholder" v-if="!store.raceData">Select a race to view positions</p>
      <p class="placeholder" v-else-if="!store.activeDrivers.length">Select one or more drivers to view positions</p>
    </div>
  </div>
</template>

<style scoped>
.bump-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
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

.panel-expand {
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text);
  cursor: pointer;
  flex-shrink: 0;
}

.panel-expand:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.panel-sim-hold {
  touch-action: none;
  user-select: none;
}

.panel-sim-hold:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.panel-sim-hold:disabled:hover {
  border-color: var(--color-border);
  color: var(--color-text);
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
