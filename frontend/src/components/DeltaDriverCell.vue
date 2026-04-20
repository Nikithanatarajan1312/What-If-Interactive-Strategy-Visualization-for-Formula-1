<script setup>
import { computed } from 'vue'
import { formatGainSeconds, stackMaxAbs, layoutStackedSegments } from '../utils/deltaBreakdownUtils'

const props = defineProps({
  driverCode: { type: String, required: true },
  driverColor: { type: String, default: '#e8eaef' },
  /** Pit-window model breakdown */
  actualDelta: { type: Object, default: null },
  /** Saved sim breakdown */
  simDelta: { type: Object, default: null },
  showActual: { type: Boolean, default: true },
  showSim: { type: Boolean, default: true },
  dimmed: { type: Boolean, default: false },
})

const emit = defineEmits(['pointer-on', 'pointer-off'])

const showSimRow = computed(
  () => props.showSim && props.simDelta?.components?.length
)

/** One symmetric domain for actual + sim so rows are comparable. */
const sharedMaxAbs = computed(() => {
  let m = 1e-6
  if (props.actualDelta?.components?.length) {
    m = Math.max(
      m,
      stackMaxAbs(props.actualDelta.components, props.actualDelta.total)
    )
  }
  if (props.simDelta?.components?.length) {
    m = Math.max(m, stackMaxAbs(props.simDelta.components, props.simDelta.total))
  }
  return m * 1.06
})

const actualLayout = computed(() => {
  if (!props.showActual || !props.actualDelta?.components?.length) return null
  return layoutStackedSegments(
    props.actualDelta.components,
    props.actualDelta.total,
    sharedMaxAbs.value
  )
})

const simLayout = computed(() => {
  if (!showSimRow.value || !props.simDelta?.components?.length) return null
  return layoutStackedSegments(
    props.simDelta.components,
    props.simDelta.total,
    sharedMaxAbs.value
  )
})

function axisLabel(maxAbs) {
  const x = Math.abs(maxAbs)
  return `−${x.toFixed(1)}s · 0 · +${x.toFixed(1)}s`
}

function actualNetOpacity(layout) {
  if (!layout || props.actualDelta?.total == null) return 0.35
  return Math.abs(layout.cumEnd - props.actualDelta.total) > 0.08 ? 1 : 0.35
}

function simNetOpacity(layout) {
  if (!layout || props.simDelta?.total == null) return 0.35
  return Math.abs(layout.cumEnd - props.simDelta.total) > 0.08 ? 1 : 0.35
}

function onEnter() {
  emit('pointer-on', props.driverCode)
}

function onLeave() {
  emit('pointer-off')
}
</script>

