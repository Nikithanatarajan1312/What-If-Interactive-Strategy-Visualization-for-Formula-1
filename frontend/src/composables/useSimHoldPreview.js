import { onUnmounted } from 'vue'

/** @typedef {'raceTrace' | 'bumpChart' | 'stintBar' | 'pitHeatmap' | 'deltaBreakdown'} SimHoldChartId */

/**
 * While a chart's "Sim" control is held, that chart alone shows simulated series only.
 * @param {import('pinia').Store<'race', any>} store — useRaceStore()
 * @param {SimHoldChartId} chartId
 */
export function chartVizLayers(store, chartId) {
  const hold =
    store.simHoldChartId === chartId && store.hasSavedSimulations
  if (hold) {
    return { showActual: false, showSim: true }
  }
  return {
    showActual: store.vizShowActualLayer,
    showSim: store.vizShowSimLayer,
  }
}

/**
 * Pointer-down opens sim-only preview for this chart; pointer-up anywhere ends it.
 * @param {import('pinia').Store<'race', any>} store
 * @param {SimHoldChartId} chartId
 */
export function useSimHoldPreview(store, chartId) {
  function endHold() {
    if (store.simHoldChartId === chartId) {
      store.clearSimHoldChart()
    }
    window.removeEventListener('pointerup', endHold)
    window.removeEventListener('pointercancel', endHold)
    window.removeEventListener('blur', endHold)
  }

  function onSimHoldPointerDown(e) {
    if (!store.hasSavedSimulations) return
    e.preventDefault()
    store.setSimHoldChart(chartId)
    window.addEventListener('pointerup', endHold)
    window.addEventListener('pointercancel', endHold)
    window.addEventListener('blur', endHold)
  }

  onUnmounted(() => {
    endHold()
  })

  return { onSimHoldPointerDown }
}
