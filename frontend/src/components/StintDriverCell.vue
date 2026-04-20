<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useRaceStore } from '../stores/raceStore'
import { useTooltip } from '../composables/useTooltip'
import {
  COMPOUND_COLORS,
  buildStints,
  stintLayout,
  pitLayoutPct,
} from '../utils/stintUtils'

const props = defineProps({
  driver: { type: Object, required: true },
  /** Editable strategy pits (modified / saved sim / race copy). */
  pitStops: { type: Array, required: true },
  /** Baseline race pits — bottom band only, never edited here. */
  originalPitStops: { type: Array, required: true },
  simDriver: { type: Object, default: null },
  totalLaps: { type: Number, required: true },
  showActual: { type: Boolean, default: true },
  showSimLayer: { type: Boolean, default: false },
  simOnly: { type: Boolean, default: false },
  dimmed: { type: Boolean, default: false },
})

const store = useRaceStore()
const tooltip = useTooltip()
/** Top band: sim and/or strategy handles (lap → X mapping). */
const topTrackRef = ref(null)
const dragging = ref(null)

const isEditing = computed(() => store.modifiedStrategy?.driverCode === props.driver.code)
const hasSavedSim = computed(() => !!store.savedSimulations?.[props.driver.code])
const showStrategyStyle = computed(() => isEditing.value || hasSavedSim.value)

const showSimVisual = computed(
  () => !!props.simDriver && (props.showSimLayer || props.simOnly)
)

/** Strategy row on top when no sim to draw but user still edits race-based strategy. */
const showStrategyOnTop = computed(
  () => props.showActual && !props.simOnly && !showSimVisual.value
)

const originalStints = computed(() =>
  buildStints(props.driver, props.originalPitStops || [], props.totalLaps)
)
const originalLayout = computed(() => stintLayout(originalStints.value, props.totalLaps))

const strategyStints = computed(() =>
  buildStints(props.driver, props.pitStops, props.totalLaps)
)
const strategyLayout = computed(() => stintLayout(strategyStints.value, props.totalLaps))

const simStints = computed(() => {
  if (!props.simDriver) return []
  return buildStints(props.simDriver, props.simDriver.pitStops, props.totalLaps)
})
const simLayout = computed(() => stintLayout(simStints.value, props.totalLaps))

const originalPitLapsLabel = computed(() => {
  const pits = props.originalPitStops || []
  if (!pits.length) return 'No pit stops in race data'
  return pits
    .map((p) => `L${p.lap}`)
    .join(' · ')
})

const topBandLabel = computed(() => {
  if (showSimVisual.value) return 'Simulated'
  if (showStrategyOnTop.value) return 'Strategy'
  return ''
})

const editableHandles = computed(
  () => props.showActual && !props.simOnly
)

function compoundFill(c) {
  return COMPOUND_COLORS[c] || '#888'
}

function lapFromClientX(clientX) {
  const el = topTrackRef.value
  if (!el) return props.totalLaps
  const r = el.getBoundingClientRect()
  const t = (clientX - r.left) / Math.max(1, r.width)
  const span = Math.max(1, props.totalLaps - 1)
  return Math.round(1 + Math.max(0, Math.min(1, t)) * span)
}

function applyPitMove(pitIdx, newLap) {
  const clamped = Math.max(2, Math.min(props.totalLaps - 1, newLap))
  const currentPits = props.pitStops.map((p) => ({ ...p }))
  currentPits[pitIdx] = { ...currentPits[pitIdx], lap: clamped }
  currentPits.sort((a, b) => a.lap - b.lap)
  void store.applyPitStrategyChange({
    driverCode: props.driver.code,
    pitStops: currentPits,
  })
}

function onWindowPointerMove(e) {
  const d = dragging.value
  if (!d || e.pointerId !== d.pointerId) return
  applyPitMove(d.pitIdx, lapFromClientX(e.clientX))
}

function endWindowDrag(e) {
  const d = dragging.value
  if (!d || e.pointerId !== d.pointerId) return
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', endWindowDrag)
  window.removeEventListener('pointercancel', endWindowDrag)
  dragging.value = null
}

function onPitPointerDown(e, pitIdx) {
  if (!editableHandles.value) return
  e.preventDefault()
  e.stopPropagation()
  dragging.value = { pitIdx, pointerId: e.pointerId }
  window.addEventListener('pointermove', onWindowPointerMove)
  window.addEventListener('pointerup', endWindowDrag)
  window.addEventListener('pointercancel', endWindowDrag)
}

function onCellEnter() {
  store.setHighlightedDriver(props.driver.code)
}

function onCellLeave() {
  store.setHighlightedDriver(null)
}

function stintTooltip(stint, kind) {
  const tag = kind === 'race' ? 'Race' : kind === 'sim' ? 'Sim' : 'Strategy'
  return `<strong style="color:${props.driver.color}">${props.driver.code}</strong> · ${tag}<br/>
    ${stint.compound} · Laps ${stint.startLap}–${stint.endLap}
    (${stint.endLap - stint.startLap + 1} laps)`
}

