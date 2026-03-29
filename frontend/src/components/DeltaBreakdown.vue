<script setup>
import { ref, watch } from 'vue'
import * as d3 from 'd3'
import { useRaceStore } from '../stores/raceStore'
import { useChart } from '../composables/useChart'
import { useTooltip } from '../composables/useTooltip'

const store = useRaceStore()
const container = ref(null)
const tooltip = useTooltip()

const margin = { top: 16, right: 24, bottom: 36, left: 52 }
const { width, height, getG, getSvg, onDraw, redraw } = useChart(container, margin)

onDraw(draw)

watch(
  () => [store.activeDrivers, store.simulatedData, store.showSimulated, store.highlightedDriver],
  () => { redraw() },
  { deep: true }
)

const COMPONENTS = [
  { label: 'Pit Stop Loss', color: '#ff6b6b' },
  { label: 'Tyre Degradation', color: '#ffbf40' },
  { label: 'Traffic / Pace', color: '#818cf8' },
]

function computeDeltas(driver) {
  if (!driver.laps.length) return null
  const lastWithGap = [...driver.laps].reverse().find(
    (l) => l.gapToLeader != null && Number.isFinite(l.gapToLeader)
  )
  const finalGap = lastWithGap?.gapToLeader
  if (finalGap == null || finalGap <= 0) return null

  const numExtraPits = Math.max(0, driver.pitStops.length - 1)
  const pitLoss = numExtraPits * 2.5 + driver.pitStops.length * 0.3
  const remaining = Math.max(0, finalGap - pitLoss)
  const tyreDeg = remaining * 0.55
  const trafficEffect = remaining * 0.45

  return {
    driver: driver.code,
    color: driver.color,
    components: [
      { label: COMPONENTS[0].label, value: pitLoss, color: COMPONENTS[0].color },
      { label: COMPONENTS[1].label, value: tyreDeg, color: COMPONENTS[1].color },
      { label: COMPONENTS[2].label, value: trafficEffect, color: COMPONENTS[2].color },
    ],
    total: finalGap,
  }
}

