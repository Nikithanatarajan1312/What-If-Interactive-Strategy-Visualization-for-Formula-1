<script setup>
import { onMounted } from 'vue'
import { useRaceStore } from './stores/raceStore'
import ControlsPanel from './components/ControlsPanel.vue'
import RaceTrace from './components/RaceTrace.vue'
import BumpChart from './components/BumpChart.vue'
import StintBar from './components/StintBar.vue'
import PitHeatmap from './components/PitHeatmap.vue'
import DeltaBreakdown from './components/DeltaBreakdown.vue'

const store = useRaceStore()

onMounted(() => {
  store.loadAvailableRaces()
})
</script>

<template>
  <div class="app">
    <header class="app-header" role="banner">
      <div class="app-brand">
        <h1 class="app-title">What If<span class="app-title__q">?</span></h1>
        <span class="app-subtitle">Interactive F1 Strategy Visualization</span>
      </div>
      <div class="app-meta" v-if="store.raceData" aria-label="Race info">
        <span class="race-badge">{{ store.raceData.race?.name }}</span>
        <span class="race-laps" aria-label="Total laps">{{ store.totalLaps }} Laps</span>
      </div>
    </header>

    <nav aria-label="Race controls">
      <ControlsPanel />
    </nav>

    <div
      class="loading-overlay"
      v-if="store.loading"
      role="status"
      aria-live="polite"
      aria-label="Loading race data"
    >
      <div class="loading-spinner" aria-hidden="true"></div>
      <span>Loading race data…</span>
    </div>

    <div
      class="error-banner"
      v-if="store.error"
      role="alert"
      aria-live="assertive"
    >
      <span class="error-banner__icon" aria-hidden="true">⚠</span>
      {{ store.error }}
    </div>

    <main id="main-dashboard" class="dashboard" v-if="store.raceData" aria-label="Race strategy dashboard">
      <div class="dashboard-row dashboard-row--top">
        <section class="panel panel--race-trace" aria-label="Race trace chart: gap to leader over laps">
          <RaceTrace />
        </section>
        <section class="panel panel--bump-chart" aria-label="Position flow chart: driver positions over laps">
          <BumpChart />
        </section>
      </div>
      <div class="dashboard-row dashboard-row--mid">
        <section class="panel panel--stint-bar" aria-label="Stint history: tyre strategies per driver">
          <StintBar />
        </section>
        <section class="panel panel--heatmap" aria-label="Pit window heatmap: predicted gain or loss per lap">
          <PitHeatmap />
        </section>
      </div>
      <div class="dashboard-row dashboard-row--bottom">
        <section class="panel panel--delta" aria-label="Delta breakdown: time gap decomposition by factor">
          <DeltaBreakdown />
        </section>
      </div>
    </main>

    <main id="main-dashboard" class="empty-state" v-else-if="!store.loading" aria-label="Welcome">
      <div class="empty-flag" aria-hidden="true">
        <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
          <rect x="2" y="8" width="12" height="12" fill="#e10600"/>
          <rect x="14" y="8" width="12" height="12" fill="#e8eaef"/>
          <rect x="26" y="8" width="12" height="12" fill="#e10600"/>
          <rect x="2" y="20" width="12" height="12" fill="#e8eaef"/>
          <rect x="14" y="20" width="12" height="12" fill="#e10600"/>
          <rect x="26" y="20" width="12" height="12" fill="#e8eaef"/>
          <rect x="2" y="32" width="12" height="12" fill="#e10600"/>
          <rect x="14" y="32" width="12" height="12" fill="#e8eaef"/>
          <rect x="26" y="32" width="12" height="12" fill="#e10600"/>
          <rect x="44" y="8" width="4" height="48" rx="2" fill="#3d4260"/>
        </svg>
      </div>
      <h2 class="empty-title">Select a race to begin</h2>
      <p class="empty-desc">Choose a Grand Prix from the dropdown above to visualize pit strategies and explore what-if scenarios.</p>
    </main>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-6);
  border-bottom: 2px solid var(--color-accent);
  background: var(--color-surface);
}

.app-brand {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.app-title {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: 900;
  color: var(--color-text);
  margin: 0;
  letter-spacing: -0.02em;
  text-transform: uppercase;
}

.app-title__q {
  color: var(--color-accent);
}

.app-subtitle {
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 400;
  color: var(--color-text-secondary);
  letter-spacing: 0.02em;
}

.app-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.race-badge {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text);
  background: var(--color-bg);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.race-laps {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.loading-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-8);
  color: var(--color-text-secondary);
  font-family: var(--font-body);
  font-size: var(--text-base);
}

.loading-spinner {
  width: 22px;
  height: 22px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  background: rgba(255, 107, 107, 0.1);
  border-bottom: 1px solid rgba(255, 107, 107, 0.25);
  color: var(--color-danger);
  font-family: var(--font-body);
  font-size: var(--text-base);
  font-weight: 500;
}

.error-banner__icon {
  font-size: var(--text-md);
}

.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  padding-bottom: var(--space-8);
  flex: 1;
}

.dashboard-row {
  display: grid;
  gap: var(--space-3);
}

.dashboard-row--top {
  grid-template-columns: 3fr 2fr;
  height: 380px;
}

.dashboard-row--mid {
  grid-template-columns: 3fr 2fr;
  height: 240px;
}

.dashboard-row--bottom {
  grid-template-columns: 1fr;
  height: 220px;
}

.panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  overflow: hidden;
  transition: border-color var(--duration-normal) var(--ease-out),
              box-shadow var(--duration-normal) var(--ease-out);
}

.panel:hover {
  border-color: var(--color-border-hover);
}

.panel:focus-within {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px var(--space-6);
  text-align: center;
  flex: 1;
}

.empty-flag {
  margin-bottom: var(--space-5);
  opacity: 0.6;
}

.empty-title {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 var(--space-2) 0;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.empty-desc {
  font-family: var(--font-body);
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  max-width: 420px;
  line-height: 1.7;
}
</style>
