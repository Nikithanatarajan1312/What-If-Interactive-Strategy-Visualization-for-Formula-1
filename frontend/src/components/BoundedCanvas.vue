<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, provide, readonly } from 'vue'

const props = defineProps({
  minZoom: { type: Number, default: 0.5 },
  maxZoom: { type: Number, default: 2.5 },
  panMin: { type: Number, default: -3000 },
  panMax: { type: Number, default: 3000 },
  /** Visual overshoot allowed past the pan clamp before snap-back. */
  rubberBand: { type: Number, default: 80 },
  /** Half-extent of the dot-grid rectangle (world units). */
  gridHalfSize: { type: Number, default: 4000 },
  gridSpacing: { type: Number, default: 24 },
})

const viewport = ref(null)

const transform = reactive({ tx: 0, ty: 0, scale: 1 })

const stackingZ = ref(10)
const cardZ = reactive({})

function bringToFront(cardId) {
  if (!cardId) return
  stackingZ.value += 1
  cardZ[cardId] = stackingZ.value
}

function getCardZ(cardId) {
  return cardZ[cardId] ?? 1
}

provide('boundedCanvas', {
  transform: readonly(transform),
  bringToFront,
  getCardZ,
})

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v))
}

/** Soft clamp with rubber-band overshoot during interaction. */
function rubberClamp(v, lo, hi, give) {
  if (v < lo) {
    const over = lo - v
    return lo - (give * over) / (over + give)
  }
  if (v > hi) {
    const over = v - hi
    return hi + (give * over) / (over + give)
  }
  return v
}

const pan = {
  active: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  startTx: 0,
  startTy: 0,
}

function onPanLayerPointerDown(e) {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  pan.active = true
  pan.pointerId = e.pointerId
  pan.startX = e.clientX
  pan.startY = e.clientY
  pan.startTx = transform.tx
  pan.startTy = transform.ty
  try {
    e.currentTarget.setPointerCapture?.(e.pointerId)
  } catch {}
  e.preventDefault()
}

function onWindowPointerMove(e) {
  if (!pan.active || e.pointerId !== pan.pointerId) return
  const dx = e.clientX - pan.startX
  const dy = e.clientY - pan.startY
  transform.tx = rubberClamp(pan.startTx + dx, props.panMin, props.panMax, props.rubberBand)
  transform.ty = rubberClamp(pan.startTy + dy, props.panMin, props.panMax, props.rubberBand)
}

function endPan() {
  if (!pan.active) return
  pan.active = false
  pan.pointerId = null
  transform.tx = clamp(transform.tx, props.panMin, props.panMax)
  transform.ty = clamp(transform.ty, props.panMin, props.panMax)
}

function onWheel(e) {
  if (!viewport.value) return
  e.preventDefault()
  const rect = viewport.value.getBoundingClientRect()
  /* World origin sits at viewport center; measure pointer relative to it. */
  const dmx = e.clientX - rect.left - rect.width / 2
  const dmy = e.clientY - rect.top - rect.height / 2
  const factor = Math.exp(-e.deltaY * 0.0015)
  const nextScale = clamp(transform.scale * factor, props.minZoom, props.maxZoom)
  const ratio = nextScale / transform.scale
  transform.tx = clamp(dmx - (dmx - transform.tx) * ratio, props.panMin, props.panMax)
  transform.ty = clamp(dmy - (dmy - transform.ty) * ratio, props.panMin, props.panMax)
  transform.scale = nextScale
}

function resetView() {
  transform.tx = 0
  transform.ty = 0
  transform.scale = 1
}

defineExpose({ resetView, transform })

const worldStyle = computed(() => ({
  transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.scale})`,
}))

const gridRect = computed(() => ({
  x: -props.gridHalfSize,
  y: -props.gridHalfSize,
  size: props.gridHalfSize * 2,
}))

onMounted(() => {
  window.addEventListener('pointermove', onWindowPointerMove, { passive: true })
  window.addEventListener('pointerup', endPan, { passive: true })
  window.addEventListener('pointercancel', endPan, { passive: true })
  viewport.value?.addEventListener('wheel', onWheel, { passive: false })
})

onUnmounted(() => {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', endPan)
  window.removeEventListener('pointercancel', endPan)
  viewport.value?.removeEventListener('wheel', onWheel)
})
</script>

<template>
  <div
    ref="viewport"
    class="bounded-canvas"
    :class="{ 'bounded-canvas--panning': pan.active }"
    role="application"
    aria-label="Pro canvas workspace"
  >
    <div
      class="bounded-canvas__pan-layer"
      @pointerdown="onPanLayerPointerDown"
      aria-hidden="true"
    ></div>

    <div class="bounded-canvas__world" :style="worldStyle">
      <svg
        class="bounded-canvas__grid"
        :width="gridRect.size"
        :height="gridRect.size"
        :viewBox="`0 0 ${gridRect.size} ${gridRect.size}`"
        :style="{ left: gridRect.x + 'px', top: gridRect.y + 'px' }"
        aria-hidden="true"
      >
        <defs>
          <pattern
            id="bc-dot-grid"
            :width="gridSpacing"
            :height="gridSpacing"
            patternUnits="userSpaceOnUse"
          >
            <circle :cx="gridSpacing / 2" :cy="gridSpacing / 2" r="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#bc-dot-grid)" />
      </svg>

      <slot />
    </div>

    <button
      type="button"
      class="bounded-canvas__reset"
      @click="resetView"
      aria-label="Reset canvas view"
    >
      Reset view
    </button>
  </div>
</template>

<style scoped>
.bounded-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  touch-action: none;
  user-select: none;
}

.bounded-canvas__pan-layer {
  position: absolute;
  inset: 0;
  cursor: grab;
  z-index: 0;
}

.bounded-canvas--panning .bounded-canvas__pan-layer {
  cursor: grabbing;
}

.bounded-canvas__world {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 0;
  height: 0;
  transform-origin: 0 0;
  will-change: transform;
  z-index: 1;
}

.bounded-canvas__grid {
  position: absolute;
  pointer-events: none;
  color: var(--color-text-muted);
  opacity: 0.18;
}

.bounded-canvas__grid circle {
  fill: currentColor;
}

.bounded-canvas__reset {
  position: absolute;
  right: var(--space-3);
  bottom: var(--space-3);
  z-index: 5;
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  transition: border-color var(--duration-normal) var(--ease-out),
    color var(--duration-normal) var(--ease-out);
}

.bounded-canvas__reset:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.bounded-canvas__reset:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
