import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'

/**
 * Shared D3 chart setup composable.
 * Creates a responsive SVG with margin convention and resize observer.
 *
 * @param {import('vue').Ref<HTMLElement>} containerRef
 * @param {object} margin - { top, right, bottom, left }
 * @returns {{ width, height, getSvg, getG, onDraw, redraw }}
 */
export function useChart(containerRef, margin = { top: 20, right: 20, bottom: 30, left: 50 }) {
  const width = ref(0)
  const height = ref(0)
  let svg = null
  let g = null
  let resizeObserver = null
  let drawCallback = null
  let lastW = 0
  let lastH = 0
  let resizeTimer = null

  function setup() {
    const el = containerRef.value
    if (!el) return

    const rect = el.getBoundingClientRect()
    const newW = Math.floor(rect.width)
    const newH = Math.floor(rect.height)

    if (newW === lastW && newH === lastH && svg) return
    lastW = newW
    lastH = newH

    d3.select(el).select('svg').remove()

    width.value = Math.max(0, newW - margin.left - margin.right)
    height.value = Math.max(0, newH - margin.top - margin.bottom)

    if (width.value <= 0 || height.value <= 0) return

    svg = d3
      .select(el)
      .append('svg')
      .attr('width', newW)
      .attr('height', newH)

    g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    if (drawCallback) drawCallback()
  }

  function onDraw(fn) {
    drawCallback = fn
  }

  function redraw() {
    if (g) {
      g.selectAll('*').remove()
      if (drawCallback) drawCallback()
    }
  }

  function getSvg() { return svg }
  function getG() { return g }

  function debouncedSetup() {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(setup, 50)
  }

  onMounted(() => {
    nextTick(() => {
      setup()
      resizeObserver = new ResizeObserver(debouncedSetup)
      if (containerRef.value) resizeObserver.observe(containerRef.value)
    })
  })

  onUnmounted(() => {
    clearTimeout(resizeTimer)
    resizeObserver?.disconnect()
  })

  return { width, height, getSvg, getG, onDraw, redraw, setup }
}