function pitTooltip(pit) {
  const dur = pit.duration_s != null && Number.isFinite(pit.duration_s)
    ? Number(pit.duration_s).toFixed(1)
    : '—'
  return `<strong style="color:${props.driver.color}">${props.driver.code}</strong>
    Strategy pit Lap ${pit.lap}<br/>
    ${pit.fromCompound} → ${pit.toCompound} · ${dur}s<br/>
    <em style="color:var(--color-text-muted)">Drag to move (bottom row shows race pits)</em>`
}

onUnmounted(() => {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', endWindowDrag)
  window.removeEventListener('pointercancel', endWindowDrag)
})
</script>

<template>
  <article
    class="stint-driver-cell"
    :class="{ 'stint-driver-cell--dimmed': dimmed }"
    role="group"
    :aria-label="`Stint history for ${driver.code}`"
    @mouseenter="onCellEnter"
    @mouseleave="onCellLeave"
  >
    <header class="stint-driver-cell__head">
      <span class="stint-driver-cell__code" :style="{ color: driver.color }">
        {{ driver.code }}
        <span v-if="isEditing" class="stint-driver-cell__badge" title="Editing">●</span>
        <span v-else-if="hasSavedSim" class="stint-driver-cell__badge" title="Saved sim">◆</span>
      </span>
    </header>

    <!-- Top: simulated (and/or strategy when no sim); pit handles = strategy -->
    <div
      v-if="showSimVisual || showStrategyOnTop"
      class="stint-driver-cell__band"
    >
      <div class="stint-driver-cell__band-label">{{ topBandLabel }}</div>
      <div ref="topTrackRef" class="stint-driver-cell__track">
        <div class="stint-driver-cell__track-bg" />
        <template v-if="showSimVisual">
          <div
            v-for="(seg, i) in simLayout"
            :key="'sim-' + i"
            class="stint-driver-cell__stint stint-driver-cell__stint--sim"
            :style="{
              left: seg.leftPct + '%',
              width: seg.widthPct + '%',
              background: compoundFill(seg.compound),
            }"
            @mouseenter="(e) => { tooltip.show(stintTooltip(seg, 'sim')); tooltip.move(e) }"
            @mousemove="(e) => tooltip.move(e)"
            @mouseleave="() => tooltip.hide()"
          />
          <div
            v-for="(pit, pi) in simDriver.pitStops"
            :key="'simpl-' + pi"
            class="stint-driver-cell__pit-line stint-driver-cell__pit-line--sim"
            :style="{ left: pitLayoutPct(pit.lap, totalLaps) + '%' }"
          />
        </template>
        <template v-else-if="showStrategyOnTop">
          <div
            v-for="(seg, i) in strategyLayout"
            :key="'st-' + i"
            class="stint-driver-cell__stint"
            :class="{ 'stint-driver-cell__stint--strategy': showStrategyStyle }"
            :style="{
              left: seg.leftPct + '%',
              width: seg.widthPct + '%',
              background: compoundFill(seg.compound),
              borderColor: driver.color,
            }"
            @mouseenter="(e) => { tooltip.show(stintTooltip(seg, 'strategy')); tooltip.move(e) }"
            @mousemove="(e) => tooltip.move(e)"
            @mouseleave="() => tooltip.hide()"
          />
        </template>
        <template v-if="editableHandles && pitStops.length">
          <template v-for="(pit, pitIdx) in pitStops" :key="'ph-' + pitIdx">
            <div
              class="stint-driver-cell__pit-line"
              :style="{ left: pitLayoutPct(pit.lap, totalLaps) + '%' }"
            />
            <button
              type="button"
              class="stint-driver-cell__pit-handle"
              :style="{
                left: pitLayoutPct(pit.lap, totalLaps) + '%',
                borderColor: isEditing ? 'var(--color-accent)' : driver.color,
                background: isEditing ? 'var(--color-accent)' : '#fff',
              }"
              :aria-label="`${driver.code} strategy pit lap ${pit.lap}, drag to move`"
              @pointerdown="(e) => onPitPointerDown(e, pitIdx)"
              @mouseenter="(e) => { tooltip.show(pitTooltip(pit)); tooltip.move(e) }"
              @mousemove="(e) => tooltip.move(e)"
              @mouseleave="() => tooltip.hide()"
            />
          </template>
        </template>
        <div
          v-if="store.hoveredLap != null"
          class="stint-driver-cell__hover-line"
          :style="{ left: pitLayoutPct(store.hoveredLap, totalLaps) + '%' }"
        />
      </div>
    </div>

    <!-- Bottom: real race stints + fixed original pit lap list (read-only) -->
    <div
      v-if="(showActual || simOnly) && (originalPitStops?.length || originalLayout.length)"
      class="stint-driver-cell__band stint-driver-cell__band--race"
    >
      <div class="stint-driver-cell__band-label">Race (original pits)</div>
      <div class="stint-driver-cell__track stint-driver-cell__track--race">
        <div class="stint-driver-cell__track-bg" />
        <div
          v-for="(seg, i) in originalLayout"
          :key="'race-' + i"
          class="stint-driver-cell__stint stint-driver-cell__stint--race"
          :style="{
            left: seg.leftPct + '%',
            width: seg.widthPct + '%',
            background: compoundFill(seg.compound),
            borderColor: 'rgba(255,255,255,0.35)',
          }"
          @mouseenter="(e) => { tooltip.show(stintTooltip(seg, 'race')); tooltip.move(e) }"
          @mousemove="(e) => tooltip.move(e)"
          @mouseleave="() => tooltip.hide()"
        />
        <div
          v-for="(pit, ri) in originalPitStops"
          :key="'rpl-' + ri"
          class="stint-driver-cell__pit-line stint-driver-cell__pit-line--race"
          :style="{ left: pitLayoutPct(pit.lap, totalLaps) + '%' }"
        />
        <div
          v-if="store.hoveredLap != null"
          class="stint-driver-cell__hover-line"
          :style="{ left: pitLayoutPct(store.hoveredLap, totalLaps) + '%' }"
        />
      </div>
      <p class="stint-driver-cell__original-pits" aria-label="Original race pit laps">
        <span class="stint-driver-cell__original-pits-label">Pit laps (race):</span>
        {{ originalPitLapsLabel }}
      </p>
    </div>

    <p class="stint-driver-cell__axis" aria-hidden="true">
      L1 … L{{ totalLaps }}
    </p>
  </article>
