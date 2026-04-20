<script setup>
import { computed, inject, onUnmounted } from 'vue'

const props = defineProps({
  cardId: { type: String, required: true },
  title: { type: String, required: true },
  x: { type: Number, required: true },
  y: { type: Number, required: true },
  width: { type: Number, default: 560 },
  height: { type: Number, default: 360 },
  minWidth: { type: Number, default: 320 },
  minHeight: { type: Number, default: 220 },
  ariaLabel: { type: String, default: '' },
})

const emit = defineEmits([
  'update:x',
  'update:y',
  'update:width',
  'update:height',
  'focus',
])

const canvas = inject('boundedCanvas', null)

const drag = {
  active: false,
  pointerId: null,
  startClientX: 0,
  startClientY: 0,
  startX: 0,
  startY: 0,
  target: null,
}

const resize = {
  active: false,
  pointerId: null,
  startClientX: 0,
  startClientY: 0,
  startW: 0,
  startH: 0,
  target: null,
}

function focus() {
  canvas?.bringToFront(props.cardId)
  emit('focus', props.cardId)
}

function onHandlePointerDown(e) {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  focus()
  drag.active = true
  drag.pointerId = e.pointerId
  drag.startClientX = e.clientX
  drag.startClientY = e.clientY
  drag.startX = props.x
  drag.startY = props.y
  drag.target = e.currentTarget
  try {
    e.currentTarget.setPointerCapture?.(e.pointerId)
  } catch {}
  window.addEventListener('pointermove', onWindowPointerMove)
  window.addEventListener('pointerup', onWindowPointerUp)
  window.addEventListener('pointercancel', onWindowPointerUp)
  e.preventDefault()
  e.stopPropagation()
}

function onWindowPointerMove(e) {
  if (!drag.active || e.pointerId !== drag.pointerId) return
  const scale = canvas?.transform?.scale ?? 1
  const dx = (e.clientX - drag.startClientX) / scale
  const dy = (e.clientY - drag.startClientY) / scale
  emit('update:x', drag.startX + dx)
  emit('update:y', drag.startY + dy)
}

function onWindowPointerUp(e) {
  if (!drag.active) return
  if (e.pointerId !== drag.pointerId) return
  drag.active = false
  drag.pointerId = null
  try {
    drag.target?.releasePointerCapture?.(e.pointerId)
  } catch {}
  drag.target = null
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
  window.removeEventListener('pointercancel', onWindowPointerUp)
}

function onResizePointerDown(e) {
  if (e.button !== 0 && e.pointerType === 'mouse') return
  focus()
  resize.active = true
  resize.pointerId = e.pointerId
  resize.startClientX = e.clientX
  resize.startClientY = e.clientY
  resize.startW = props.width
  resize.startH = props.height
  resize.target = e.currentTarget
  try {
    e.currentTarget.setPointerCapture?.(e.pointerId)
  } catch {}
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeUp)
  window.addEventListener('pointercancel', onResizeUp)
  e.preventDefault()
  e.stopPropagation()
}

function onResizeMove(e) {
  if (!resize.active || e.pointerId !== resize.pointerId) return
  const scale = canvas?.transform?.scale ?? 1
  const dx = (e.clientX - resize.startClientX) / scale
  const dy = (e.clientY - resize.startClientY) / scale
  const nextW = Math.max(props.minWidth, resize.startW + dx)
  const nextH = Math.max(props.minHeight, resize.startH + dy)
  emit('update:width', nextW)
  emit('update:height', nextH)
}

function onResizeUp(e) {
  if (!resize.active) return
  if (e.pointerId !== resize.pointerId) return
  resize.active = false
  resize.pointerId = null
  try {
    resize.target?.releasePointerCapture?.(e.pointerId)
  } catch {}
  resize.target = null
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
  window.removeEventListener('pointercancel', onResizeUp)
}

onUnmounted(() => {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
  window.removeEventListener('pointercancel', onWindowPointerUp)
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeUp)
  window.removeEventListener('pointercancel', onResizeUp)
})

const rootStyle = computed(() => ({
  transform: `translate(${props.x}px, ${props.y}px)`,
  width: `${props.width}px`,
  height: `${props.height}px`,
  zIndex: canvas?.getCardZ(props.cardId) ?? 1,
}))
</script>

<template>
  <div
    class="draggable-card"
    :class="{
      'draggable-card--dragging': drag.active,
      'draggable-card--resizing': resize.active,
    }"
    :style="rootStyle"
    :aria-label="ariaLabel || title"
    role="group"
    @pointerdown="focus"
  >
    <div
      class="draggable-card__handle"
      @pointerdown="onHandlePointerDown"
      role="toolbar"
      :aria-label="`Drag handle for ${title}`"
    >
      <span class="draggable-card__grip" aria-hidden="true">
        <span></span><span></span><span></span>
        <span></span><span></span><span></span>
      </span>
      <span class="draggable-card__title">{{ title }}</span>
    </div>
    <div
      class="draggable-card__body"
      @pointerdown.stop="focus"
      @mousedown.stop
    >
      <slot />
    </div>
    <div
      class="draggable-card__resize"
      @pointerdown="onResizePointerDown"
      role="separator"
      :aria-label="`Resize ${title}`"
    >
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2 12 L12 2 M6 12 L12 6 M10 12 L12 10" stroke="currentColor" stroke-width="1.5" fill="none" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
.draggable-card {
  position: absolute;
  left: 0;
  top: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  transition: border-color var(--duration-normal) var(--ease-out),
    box-shadow var(--duration-normal) var(--ease-out);
}

.draggable-card:hover {
  border-color: var(--color-border-hover);
}

.draggable-card--dragging,
.draggable-card--resizing {
  border-color: var(--color-accent);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
}

.draggable-card__handle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
  cursor: grab;
  user-select: none;
  flex-shrink: 0;
}

.draggable-card--dragging .draggable-card__handle {
  cursor: grabbing;
}

.draggable-card__grip {
  display: inline-grid;
  grid-template-columns: repeat(2, 3px);
  grid-template-rows: repeat(3, 3px);
  gap: 2px;
  opacity: 0.5;
}

.draggable-card__grip span {
  width: 3px;
  height: 3px;
  background: var(--color-text-muted);
  border-radius: 50%;
}

.draggable-card__title {
  font-family: var(--font-display);
  font-size: var(--text-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text);
}

.draggable-card__body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-2);
  overflow: hidden;
}

/* Pro mode has its own card chrome — hide each chart's Expand button.
   Targets only the expand toggle (it carries aria-expanded); Sim-hold stays. */
.draggable-card__body :deep(.panel-expand[aria-expanded]) {
  display: none !important;
}

.draggable-card__resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 3px;
  cursor: nwse-resize;
  color: var(--color-text-muted);
  background: linear-gradient(135deg, transparent 50%, rgba(225, 6, 0, 0.15) 50%);
  opacity: 0.85;
  touch-action: none;
  z-index: 2;
  border-bottom-right-radius: var(--radius-lg);
}

.draggable-card__resize:hover,
.draggable-card--resizing .draggable-card__resize {
  color: var(--color-accent);
  opacity: 1;
  background: linear-gradient(135deg, transparent 50%, rgba(225, 6, 0, 0.4) 50%);
}
</style>
