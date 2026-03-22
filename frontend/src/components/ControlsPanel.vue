<script setup>
import { useRaceStore } from '../stores/raceStore'

const store = useRaceStore()

function onRaceChange(e) {
  const val = e.target.value
  if (!val) return
  const [year, round] = val.split('-')
  store.loadRace(Number(year), Number(round))
}

function onDriverHover(code) {
  store.setHighlightedDriver(code)
}

function onDriverLeave() {
  store.setHighlightedDriver(null)
}

function onRunSimulation() {
  if (!store.modifiedStrategy) return
  store.simulate(store.modifiedStrategy)
}

function onResetStrategy() {
  store.modifiedStrategy = null
  store.resetStrategy()
}

function isDriverActive(code) {
  return store.selectedDrivers.length === 0 || store.selectedDrivers.includes(code)
}
</script>

<template>
  <div class="controls" role="toolbar" aria-label="Dashboard controls">
    <div class="controls-group">
      <label class="control-label" for="race-select" id="race-label">Race</label>
      <select
        id="race-select"
        class="control-select"
        aria-labelledby="race-label"
        @change="onRaceChange"
      >
        <option value="">Select a race…</option>
        <option
          v-for="race in store.availableRaces"
          :key="`${race.year}-${race.round}`"
          :value="`${race.year}-${race.round}`"
        >
          {{ race.year }} {{ race.name }}
        </option>
      </select>
    </div>

    <div class="controls-group" v-if="store.drivers.length">
      <span class="control-label" id="drivers-label">Drivers</span>
      <div
        class="driver-chips"
        role="group"
        aria-labelledby="drivers-label"
      >
        <button
          v-for="driver in store.drivers"
          :key="driver.code"
          class="driver-chip"
          :class="{
            active: isDriverActive(driver.code),
            highlighted: store.highlightedDriver === driver.code,
          }"
          :style="{ '--driver-color': driver.color }"
          :aria-pressed="isDriverActive(driver.code)"
          :aria-label="`${driver.code} — ${isDriverActive(driver.code) ? 'visible' : 'hidden'}`"
          @click="store.toggleDriver(driver.code)"
          @mouseenter="onDriverHover(driver.code)"
          @mouseleave="onDriverLeave"
          @focus="onDriverHover(driver.code)"
          @blur="onDriverLeave"
        >
          {{ driver.code }}
        </button>
      </div>
    </div>

    <div class="controls-group controls-group--actions" v-if="store.raceData">
      <button
        v-if="store.modifiedStrategy && !store.simulatedData"
        class="control-btn control-btn--simulate"
        :disabled="store.loading"
        @click="onRunSimulation"
        aria-label="Run what-if simulation with modified pit strategy"
      >
        Run Simulation
      </button>
      <button
        v-if="store.modifiedStrategy"
        class="control-btn control-btn--reset"
        @click="onResetStrategy"
        aria-label="Reset modified pit strategy to original"
      >
        Reset Strategy
      </button>
      <label class="control-toggle" v-if="store.simulatedData">
        <input
          type="checkbox"
          v-model="store.showSimulated"
          aria-label="Toggle simulated overlay"
        />
        <span class="toggle-label">Show Simulated</span>
      </label>
    </div>

    <div
      class="controls-status"
      v-if="store.loading"
      role="status"
      aria-live="polite"
    >
      <span class="spinner" aria-hidden="true"></span>
      Loading…
    </div>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-3) var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.controls-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.control-label {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
}

.control-select {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-body);
  font-size: var(--text-base);
  cursor: pointer;
  transition: border-color var(--duration-fast);
}

.control-select:hover {
  border-color: var(--color-border-hover);
}

.driver-chips {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.driver-chip {
  padding: 3px 10px;
  border: 2px solid var(--driver-color, var(--color-border));
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.driver-chip.active {
  background: var(--driver-color, var(--color-accent));
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.driver-chip.highlighted {
  box-shadow: 0 0 0 2px var(--driver-color), 0 0 10px var(--driver-color);
  transform: scale(1.08);
}

.driver-chip[aria-pressed="false"] {
  opacity: 0.45;
}

.control-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-body);
  font-size: var(--text-base);
  color: var(--color-text);
  cursor: pointer;
}

.toggle-label {
  user-select: none;
}

.control-btn {
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.control-btn:hover:not(:disabled) {
  background: var(--color-surface-hover);
  border-color: var(--color-border-hover);
}

.control-btn--simulate {
  border-color: var(--color-success, #27c93f);
  color: var(--color-success, #27c93f);
  font-weight: 700;
}

.control-btn--simulate:hover:not(:disabled) {
  background: rgba(39, 201, 63, 0.12);
}

.control-btn--reset {
  border-color: var(--color-accent);
  color: var(--color-accent-text);
}

.control-btn--reset:hover {
  background: rgba(225, 6, 0, 0.12);
}

.control-btn:disabled,
.driver-chip:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.controls-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-body);
  font-size: var(--text-sm);
  color: var(--color-accent-text);
}

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
