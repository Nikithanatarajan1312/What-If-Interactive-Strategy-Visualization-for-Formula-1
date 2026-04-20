<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import { useRaceStore } from './stores/raceStore'
import ControlsPanel from './components/ControlsPanel.vue'
import RaceTrace from './components/RaceTrace.vue'
import BumpChart from './components/BumpChart.vue'
import StintBar from './components/StintBar.vue'
import PitHeatmap from './components/PitHeatmap.vue'
import DeltaBreakdown from './components/DeltaBreakdown.vue'
import BoundedCanvas from './components/BoundedCanvas.vue'
import DraggableCard from './components/DraggableCard.vue'

const store = useRaceStore()

const EXPANDED_LABELS = {
  raceTrace: 'Race trace — gap to leader',
  bumpChart: 'Bump chart — positions',
  stintBar: 'Stint history',
  pitHeatmap: 'Pit window heatmap',
  deltaBreakdown: 'Delta breakdown',
}

const expandedPanelLabel = computed(() => {
  const id = store.expandedPanelId
  return id ? EXPANDED_LABELS[id] || '' : ''
})

function closeExpanded() {
  store.setExpandedPanel(null)
}

/** Basic-mode per-panel heights (user-resizable via bottom drag handle). */
const basicHeights = reactive({
  raceTrace: 380,
  bumpChart: 380,
  stintBar: 340,
  pitHeatmap: 340,
  deltaBreakdown: 320,
})

const basicPanelStyles = computed(() =>
  Object.fromEntries(
    Object.entries(basicHeights).map(([id, h]) => [id, { height: `${h}px` }])
  )
)

const basicResize = {
  active: false,
  id: null,
  pointerId: null,
  startY: 0,
  startH: 0,
}

function onBasicResizeDown(e, id) {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  basicResize.active = true
  basicResize.id = id
  basicResize.pointerId = e.pointerId
  basicResize.startY = e.clientY
  basicResize.startH = basicHeights[id]
  try {
    e.currentTarget.setPointerCapture?.(e.pointerId)
  } catch {}
  window.addEventListener('pointermove', onBasicResizeMove)
  window.addEventListener('pointerup', onBasicResizeUp)
  window.addEventListener('pointercancel', onBasicResizeUp)
  e.preventDefault()
}

function onBasicResizeMove(e) {
  if (!basicResize.active || e.pointerId !== basicResize.pointerId) return
  const dy = e.clientY - basicResize.startY
  basicHeights[basicResize.id] = Math.max(200, basicResize.startH + dy)
}

function onBasicResizeUp(e) {
  if (!basicResize.active) return
  if (e.pointerId !== basicResize.pointerId) return
  basicResize.active = false
  basicResize.id = null
  basicResize.pointerId = null
  window.removeEventListener('pointermove', onBasicResizeMove)
  window.removeEventListener('pointerup', onBasicResizeUp)
  window.removeEventListener('pointercancel', onBasicResizeUp)
}

/** Pro-mode default layout — staggered around (0, 0) so cards do not overlap. */
const PRO_DEFAULT_LAYOUT = {
  raceTrace:      { title: 'Race trace',      x: -620, y: -380, width: 600, height: 360 },
  bumpChart:      { title: 'Position flow',   x: 20,   y: -380, width: 600, height: 360 },
  stintBar:       { title: 'Stint history',   x: -620, y: 0,    width: 600, height: 360 },
  pitHeatmap:     { title: 'Pit heatmap',     x: 20,   y: 0,    width: 600, height: 360 },
  deltaBreakdown: { title: 'Delta breakdown', x: -300, y: 380,  width: 920, height: 340 },
}

const proCards = reactive(
  Object.fromEntries(
    Object.entries(PRO_DEFAULT_LAYOUT).map(([id, c]) => [
      id,
      { x: c.x, y: c.y, width: c.width, height: c.height },
    ])
  )
)

function resetProLayout() {
  for (const [id, c] of Object.entries(PRO_DEFAULT_LAYOUT)) {
    proCards[id].x = c.x
    proCards[id].y = c.y
    proCards[id].width = c.width
    proCards[id].height = c.height
  }
}

watch(
  () => store.viewMode,
  (mode, prev) => {
    if (mode === 'pro' && prev !== 'pro') resetProLayout()
  }
)

function setViewMode(mode) {
  store.setViewMode(mode)
}

onMounted(() => {
  store.bootstrap()
})
</script>

