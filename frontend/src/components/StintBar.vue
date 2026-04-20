<script setup>
import { computed } from 'vue'
import { useRaceStore } from '../stores/raceStore'
import { chartVizLayers, useSimHoldPreview } from '../composables/useSimHoldPreview'
import StintDriverCell from './StintDriverCell.vue'

const store = useRaceStore()
const { onSimHoldPointerDown } = useSimHoldPreview(store, 'stintBar')

function getDriverStrategy(driver) {
  if (store.modifiedStrategy && store.modifiedStrategy.driverCode === driver.code) {
    return store.modifiedStrategy.pitStops
  }
  const saved = store.savedSimulations?.[driver.code]
  if (saved?.strategy?.pitStops) return saved.strategy.pitStops
  return driver.pitStops
}

function isStintDimmed(code) {
  const h = store.highlightedDriver
  const f = store.focusDriverCode
  if (h && h !== code) return true
  if (f && f !== code) return true
  return false
}

const totalLaps = computed(() => {
  if (store.totalLaps) return store.totalLaps
  const laps = store.activeDrivers.flatMap((d) => d.laps.map((l) => l.lap))
  return laps.length ? Math.max(...laps) : 1
})

const stintRows = computed(() => {
  const drivers = store.activeDrivers
  if (!drivers.length) return []

  const { showActual, showSim: showSimViz } = chartVizLayers(store, 'stintBar')
  const showSimLayer = !!(showSimViz && store.simulatedData?.drivers?.length)
  const simOnly = !showActual && showSimLayer

  if (!showActual && !showSimLayer) return []

  const rows = drivers.map((driver) => {
    const pitStops = getDriverStrategy(driver)
    const simDriver =
      store.simulatedData?.drivers?.find((s) => s.code === driver.code) || null
    return {
      driver,
      pitStops,
      originalPitStops: driver.pitStops || [],
      simDriver,
      showActual,
      showSimLayer,
      simOnly,
    }
  })

  if (simOnly) return rows.filter((r) => r.simDriver)
  return rows
})
</script>

<template>
  <div class="stint-bar">
    <div class="panel-header">
      <h3 class="panel-title">
        Stint History
        <span class="panel-hint">Drag pit markers to change strategy</span>
      </h3>
      <div class="panel-header-actions">
        <span
          class="modified-badge"
          v-if="store.modifiedStrategy || store.savedSimulationCodes.length"
          role="status"
          aria-live="polite"
        >{{ store.savedSimulationCodes.length ? 'Strategy / sim saved' : 'Strategy Modified' }}</span>
        <button
          type="button"
          class="panel-expand panel-sim-hold"
          :disabled="!store.hasSavedSimulations"
          title="Hold to preview this chart with simulated data only"
          aria-label="Hold to preview stint history with simulated data only"
          @pointerdown="onSimHoldPointerDown"
          @click.prevent
        >
          Sim
        </button>
        <button
          type="button"
          class="panel-expand"
          :aria-expanded="store.expandedPanelId === 'stintBar'"
          aria-label="Expand stint history panel"
          @click="store.toggleExpandedPanel('stintBar')"
        >
          Expand
        </button>
      </div>
    </div>
    <div class="chart-container" role="region" aria-label="Tyre stint bars per driver">
      <p v-if="!store.raceData" class="placeholder">Select a race to view stints</p>
      <p v-else-if="!store.activeDrivers.length" class="placeholder">
        Select one or more drivers to view stints
      </p>
      <div v-else class="stint-cells">
        <StintDriverCell
          v-for="row in stintRows"
          :key="row.driver.code"
          :driver="row.driver"
          :pit-stops="row.pitStops"
          :original-pit-stops="row.originalPitStops"
          :sim-driver="row.simDriver"
          :total-laps="totalLaps"
          :show-actual="row.showActual"
          :show-sim-layer="row.showSimLayer"
          :sim-only="row.simOnly"
          :dimmed="isStintDimmed(row.driver.code)"
        />
      </div>
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
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.chart-container {
  flex: 1 1 0;
  position: relative;
  min-height: 0;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.stint-cells {
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
