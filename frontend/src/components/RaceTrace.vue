<script setup>
import { ref, watch, computed } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'

const COMPOUND_COLORS = {
  SOFT: 'var(--tyre-soft)',
  MEDIUM: 'var(--tyre-medium)',
  HARD: 'var(--tyre-hard)',
  INTERMEDIATE: 'var(--tyre-intermediate)',
  WET: 'var(--tyre-wet)',
}

const store = useRaceStore()
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 44, bottom: 36, left: 52 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [store.activeDrivers, store.hoveredLap, store.brushedLapRange, store.simulatedData, store.showSimulated],
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

function generateUncertaintyBands(driver, scale = 1.0) {
  const nonPitLaps = driver.laps.filter(l => !l.isPitLap && hasFiniteGap(l))
  return nonPitLaps.map(l => {
    const noise = (l.tyreAge * 0.15 + l.lap * 0.04) * scale
    return {
      lap: l.lap,
      gap: l.gapToLeader,
      p5: l.gapToLeader + noise * 1.8,
      p25: l.gapToLeader + noise * 0.8,
      p75: Math.max(0, l.gapToLeader - noise * 0.8),
      p95: Math.max(0, l.gapToLeader - noise * 1.8),
    }
  })
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

  const lapExtent = store.brushedLapRange
    ? [store.brushedLapRange[0], store.brushedLapRange[1]]
    : fullLapExtent

  const visibleLaps = allLaps.filter(
    l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1] && hasFiniteGap(l)
  )
  const gapExtent = d3.extent(visibleLaps, l => l.gapToLeader)
  const gLo = gapExtent[0] ?? 0
  const gHi = gapExtent[1] ?? 1
  const gapPadding = (gHi - gLo) * 0.08 || 1

  const x = d3.scaleLinear().domain(lapExtent).range([0, w])
  const y = d3.scaleLinear()
    .domain([gLo - gapPadding, gHi + gapPadding])
    .range([0, h])

  g.append('g').attr('class', 'grid')
    .call(d3.axisLeft(y).tickSize(-w).tickFormat(''))
  g.append('g').attr('class', 'grid').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).tickSize(-h).tickFormat(''))

  g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(Math.min(w / 60, 20)).tickFormat(d => `L${d}`))
  g.append('g').attr('class', 'axis')
    .call(d3.axisLeft(y).ticks(Math.min(h / 40, 10)).tickFormat(d => `${d.toFixed(1)}s`))

  g.append('text').attr('transform', 'rotate(-90)')
    .attr('x', -h / 2).attr('y', -40).attr('text-anchor', 'middle')
    .style('font-size', 'var(--text-xs)').style('fill', 'var(--color-text-secondary)')
    .style('font-family', 'var(--font-display)').style('font-weight', '600')
    .text('Gap to Leader (s)')

  const area5_95 = d3.area()
    .x(d => x(d.lap)).y0(d => y(d.p5)).y1(d => y(d.p95))
    .curve(d3.curveMonotoneX)
  const area25_75 = d3.area()
    .x(d => x(d.lap)).y0(d => y(d.p25)).y1(d => y(d.p75))
    .curve(d3.curveMonotoneX)

  drivers.forEach(driver => {
    const bands = generateUncertaintyBands(driver)
    const filtered = bands.filter(b => b.lap >= lapExtent[0] && b.lap <= lapExtent[1])
    if (filtered.length < 2) return
    g.append('path').datum(filtered).attr('d', area5_95)
      .attr('fill', driver.color).attr('fill-opacity', 0.06)
    g.append('path').datum(filtered).attr('d', area25_75)
      .attr('fill', driver.color).attr('fill-opacity', 0.12)
  })

  const line = d3.line()
    .defined(d => !d.isPitLap && hasFiniteGap(d))
    .x(d => x(d.lap)).y(d => y(d.gapToLeader))
    .curve(d3.curveMonotoneX)

  drivers.forEach(driver => {
    const visible = driver.laps.filter(
      l => l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
    )
    g.append('path').datum(visible).attr('d', line)
      .attr('fill', 'none').attr('stroke', driver.color)
      .attr('stroke-width', 2.5).attr('stroke-opacity', 0.9)
  })

  drivers.forEach(driver => {
    driver.pitStops.forEach(pit => {
      const lapBefore = driver.laps.find(l => l.lap === pit.lap - 1)
      if (!lapBefore || !hasFiniteGap(lapBefore)
        || lapBefore.lap < lapExtent[0] || lapBefore.lap > lapExtent[1]) return
      g.append('circle')
        .attr('cx', x(lapBefore.lap)).attr('cy', y(lapBefore.gapToLeader))
        .attr('r', 5)
        .attr('fill', COMPOUND_COLORS[pit.toCompound] || '#fff')
        .attr('stroke', driver.color).attr('stroke-width', 2)
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
      .attr('x', x(lastLap.lap) + 6).attr('y', y(lastLap.gapToLeader))
      .attr('dy', '0.35em')
      .style('font-size', 'var(--text-xs)').style('font-weight', '700')
      .style('font-family', 'var(--font-display)')
      .style('fill', driver.color)
      .text(driver.code)
  })

  if (store.showSimulated && store.simulatedData) {
    const simDriverCode = store.modifiedStrategy?.driverCode
    const simDriver = store.simulatedData.drivers?.find(d => d.code === simDriverCode)
    if (simDriver) {
      const simColor = simDriver.color || '#fff'
      const simLaps = simDriver.laps.filter(
        l => !l.isPitLap && l.lap >= lapExtent[0] && l.lap <= lapExtent[1]
      )

      const hasBackendBands = simLaps.some(
        l => hasFiniteGap(l) && l.p5 != null && Number.isFinite(l.p5)
      )
      if (hasBackendBands) {
        const bandData = simLaps.filter(
          l => hasFiniteGap(l) && l.p5 != null && Number.isFinite(l.p5)
            && l.p95 != null && Number.isFinite(l.p95)
        )

        const simArea5_95 = d3.area()
          .x(d => x(d.lap)).y0(d => y(d.p5)).y1(d => y(d.p95))
          .curve(d3.curveMonotoneX)
        const simArea25_75 = d3.area()
          .x(d => x(d.lap)).y0(d => y(d.p25)).y1(d => y(d.p75))
          .curve(d3.curveMonotoneX)

        g.append('path').datum(bandData).attr('d', simArea5_95)
          .attr('fill', simColor).attr('fill-opacity', 0.08)
          .attr('stroke', 'none')
        g.append('path').datum(bandData).attr('d', simArea25_75)
          .attr('fill', simColor).attr('fill-opacity', 0.15)
          .attr('stroke', 'none')
      }

      const simLine = d3.line()
        .defined(d => !d.isPitLap && hasFiniteGap(d))
        .x(d => x(d.lap)).y(d => y(d.gapToLeader))
        .curve(d3.curveMonotoneX)

      g.append('path').datum(simLaps).attr('d', simLine)
        .attr('fill', 'none').attr('stroke', simColor)
        .attr('stroke-width', 2.5).attr('stroke-dasharray', '6,3')
        .attr('stroke-opacity', 0.9)

      const simLast = [...simLaps].reverse().find((l) => hasFiniteGap(l))
      if (simLast) {
        g.append('text')
          .attr('x', x(simLast.lap) + 6).attr('y', y(simLast.gapToLeader) - 12)
          .attr('dy', '0.35em')
          .style('font-size', 'var(--text-xs)').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', simColor).style('font-style', 'italic')
          .text(`${simDriverCode} (sim)`)
      }
    }
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
      drivers.forEach(driver => {
        const lapData = driver.laps.find(l => l.lap === clampedLap && !l.isPitLap)
        if (!lapData || !hasFiniteGap(lapData)) return
        crosshairDots.append('circle')
          .attr('cx', x(clampedLap)).attr('cy', y(lapData.gapToLeader))
          .attr('r', 4).attr('fill', driver.color)
          .attr('stroke', '#fff').attr('stroke-width', 1.5)
        const posStr = lapData.position != null && Number.isFinite(lapData.position)
          ? ` · P${lapData.position}` : ''
        html += `<span style="color:${driver.color};font-weight:700">${driver.code}</span>
          +${lapData.gapToLeader.toFixed(1)}s${posStr}
          · ${lapData.compound} (age ${lapData.tyreAge})<br/>`
      })
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
      <button
        v-if="store.brushedLapRange"
        class="reset-btn"
        @click="store.setBrushedRange(null)"
        aria-label="Reset zoom to full race"
      >Reset Zoom</button>
    </div>
    <div ref="container" class="chart-container" role="figure" aria-label="Gap to leader line chart">
      <p class="placeholder" v-if="!store.raceData">Select a race to view the trace</p>
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