function draw() {
  const g = getG()
  const svg = getSvg()
  const w = width.value
  const h = height.value
  if (!g || !svg || w <= 0 || h <= 0) return

  svg.attr('role', 'img')
    .attr('aria-label', 'Delta breakdown showing time gap to leader decomposed into pit loss, tyre degradation, and traffic/pace.')

  const drivers = store.activeDrivers
  if (!drivers.length) return

  const showSim = store.showSimulated && store.simulatedData
  const simCode = store.modifiedStrategy?.driverCode

  const deltas = drivers.map(d => computeDeltas(d)).filter(d => d && Math.abs(d.total) > 0.1)

  let simDeltas = []
  if (showSim && simCode) {
    const simDriver = store.simulatedData.drivers?.find(d => d.code === simCode)
    if (simDriver) {
      const sd = computeDeltas(simDriver)
      if (sd) simDeltas = [{ ...sd, driver: `${simCode} (sim)`, isSim: true, origCode: simCode, color: simDriver.color }]
    }
  }

  const highlighted = store.highlightedDriver

  const allDeltas = [...deltas, ...simDeltas]

  if (!allDeltas.length) {
    g.append('text').attr('x', w / 2).attr('y', h / 2).attr('text-anchor', 'middle')
      .style('fill', 'var(--color-text-muted)')
      .style('font-size', 'var(--text-base)')
      .style('font-family', 'var(--font-body)')
      .text('Leader has no delta — select trailing drivers to see breakdown')
    return
  }

  const xMax = d3.max(allDeltas, d => d3.sum(d.components, c => Math.abs(c.value))) || 1
  const x = d3.scaleLinear().domain([0, xMax * 1.1]).range([0, w])
  const yBand = d3.scaleBand().domain(allDeltas.map(d => d.driver)).range([0, h]).padding(0.25)

  g.append('g').attr('class', 'axis').attr('transform', `translate(0,${h})`)
    .call(d3.axisBottom(x).ticks(6).tickFormat(d => `${d.toFixed(1)}s`))

  g.append('text').attr('x', w / 2).attr('y', h + 30).attr('text-anchor', 'middle')
    .style('font-size', 'var(--text-xs)').style('fill', 'var(--color-text-secondary)')
    .style('font-family', 'var(--font-display)').style('font-weight', '600')
    .text('Time delta to leader (s)')

  allDeltas.forEach(delta => {
    const isSim = delta.isSim
    const matchCode = isSim ? delta.origCode : delta.driver
    const dimmed = highlighted && highlighted !== matchCode
    const opacity = dimmed ? 0.15 : isSim ? 0.7 : 0.85

    g.append('text').attr('x', -8)
      .attr('y', yBand(delta.driver) + yBand.bandwidth() / 2)
      .attr('dy', '0.35em').attr('text-anchor', 'end')
      .style('font-size', 'var(--text-xs)').style('font-weight', '700')
      .style('font-family', 'var(--font-display)')
      .style('fill', delta.color).style('opacity', dimmed ? 0.3 : 1)
      .style('font-style', isSim ? 'italic' : 'normal')
      .text(delta.driver)

    let cumX = 0
    delta.components.forEach(comp => {
      const barW = x(Math.abs(comp.value))
      const bx = x(cumX)

      g.append('rect')
        .attr('x', bx).attr('y', yBand(delta.driver))
        .attr('width', Math.max(1, barW)).attr('height', yBand.bandwidth())
        .attr('rx', 2).attr('fill', comp.color).attr('fill-opacity', opacity)
        .attr('stroke', isSim ? '#fff' : 'none')
        .attr('stroke-width', isSim ? 1 : 0)
        .attr('stroke-dasharray', isSim ? '4,2' : 'none')
        .style('cursor', 'pointer')
        .on('mouseover', (event) => {
          let tip = `<strong style="color:${delta.color}">${delta.driver}</strong>`
          if (isSim) tip += ` <em>(simulated)</em>`
          tip += `<br/>${comp.label}: <strong>${comp.value.toFixed(1)}s</strong>`
          tooltip.show(tip)
          tooltip.move(event)
          store.setHighlightedDriver(matchCode)
        })
        .on('mousemove', (event) => tooltip.move(event))
        .on('mouseout', () => {
          tooltip.hide()
          store.setHighlightedDriver(null)
        })

      if (barW > 35 && !dimmed) {
        g.append('text')
          .attr('x', bx + barW / 2)
          .attr('y', yBand(delta.driver) + yBand.bandwidth() / 2)
          .attr('dy', '0.35em').attr('text-anchor', 'middle')
          .style('font-size', '9px').style('font-weight', '700')
          .style('font-family', 'var(--font-display)')
          .style('fill', '#fff').style('pointer-events', 'none')
          .text(`${comp.value.toFixed(1)}s`)
      }

      cumX += Math.abs(comp.value)
    })

    if (!dimmed) {
      g.append('text')
        .attr('x', x(cumX) + 6)
        .attr('y', yBand(delta.driver) + yBand.bandwidth() / 2)
        .attr('dy', '0.35em')
        .style('font-size', 'var(--text-xs)').style('font-weight', '700')
        .style('font-family', 'var(--font-display)')
        .style('fill', isSim ? 'var(--color-accent-text, #ff3333)' : 'var(--color-text)')
        .text(`+${delta.total.toFixed(1)}s`)
    }
  })

  const legendItems = [...COMPONENTS]
  if (showSim) legendItems.push({ label: 'Simulated', color: 'var(--color-accent, #e10600)' })
  const legendW = legendItems.length * 110
  const legend = g.append('g').attr('transform', `translate(${w - legendW}, -10)`)
  legendItems.forEach((item, i) => {
    legend.append('rect')
      .attr('x', i * 110).attr('y', 0).attr('width', 10).attr('height', 10)
      .attr('rx', 2).attr('fill', item.color).attr('fill-opacity', 0.85)
      .attr('stroke', item.label === 'Simulated' ? '#fff' : 'none')
      .attr('stroke-dasharray', item.label === 'Simulated' ? '3,1' : 'none')
    legend.append('text')
      .attr('x', i * 110 + 14).attr('y', 9)
      .style('font-size', '9px').style('fill', 'var(--color-text-secondary)')
      .style('font-family', 'var(--font-display)').style('font-weight', '600')
      .text(item.label)
  })
}
</script>

<template>
  <div class="delta-breakdown">
    <h3 class="panel-title">Delta Breakdown</h3>
    <div ref="container" class="chart-container" role="figure" aria-label="Time delta decomposition stacked bar chart">
      <p class="placeholder" v-if="!store.raceData">
        Select a race to see the time delta breakdown
      </p>
    </div>
  </div>
</template>

<style scoped>
.delta-breakdown {
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
  text-align: center;
}
</style>
