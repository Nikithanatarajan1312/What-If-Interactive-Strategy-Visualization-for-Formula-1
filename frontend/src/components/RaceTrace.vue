<script setup>
import { ref, watch, computed } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'
import { chartVizLayers, useSimHoldPreview } from '../composables/useSimHoldPreview'

const COMPOUND_COLORS = {
  SOFT: 'var(--tyre-soft)',
  MEDIUM: 'var(--tyre-medium)',
  HARD: 'var(--tyre-hard)',
  INTERMEDIATE: 'var(--tyre-intermediate)',
  WET: 'var(--tyre-wet)',
}

const store = useRaceStore()
const { onSimHoldPointerDown } = useSimHoldPreview(store, 'raceTrace')
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 44, bottom: 36, left: 52 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [
    store.activeDrivers,
    store.hoveredLap,
    store.brushedLapRange,
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

const chartDescription = computed(() => {
  const drivers = store.activeDrivers
  if (!drivers.length) return 'No data loaded'
  const count = drivers.length
  const range = store.brushedLapRange
  const lapInfo = range ? `Laps ${range[0]}–${range[1]}` : `Full race`
  return `Race trace showing gap to leader for ${count} drivers. ${lapInfo}. Brush to zoom, hover for details.`
})

function hasFiniteGap(l) {
  return l.gapToLeader != null && Number.isFinite(l.gapToLeader)
}

/** Backend may echo p5/p95 even when Monte Carlo is off (all equal to median). */
function hasMeaningfulGapBands(laps) {
  return laps.some((l) => {
    if (!hasFiniteGap(l)) return false
    if (l.p5 == null || l.p95 == null || !Number.isFinite(l.p5) || !Number.isFinite(l.p95)) return false
    return Math.abs(l.p95 - l.p5) > 1e-3
  })
}

function dimForCode(code) {
  const f = store.focusDriverCode
  if (!f) return 1
  return f === code ? 1 : 0.2
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

  const { showActual, showSim: showSimLayer } = chartVizLayers(store, 'raceTrace')
  const showSim = showSimLayer && store.simulatedData?.drivers?.length
  const split = store.vizCompareMode === 'split' && showActual && showSim

  const allLaps = drivers.flatMap(d => d.laps)
  const fullLapExtent = d3.extent(allLaps, l => l.lap)

  const lapExtent = store.brushedLapRange
    ? [store.brushedLapRange[0], store.brushedLapRange[1]]
    : fullLapExtent

  const visibleLaps = allLaps.filter(
    l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1] && hasFiniteGap(l)
  )
  const gapExtentAct = d3.extent(visibleLaps, l => l.gapToLeader)
  let gLo = gapExtentAct[0] ?? 0
  let gHi = gapExtentAct[1] ?? 1
  if (!showActual || !visibleLaps.length) {
    gLo = 0
    gHi = 1
  }

  let gLoS = gLo
  let gHiS = gHi
  if (showSim && store.simulatedData?.drivers?.length) {
    const band = []
    for (const simD of store.simulatedData.drivers) {
      const simVis = simD.laps.filter(
        (l) => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      for (const l of simVis) {
        if (hasFiniteGap(l)) band.push(l.gapToLeader)
        if (
          l.p5 != null && l.p95 != null
          && Number.isFinite(l.p5) && Number.isFinite(l.p95)
          && Math.abs(l.p95 - l.p5) > 1e-3
        ) {
          band.push(l.p5, l.p95)
        }
      }
    }
    if (band.length) {
      gLoS = d3.min(band)
      gHiS = d3.max(band)
    }
  }

  if (!split && showActual && showSim) {
    gLo = Math.min(gLo, gLoS)
    gHi = Math.max(gHi, gHiS)
  } else if (!showActual && showSim) {
    gLo = gLoS
    gHi = gHiS
  }

  const bandGap = split ? 10 : 0
  const hTop = split ? (h - bandGap) / 2 : h
  const hBot = split ? (h - bandGap) / 2 : 0

  const gapPadA = showActual && visibleLaps.length ? (gHi - gLo) * 0.08 || 1 : 1
  const gapPadS = (gHiS - gLoS) * 0.08 || 1

  const x = d3.scaleLinear().domain(lapExtent).range([0, w])

  let y
  let ySim = null
  if (split) {
    y = d3.scaleLinear()
      .domain([gLo - gapPadA, gHi + gapPadA])
      .range([0, hTop])
    ySim = d3.scaleLinear()
      .domain([gLoS - gapPadS, gHiS + gapPadS])
      .range([hTop + bandGap, h])
  } else {
    const gapPadding = (gHi - gLo) * 0.08 || 1
    y = d3.scaleLinear()
      .domain([gLo - gapPadding, gHi + gapPadding])
      .range([0, h])
  }

  const yForActual = (gap) => y(gap)
  const yForSim = (gap) => (split && ySim ? ySim(gap) : y(gap))

  if (split) {
    g.append('g').attr('class', 'grid')
      .call(d3.axisLeft(y).tickSize(-w).tickFormat('').ticks(Math.min(hTop / 28, 8)))
    g.append('g').attr('class', 'grid')
      .attr('transform', `translate(0,${hTop + bandGap})`)
      .call(
        d3.axisLeft(ySim).tickSize(-w).tickFormat('').ticks(Math.min(hBot / 28, 8))
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
      .call(d3.axisLeft(y).tickSize(-w).tickFormat(''))
    g.append('g').attr('class', 'grid').attr('transform', `translate(0,${h})`)
      .call(d3.axisBottom(x).tickSize(-h).tickFormat(''))
  }

  g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(Math.min(w / 60, 20)).tickFormat(d => `L${d}`))

  if (split) {
    g.append('g').attr('class', 'axis')
      .call(d3.axisLeft(y).ticks(Math.min(hTop / 36, 8)).tickFormat(d => `${d.toFixed(1)}s`))
    g.append('g').attr('class', 'axis')
      .attr('transform', `translate(0,${hTop + bandGap})`)
      .call(d3.axisLeft(ySim).ticks(Math.min(hBot / 36, 8)).tickFormat(d => `${d.toFixed(1)}s`))
  } else {
    g.append('g').attr('class', 'axis')
      .call(d3.axisLeft(y).ticks(Math.min(h / 40, 10)).tickFormat(d => `${d.toFixed(1)}s`))
  }

  const yMid = split ? hTop / 2 : h / 2
  g.append('text').attr('transform', 'rotate(-90)')
    .attr('x', -yMid).attr('y', -40).attr('text-anchor', 'middle')
    .style('font-size', 'var(--text-xs)').style('fill', 'var(--color-text-secondary)')
    .style('font-family', 'var(--font-display)').style('font-weight', '600')
    .text(split ? 'Gap (s) — actual / sim' : 'Gap to Leader (s)')

  const line = d3.line()
    .defined(d => !d.isPitLap && hasFiniteGap(d))
    .x(d => x(d.lap)).y(d => yForActual(d.gapToLeader))
    .curve(d3.curveMonotoneX)

  if (showActual) {
    drivers.forEach(driver => {
      const visible = driver.laps.filter(
        l => l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      const op = 0.9 * dimForCode(driver.code)
      g.append('path').datum(visible).attr('d', line)
        .attr('fill', 'none').attr('stroke', driver.color)
        .attr('stroke-width', 2.5).attr('stroke-opacity', op)
    })

    drivers.forEach(driver => {
      driver.pitStops.forEach(pit => {
        const lapBefore = driver.laps.find(l => l.lap === pit.lap - 1)
        if (!lapBefore || !hasFiniteGap(lapBefore)
          || lapBefore.lap < lapExtent[0] || lapBefore.lap > lapExtent[1]) return
        g.append('circle')
          .attr('cx', x(lapBefore.lap)).attr('cy', yForActual(lapBefore.gapToLeader))
          .attr('r', 5)
          .attr('fill', COMPOUND_COLORS[pit.toCompound] || '#fff')
          .attr('stroke', driver.color).attr('stroke-width', 2)
          .attr('opacity', dimForCode(driver.code))
          .style('cursor', 'pointer')
          .on('mouseover', (event) => {
            tooltip.show(`<strong>${driver.code}</strong> Pit Lap ${pit.lap}<br/>
            ${pit.fromCompound} → ${pit.toCompound}<br/>Stop: ${pit.duration_s.toFixed(1)}s`)
            tooltip.move(event)
          })
          .on('mousemove', (event) => tooltip.move(event))
          .on('mouseout', () => tooltip.hide())
      })
    })

    drivers.forEach(driver => {
      const visible = driver.laps.filter(
        l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1] && hasFiniteGap(l)
      )
      const lastLap = visible[visible.length - 1]
      if (!lastLap) return
      g.append('text')
        .attr('x', x(lastLap.lap) + 6).attr('y', yForActual(lastLap.gapToLeader))
        .attr('dy', '0.35em')
        .style('font-size', 'var(--text-xs)').style('font-weight', '700')
        .style('font-family', 'var(--font-display)')
        .style('fill', driver.color)
        .style('opacity', dimForCode(driver.code))
        .text(driver.code)
    })
  }

  if (showSim && store.simulatedData?.drivers?.length) {
    store.simulatedData.drivers.forEach((simDriver, simIdx) => {
      const simDriverCode = simDriver.code
      const simColor = simDriver.color || '#fff'
      const simLaps = simDriver.laps.filter(
        l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )
      const opS = 0.9 * dimForCode(simDriverCode)

      if (hasMeaningfulGapBands(simLaps)) {
        const bandData = simLaps.filter(
          l => hasFiniteGap(l) && l.p5 != null && Number.isFinite(l.p5)
            && l.p95 != null && Number.isFinite(l.p95)
        )

        const simArea5_95 = d3.area()
          .x(d => x(d.lap)).y0(d => yForSim(d.p5)).y1(d => yForSim(d.p95))
          .curve(d3.curveMonotoneX)
        const simArea25_75 = d3.area()
          .x(d => x(d.lap)).y0(d => yForSim(d.p25)).y1(d => yForSim(d.p75))
          .curve(d3.curveMonotoneX)

        const fillOp = split ? opS : opS
        g.append('path').datum(bandData).attr('d', simArea5_95)
          .attr('fill', simColor).attr('fill-opacity', split ? 0.1 * fillOp : 0.08 * fillOp)
          .attr('stroke', 'none')
        g.append('path').datum(bandData).attr('d', simArea25_75)
          .attr('fill', simColor).attr('fill-opacity', split ? 0.18 * fillOp : 0.15 * fillOp)
          .attr('stroke', 'none')
      }

      const simLine = d3.line()
        .defined(d => !d.isPitLap && hasFiniteGap(d))
        .x(d => x(d.lap)).y(d => yForSim(d.gapToLeader))
        .curve(d3.curveMonotoneX)

      g.append('path').datum(simLaps).attr('d', simLine)
        .attr('fill', 'none').attr('stroke', simColor)
        .attr('stroke-width', 2.5).attr('stroke-dasharray', split ? '8,4' : '6,3')
        .attr('stroke-opacity', opS)

      const simLast = [...simLaps].reverse().find((l) => hasFiniteGap(l))
      if (simLast) {
        const labelDy = split ? 0 : (-12 - simIdx * 14)
        g.append('text')
          .attr('x', x(simLast.lap) + 6).attr('y', yForSim(simLast.gapToLeader) + labelDy)
          .attr('dy', '0.35em')
          .style('font-size', 'var(--text-xs)').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', simColor).style('font-style', 'italic')
          .style('opacity', opS)
          .text(`${simDriverCode} (sim)`)
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
          if (!lapData || !hasFiniteGap(lapData)) return
          crosshairDots.append('circle')
            .attr('cx', x(clampedLap)).attr('cy', yForActual(lapData.gapToLeader))
            .attr('r', 4).attr('fill', driver.color)
            .attr('stroke', '#fff').attr('stroke-width', 1.5)
          const posStr = lapData.position != null && Number.isFinite(lapData.position)
            ? ` · P${lapData.position}` : ''
          html += `<span style="color:${driver.color};font-weight:700">${driver.code}</span>
          +${lapData.gapToLeader.toFixed(1)}s${posStr}
          · ${lapData.compound} (age ${lapData.tyreAge})<br/>`
        })
      }
      if (showSim && store.simulatedData?.drivers?.length) {
        for (const simD of store.simulatedData.drivers) {
          const simLap = simD.laps.find((l) => l.lap === clampedLap && !l.isPitLap)
          if (!simLap || !hasFiniteGap(simLap)) continue
          const c = simD.color || '#fff'
          crosshairDots.append('circle')
            .attr('cx', x(clampedLap)).attr('cy', yForSim(simLap.gapToLeader))
            .attr('r', 4).attr('fill', c)
            .attr('stroke', '#fff').attr('stroke-width', 1.5)
            .attr('stroke-dasharray', '2,2')
          html += `<span style="color:${c};font-weight:700;font-style:italic">${simD.code} (sim)</span>
            +${simLap.gapToLeader.toFixed(1)}s<br/>`
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

  const brush = d3.brushX()
    .extent([[0, 0], [w, h]])
    .on('end', (event) => {
      if (!event.selection) {
        store.setBrushedRange(null)
        return
      }
      const [x0, x1] = event.selection.map(x.invert).map(Math.round)
      if (x1 - x0 < 3) {
        store.setBrushedRange(null)
        g.select('.brush').call(brush.move, null)
        return
      }
      store.setBrushedRange([
        Math.max(fullLapExtent[0], x0),
        Math.min(fullLapExtent[1], x1),
      ])
    })

  const brushG = g.append('g').attr('class', 'brush').call(brush)

  if (store.brushedLapRange && !store.brushedLapRange._zoomed) {
    const fullX = d3.scaleLinear().domain(fullLapExtent).range([0, w])
    brushG.call(brush.move, [
      fullX(store.brushedLapRange[0]),
      fullX(store.brushedLapRange[1]),
    ])
  }
}
</script>

<template>
  <div class="race-trace">
    <div class="panel-header">
      <h3 class="panel-title">Race Trace <span class="panel-title__sub">Gap to Leader</span></h3>
      <div class="panel-header-actions">
        <button
          v-if="store.brushedLapRange"
          class="reset-btn"
          @click="store.setBrushedRange(null)"
          aria-label="Reset zoom to full race"
        >Reset Zoom</button>
        <button
          type="button"
          class="panel-expand panel-sim-hold"
          :disabled="!store.hasSavedSimulations"
          title="Hold to preview this chart with simulated data only"
          aria-label="Hold to preview race trace with simulated data only"
          @pointerdown="onSimHoldPointerDown"
          @click.prevent
        >
          Sim
        </button>
        <button
          type="button"
          class="panel-expand"
          :aria-expanded="store.expandedPanelId === 'raceTrace'"
          aria-label="Expand race trace panel"
          @click="store.toggleExpandedPanel('raceTrace')"
        >
          Expand
        </button>
      </div>
    </div>
    <div ref="container" class="chart-container" role="figure" aria-label="Gap to leader line chart">
      <p class="placeholder" v-if="!store.raceData">Select a race to view the trace</p>
      <p class="placeholder" v-else-if="!store.activeDrivers.length">Select one or more drivers to view the trace</p>
    </div>
  </div>
</template>

<style scoped>
.race-trace {
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

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
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

.panel-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text);
  margin: 0;
}

.panel-title__sub {
  font-weight: 400;
  color: var(--color-text-muted);
  margin-left: var(--space-1);
}

.reset-btn {
  padding: 2px var(--space-3);
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 600;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-accent-text);
  cursor: pointer;
  transition: background var(--duration-fast);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.reset-btn:hover {
  background: rgba(225, 6, 0, 0.15);
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