<template>
  <div
    class="app"
    :class="{
      'app--expanded': !!store.expandedPanelId && store.viewMode === 'basic',
      'app--pro': store.viewMode === 'pro',
    }"
  >
    <header class="app-header" role="banner">
      <div class="app-brand">
        <h1 class="app-title">What If<span class="app-title__q">?</span></h1>
        <span class="app-subtitle">Interactive F1 Strategy Visualization</span>
      </div>
      <div class="app-header-actions">
        <div
          class="view-mode-toggle"
          role="radiogroup"
          aria-label="Workspace view mode"
        >
          <button
            type="button"
            role="radio"
            :aria-checked="store.viewMode === 'basic'"
            class="view-mode-toggle__btn"
            :class="{ 'view-mode-toggle__btn--active': store.viewMode === 'basic' }"
            @click="setViewMode('basic')"
          >
            Basic
          </button>
          <button
            type="button"
            role="radio"
            :aria-checked="store.viewMode === 'pro'"
            class="view-mode-toggle__btn"
            :class="{ 'view-mode-toggle__btn--active': store.viewMode === 'pro' }"
            @click="setViewMode('pro')"
          >
            Pro
          </button>
        </div>
        <a
          class="app-about"
          href="/about.html"
          target="_blank"
          rel="noopener noreferrer"
        >
          About
        </a>
        <div class="app-meta" v-if="store.raceData" aria-label="Race info">
          <span class="race-badge">{{ store.raceData.race?.name }}</span>
          <span class="race-laps" aria-label="Total laps">{{ store.totalLaps }} Laps</span>
        </div>
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

    <main
      id="main-dashboard"
      v-if="store.raceData && store.viewMode === 'pro'"
      class="dashboard dashboard--pro"
      aria-label="Race strategy dashboard, pro canvas"
    >
      <BoundedCanvas>
        <DraggableCard
          v-for="(meta, id) in PRO_DEFAULT_LAYOUT"
          :key="id"
          :card-id="id"
          :title="meta.title"
          :x="proCards[id].x"
          :y="proCards[id].y"
          :width="proCards[id].width"
          :height="proCards[id].height"
          :aria-label="meta.title"
          @update:x="(v) => (proCards[id].x = v)"
          @update:y="(v) => (proCards[id].y = v)"
          @update:width="(v) => (proCards[id].width = v)"
          @update:height="(v) => (proCards[id].height = v)"
        >
          <RaceTrace v-if="id === 'raceTrace'" />
          <BumpChart v-else-if="id === 'bumpChart'" />
          <StintBar v-else-if="id === 'stintBar'" />
          <PitHeatmap v-else-if="id === 'pitHeatmap'" />
          <DeltaBreakdown v-else-if="id === 'deltaBreakdown'" />
        </DraggableCard>
      </BoundedCanvas>
    </main>

    <main
      id="main-dashboard"
      v-else-if="store.raceData"
      :class="store.expandedPanelId ? 'dashboard dashboard--expanded' : 'dashboard'"
      aria-label="Race strategy dashboard"
    >
      <template v-if="store.expandedPanelId">
        <div class="dashboard-expanded-bar">
          <button type="button" class="dashboard-expanded-back" @click="closeExpanded">
            Back to dashboard
          </button>
          <span class="dashboard-expanded-title" aria-live="polite">{{ expandedPanelLabel }}</span>
        </div>
        <section
          v-if="store.expandedPanelId === 'raceTrace'"
          class="panel panel--expanded panel--race-trace"
          aria-label="Race trace chart: gap to leader over laps"
        >
          <RaceTrace />
        </section>
        <section
          v-else-if="store.expandedPanelId === 'bumpChart'"
          class="panel panel--expanded panel--bump-chart"
          aria-label="Position flow chart: driver positions over laps"
        >
          <BumpChart />
        </section>
        <section
          v-else-if="store.expandedPanelId === 'stintBar'"
          class="panel panel--expanded panel--stint-bar"
          aria-label="Stint history: tyre strategies per driver"
        >
          <StintBar />
        </section>
        <section
          v-else-if="store.expandedPanelId === 'pitHeatmap'"
          class="panel panel--expanded panel--heatmap"
          aria-label="Pit window heatmap: predicted gain or loss per lap"
        >
          <PitHeatmap />
        </section>
        <section
          v-else-if="store.expandedPanelId === 'deltaBreakdown'"
          class="panel panel--expanded panel--delta"
          aria-label="Delta breakdown: time gap decomposition by factor"
        >
          <DeltaBreakdown />
        </section>
      </template>
      <template v-else>
        <div class="dashboard-row dashboard-row--top">
          <section
            class="panel panel--resizable panel--race-trace"
            :style="basicPanelStyles.raceTrace"
            aria-label="Race trace chart: gap to leader over laps"
          >
            <RaceTrace />
            <div
              class="panel-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize race trace panel height"
              @pointerdown="(e) => onBasicResizeDown(e, 'raceTrace')"
            ></div>
          </section>
          <section
            class="panel panel--resizable panel--bump-chart"
            :style="basicPanelStyles.bumpChart"
            aria-label="Position flow chart: driver positions over laps"
          >
            <BumpChart />
            <div
              class="panel-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize position flow panel height"
              @pointerdown="(e) => onBasicResizeDown(e, 'bumpChart')"
            ></div>
          </section>
        </div>
        <div class="dashboard-row dashboard-row--mid">
          <section
            class="panel panel--resizable panel--stint-bar"
            :style="basicPanelStyles.stintBar"
            aria-label="Stint history: tyre strategies per driver"
          >
            <StintBar />
            <div
              class="panel-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize stint history panel height"
              @pointerdown="(e) => onBasicResizeDown(e, 'stintBar')"
            ></div>
          </section>
          <section
            class="panel panel--resizable panel--heatmap"
            :style="basicPanelStyles.pitHeatmap"
            aria-label="Pit window heatmap: predicted gain or loss per lap"
          >
            <PitHeatmap />
            <div
              class="panel-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize pit heatmap panel height"
              @pointerdown="(e) => onBasicResizeDown(e, 'pitHeatmap')"
            ></div>
          </section>
        </div>
        <div class="dashboard-row dashboard-row--bottom">
          <section
            class="panel panel--resizable panel--delta"
            :style="basicPanelStyles.deltaBreakdown"
            aria-label="Delta breakdown: time gap decomposition by factor"
          >
            <DeltaBreakdown />
            <div
              class="panel-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize delta breakdown panel height"
              @pointerdown="(e) => onBasicResizeDown(e, 'deltaBreakdown')"
            ></div>
          </section>
        </div>
      </template>
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
  overflow-x: hidden;
}