</template>

<style scoped>
.stint-driver-cell {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: 0;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom-width: 0;
  transition: opacity var(--duration-normal) var(--ease-out);
}

/* Last cell in a stack closes the bottom border. */
.stint-driver-cell:last-child {
  border-bottom-width: 1px;
}

.stint-driver-cell--dimmed {
  opacity: 0.22 !important;
}

.stint-driver-cell__head {
  margin-bottom: var(--space-1);
}

.stint-driver-cell__code {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 800;
  letter-spacing: 0.06em;
}

.stint-driver-cell__badge {
  margin-left: var(--space-1);
  font-size: 10px;
  color: var(--color-accent-text);
}

.stint-driver-cell__band {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.stint-driver-cell__band:last-child {
  margin-bottom: 0;
}

.stint-driver-cell__band--race {
  padding-top: var(--space-1);
  border-top: 1px solid rgba(255, 255, 255, 0.12);
}

.stint-driver-cell__band-label {
  font-family: var(--font-display);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.stint-driver-cell__track {
  position: relative;
  height: 26px;
  border-radius: 6px;
  overflow: visible;
}

.stint-driver-cell__track--race {
  height: 24px;
}

.stint-driver-cell__track-bg {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 6px;
}

.stint-driver-cell__stint {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 4px;
  border: 1px solid;
  box-sizing: border-box;
  cursor: default;
}

.stint-driver-cell__stint--strategy {
  border-width: 1.5px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12);
}

.stint-driver-cell__stint--sim {
  border-style: dashed;
  opacity: 0.9;
}

.stint-driver-cell__stint--race {
  opacity: 0.85;
  pointer-events: auto;
}

.stint-driver-cell__pit-line {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  margin-left: -1px;
  background: #fff;
  opacity: 0.85;
  pointer-events: none;
  z-index: 2;
}

.stint-driver-cell__pit-line--sim {
  opacity: 0.55;
}

.stint-driver-cell__pit-line--race {
  opacity: 0.5;
}

.stint-driver-cell__pit-handle {
  position: absolute;
  top: -7px;
  width: 12px;
  height: 12px;
  margin-left: -6px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid;
  cursor: ew-resize;
  z-index: 4;
  touch-action: none;
}

.stint-driver-cell__hover-line {
  position: absolute;
  top: -4px;
  bottom: -4px;
  width: 1px;
  margin-left: -0.5px;
  background: var(--color-text-muted);
  opacity: 0.45;
  pointer-events: none;
  z-index: 1;
}

.stint-driver-cell__original-pits {
  margin: var(--space-2) 0 0 0;
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  line-height: 1.4;
}

.stint-driver-cell__original-pits-label {
  color: var(--color-text-muted);
  font-weight: 700;
  text-transform: uppercase;
  font-size: 9px;
  letter-spacing: 0.06em;
  margin-right: var(--space-2);
}

.stint-driver-cell__axis {
  margin: var(--space-1) 0 0 0;
  text-align: center;
  font-family: var(--font-display);
  font-size: 9px;
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: 0.04em;
}
</style>