<template>
  <article
    class="delta-driver-cell"
    :class="{ 'delta-driver-cell--dimmed': dimmed }"
    role="group"
    :aria-label="`Stacked delta breakdown for ${driverCode}`"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
  >
    <header class="delta-driver-cell__head">
      <span class="delta-driver-cell__code" :style="{ color: driverColor }">{{ driverCode }}</span>
      <div class="delta-driver-cell__nets" aria-hidden="true">
        <span
          v-if="showActual && actualDelta && actualDelta.total != null"
          class="delta-driver-cell__net delta-driver-cell__net--actual"
        >
          Model {{ formatGainSeconds(actualDelta.total) }}
        </span>
        <span
          v-if="showSimRow && simDelta && simDelta.total != null"
          class="delta-driver-cell__net delta-driver-cell__net--sim"
        >
          Sim {{ formatGainSeconds(simDelta.total) }}
        </span>
      </div>
    </header>

    <div class="delta-driver-cell__body">
      <section
        v-if="showActual && actualLayout"
        class="delta-driver-cell__band"
        aria-label="Actual stacked breakdown"
      >
        <div class="delta-driver-cell__band-label">Actual</div>
        <div
          class="delta-driver-cell__track"
          role="img"
          :aria-label="`Actual components stack to ${formatGainSeconds(actualDelta.total)}`"
        >
          <div class="delta-driver-cell__track-bg" aria-hidden="true" />
          <div class="delta-driver-cell__zero" aria-hidden="true" />
          <div
            v-for="(seg, i) in actualLayout.segments"
            :key="'a-' + i"
            class="delta-driver-cell__seg"
            :title="`${seg.display}: ${formatGainSeconds(seg.value)}`"
            :style="{
              left: seg.left + '%',
              width: seg.width + '%',
              background: seg.fill,
            }"
          />
          <div
            class="delta-driver-cell__net-tick"
            aria-hidden="true"
            :style="{
              left: actualLayout.netLeft + '%',
              opacity: actualNetOpacity(actualLayout),
            }"
          />
        </div>
        <p class="delta-driver-cell__axis" aria-hidden="true">{{ axisLabel(actualLayout.maxAbs) }}</p>
      </section>

      <section
        v-if="showSimRow && simLayout"
        class="delta-driver-cell__band delta-driver-cell__band--sim"
        aria-label="Simulated stacked breakdown"
      >
        <div class="delta-driver-cell__band-label">Simulated</div>
        <div
          class="delta-driver-cell__track delta-driver-cell__track--sim"
          role="img"
          :aria-label="`Simulated components stack to ${formatGainSeconds(simDelta.total)}`"
        >
          <div class="delta-driver-cell__track-bg" aria-hidden="true" />
          <div class="delta-driver-cell__zero" aria-hidden="true" />
          <div
            v-for="(seg, i) in simLayout.segments"
            :key="'s-' + i"
            class="delta-driver-cell__seg delta-driver-cell__seg--sim"
            :title="`${seg.display}: ${formatGainSeconds(seg.value)}`"
            :style="{
              left: seg.left + '%',
              width: seg.width + '%',
              background: seg.fill,
            }"
          />
          <div
            class="delta-driver-cell__net-tick"
            aria-hidden="true"
            :style="{
              left: simLayout.netLeft + '%',
              opacity: simNetOpacity(simLayout),
            }"
          />
        </div>
        <p class="delta-driver-cell__axis" aria-hidden="true">{{ axisLabel(simLayout.maxAbs) }}</p>
      </section>
    </div>
  </article>
</template>

<style scoped>
.delta-driver-cell {
  flex-shrink: 0;
  padding: var(--space-1) var(--space-2);
  border-radius: 0;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom-width: 0;
  transition: opacity var(--duration-normal) var(--ease-out);
}

.delta-driver-cell:last-child {
  border-bottom-width: 1px;
}

.delta-driver-cell--dimmed {
  opacity: 0.22;
}

.delta-driver-cell__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
  flex-wrap: wrap;
}

.delta-driver-cell__code {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 800;
  letter-spacing: 0.06em;
}

.delta-driver-cell__nets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  font-variant-numeric: tabular-nums;
}

.delta-driver-cell__net {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-text-secondary);
}

.delta-driver-cell__net--sim {
  font-style: italic;
  color: var(--color-text-muted);
}

.delta-driver-cell__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.delta-driver-cell__band {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.delta-driver-cell__band--sim {
  padding-top: var(--space-1);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.delta-driver-cell__band-label {
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.delta-driver-cell__track {
  position: relative;
  height: 18px;
  margin-top: 2px;
  border-radius: 4px;
  overflow: hidden;
}

.delta-driver-cell__track--sim {
  height: 15px;
}

.delta-driver-cell__track-bg {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.22);
  border-radius: 6px;
}

.delta-driver-cell__zero {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: rgba(255, 255, 255, 0.35);
  z-index: 1;
  pointer-events: none;
}

.delta-driver-cell__seg {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 2px;
  z-index: 2;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(0, 0, 0, 0.28);
  cursor: default;
}

.delta-driver-cell__seg--sim {
  border-style: dashed;
  opacity: 0.94;
}

.delta-driver-cell__net-tick {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent);
  border-radius: 2px;
  z-index: 3;
  pointer-events: none;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
}

.delta-driver-cell__axis {
  margin: var(--space-1) 0 0 0;
  text-align: center;
  font-family: var(--font-display);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