/* Lock viewport only when a chart is expanded so the panel can fill the screen. */
.app--expanded {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
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

.app-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-shrink: 0;
}

.app-about {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  text-decoration: none;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  transition: color var(--duration-normal) var(--ease-out),
    border-color var(--duration-normal) var(--ease-out),
    background var(--duration-normal) var(--ease-out);
}

.app-about:hover {
  color: var(--color-text);
  border-color: var(--color-border);
  background: var(--color-bg);
}

.app-about:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
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
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  padding-bottom: var(--space-4);
}

.app--pro {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

.dashboard--pro {
  flex: 1;
  min-height: 0;
  display: flex;
  padding: var(--space-3) var(--space-4);
  padding-bottom: var(--space-4);
}

.view-mode-toggle {
  display: inline-flex;
  align-items: stretch;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  padding: 2px;
  gap: 2px;
}

.view-mode-toggle__btn {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  border-radius: calc(var(--radius-sm) - 2px);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
  transition: color var(--duration-normal) var(--ease-out),
    background var(--duration-normal) var(--ease-out);
}

.view-mode-toggle__btn:hover {
  color: var(--color-text);
}

.view-mode-toggle__btn--active {
  color: var(--color-text);
  background: var(--color-surface);
  box-shadow: inset 0 0 0 1px var(--color-border);
}

.view-mode-toggle__btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.dashboard--expanded {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding-bottom: var(--space-4);
}

.dashboard-expanded-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.dashboard-expanded-back {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
}

.dashboard-expanded-back:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.dashboard-expanded-back:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.dashboard-expanded-title {
  font-family: var(--font-display);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.panel--expanded {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dashboard-row {
  display: grid;
  gap: var(--space-2);
  min-height: 0;
  /* Each panel sets its own height (user-resizable via .panel-resizer). */
  align-items: start;
}

.dashboard-row--top {
  grid-template-columns: 3fr 2fr;
}

.dashboard-row--mid {
  grid-template-columns: 3fr 2fr;
}

.panel.panel--stint-bar {
  min-height: 200px;
}

.dashboard-row--bottom {
  grid-template-columns: 1fr;
}

.panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-2);
  overflow: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
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

.panel--delta {
  box-sizing: border-box;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel--resizable {
  position: relative;
  padding-bottom: calc(var(--space-2) + 6px);
}

.panel-resizer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 6px;
  cursor: ns-resize;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    transparent 35%,
    var(--color-border) 35%,
    var(--color-border) 65%,
    transparent 65%
  );
  background-size: 32px 100%;
  background-repeat: no-repeat;
  background-position: center;
  opacity: 0.6;
  transition: opacity var(--duration-fast) var(--ease-out),
    background-color var(--duration-fast) var(--ease-out);
  touch-action: none;
  user-select: none;
}

.panel-resizer:hover {
  opacity: 1;
  background-color: rgba(225, 6, 0, 0.08);
}

.panel-resizer:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: -2px;
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
