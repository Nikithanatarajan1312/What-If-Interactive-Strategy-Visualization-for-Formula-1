<script setup>
import { ref, watch, computed } from 'vue'
import { useRaceStore } from '../stores/raceStore'
import { chartVizLayers, useSimHoldPreview } from '../composables/useSimHoldPreview'
import DeltaDriverCell from './DeltaDriverCell.vue'
import {
  breakdownForDriver,
  formatGainSeconds,
} from '../utils/deltaBreakdownUtils'

const store = useRaceStore()
const { onSimHoldPointerDown } = useSimHoldPreview(store, 'deltaBreakdown')
/** When a focus driver is set, optionally show only that driver (+ sim row) in the chart. */
const narrowFocusDelta = ref(false)

watch(
  () => store.focusDriverCode,
  (c) => {
    if (!c) narrowFocusDelta.value = false
  }
)

const focusSummary = computed(() => {
  const c = store.focusDriverCode
  if (!c || !store.raceData) return ''
  const u = String(c).toUpperCase()
  const db = store.strategyViz?.delta_breakdown
  const bd = db?.[u] || db?.[c]
  const sav = store.savedSimulations?.[c]?.simDelta
  const parts = []
  if (bd?.total != null && Number.isFinite(bd.total))
    parts.push(`Pit-window model net: ${formatGainSeconds(bd.total)}`)
  if (sav?.total != null && Number.isFinite(sav.total))
    parts.push(`Saved sim net: ${formatGainSeconds(sav.total)}`)
  return parts.join(' · ')
})

function isDeltaDimmed(code) {
  const h = store.highlightedDriver
  const f = store.focusDriverCode
  if (h && h !== code) return true
  if (f && f !== code) return true
  return false
}

function onDeltaCellEnter(code) {
  store.setHighlightedDriver(code)
}

function onDeltaCellLeave() {
  store.setHighlightedDriver(null)
}

const deltaDriverRows = computed(() => {
  let drivers = store.activeDrivers
  if (!drivers.length) return []
  if (narrowFocusDelta.value && store.focusDriverCode) {
    const fc = store.focusDriverCode
    drivers = drivers.filter((d) => d.code === fc)
  }

  const db = store.strategyViz?.delta_breakdown
  const { showActual: showActDelta, showSim: showSimDelta } = chartVizLayers(
    store,
    'deltaBreakdown'
  )
  const showSimLayer = !!(showSimDelta && store.simulatedData)
  const saved = store.savedSimulations || {}

  const rows = []
  for (const d of drivers) {
    const act = showActDelta ? breakdownForDriver(d.code, db) : null
    const actDelta =
      act?.components?.length && act.total != null && Number.isFinite(act.total)
        ? { components: act.components, total: act.total }
        : null

    let simDelta = null
    if (showSimLayer) {
      const sd = saved[d.code]?.simDelta
      if (sd?.components?.length && sd.total != null && Number.isFinite(sd.total)) {
        simDelta = { components: sd.components, total: sd.total }
      }
    }

    if (!actDelta && !simDelta) continue

    rows.push({
      driverCode: d.code,
      driverColor: d.color,
      actualDelta: actDelta,
      simDelta,
      showActual: showActDelta && !!actDelta,
      showSim: showSimLayer && !!simDelta,
    })
  }
  return rows
})
</script>

<template>
  <div class="delta-breakdown">
    <div class="delta-head">
      <div class="delta-head-titles">
        <h3 class="panel-title">Delta Breakdown</h3>
        <p v-if="focusSummary" class="delta-focus-summary">{{ focusSummary }}</p>
      </div>
      <div class="delta-head-actions">
        <div
          v-if="store.focusDriverCode"
          class="delta-view-toggle"
          role="group"
          aria-label="Delta breakdown scope"
        >
          <button
            type="button"
            class="delta-view-toggle__btn"
            :class="{ 'delta-view-toggle__btn--active': !narrowFocusDelta }"
            @click="narrowFocusDelta = false"
          >
            All
          </button>
          <button
            type="button"
            class="delta-view-toggle__btn"
            :class="{ 'delta-view-toggle__btn--active': narrowFocusDelta }"
            @click="narrowFocusDelta = true"
          >
            Focus
          </button>
        </div>
        <button
          type="button"
          class="panel-expand panel-sim-hold"
          :disabled="!store.hasSavedSimulations"
          title="Hold to preview this chart with simulated breakdown only"
          aria-label="Hold to preview delta breakdown with simulated data only"
          @pointerdown="onSimHoldPointerDown"
          @click.prevent
        >
          Sim
        </button>
        <button
          type="button"
          class="panel-expand"
          :aria-expanded="store.expandedPanelId === 'deltaBreakdown'"
          aria-label="Expand delta breakdown panel"
          @click="store.toggleExpandedPanel('deltaBreakdown')"
        >
          Expand
        </button>
      </div>
    </div>
    <p v-if="store.raceData && store.strategyViz" class="delta-subtitle">
      Per driver: horizontal stacked bars from 0 (ordered components); accent tick = net vs actual. Sim row when saved.
    </p>
    <ul v-if="store.raceData && store.strategyViz" class="delta-legend" aria-label="Component colors">
      <li><span class="delta-legend__swatch delta-legend__swatch--pit"></span> Pit timing</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--tyre"></span> Tyre / pace</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--traffic"></span> Traffic / rejoin</li>
      <li><span class="delta-legend__swatch delta-legend__swatch--net"></span> Net (tick on bar)</li>
    </ul>
    <div
      class="chart-container"
      role="region"
      aria-label="Delta breakdown by driver"
    >
      <p v-if="!store.raceData" class="placeholder">Select a race to see the delta breakdown</p>
      <p v-else-if="!store.activeDrivers.length" class="placeholder">
        Select one or more drivers to see the delta breakdown
      </p>
      <p
        v-else-if="store.raceData && !store.strategyViz"
        class="placeholder"
      >
        Loading strategy model…
      </p>
      <p
        v-else-if="store.strategyViz && !deltaDriverRows.length"
        class="placeholder"
      >
        No breakdown — select drivers behind the leader
      </p>
      <div v-else class="delta-cells">
        <DeltaDriverCell
          v-for="row in deltaDriverRows"
          :key="row.driverCode"
          :driver-code="row.driverCode"
          :driver-color="row.driverColor"
          :actual-delta="row.actualDelta"
          :sim-delta="row.simDelta"
          :show-actual="row.showActual"
          :show-sim="row.showSim"
          :dimmed="isDeltaDimmed(row.driverCode)"
          @pointer-on="onDeltaCellEnter"
          @pointer-off="onDeltaCellLeave"
        />
      </div>
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

.delta-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  flex-shrink: 0;
}

.delta-head-titles {
  min-width: 0;
}

.delta-head-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.delta-focus-summary {
  margin: 4px 0 0 0;
  font-size: var(--text-xs);
  line-height: 1.35;
  color: var(--color-text-secondary);
  font-family: var(--font-body);
}

.delta-view-toggle {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.delta-view-toggle__btn {
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 4px 8px;
  border: none;
  background: var(--color-bg);
  color: var(--color-text-muted);
  cursor: pointer;
}

.delta-view-toggle__btn--active {
  background: var(--color-accent);
  color: #fff;
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

.chart-container {
  flex: 1 1 0;
  position: relative;
  min-height: 0;
  min-width: 0;
  max-height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
}

.delta-cells {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-bottom: var(--space-1);
}

.placeholder {
  padding: var(--space-6) var(--space-4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-muted);
  font-family: var(--font-body);
  font-size: var(--text-base);
  text-align: center;
}
</style>
