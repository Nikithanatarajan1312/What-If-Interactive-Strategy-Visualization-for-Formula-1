import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api/index.js'

export const useRaceStore = defineStore('race', () => {
  const availableRaces = ref([])
  const selectedRace = ref(null)
  const raceData = ref(null)
  const simulatedData = ref(null)

  const selectedDrivers = ref([])
  const hoveredLap = ref(null)
  const brushedLapRange = ref(null)
  const highlightedDriver = ref(null)
  const showSimulated = ref(false)
  const loading = ref(false)
  const error = ref(null)

  const modifiedStrategy = ref(null)

  const drivers = computed(() => raceData.value?.drivers ?? [])

  const activeDrivers = computed(() => {
    if (selectedDrivers.value.length === 0) return drivers.value
    return drivers.value.filter(d => selectedDrivers.value.includes(d.code))
  })

  const totalLaps = computed(() => raceData.value?.race?.totalLaps ?? 0)

  async function loadAvailableRaces() {
    try {
      availableRaces.value = await api.fetchRaces()
    } catch (e) {
      error.value = `Failed to load races: ${e.message}`
    }
  }

  async function loadRace(year, round) {
    loading.value = true
    error.value = null
    simulatedData.value = null
    modifiedStrategy.value = null
    showSimulated.value = false
    brushedLapRange.value = null
    highlightedDriver.value = null
    try {
      selectedRace.value = { year, round }
      raceData.value = await api.fetchRaceData(year, round)
      selectedDrivers.value = []
    } catch (e) {
      error.value = `Failed to load race: ${e.message}`
    } finally {
      loading.value = false
    }
  }

  async function simulate(strategy) {
    if (!selectedRace.value) return
    loading.value = true
    error.value = null
    try {
      modifiedStrategy.value = strategy
      simulatedData.value = await api.fetchSimulation(
        selectedRace.value.year,
        selectedRace.value.round,
        strategy
      )
      showSimulated.value = true
    } catch (e) {
      error.value = `Simulation failed: ${e.message}`
    } finally {
      loading.value = false
    }
  }

  function toggleDriver(code) {
    const idx = selectedDrivers.value.indexOf(code)
    if (idx === -1) {
      selectedDrivers.value.push(code)
    } else {
      selectedDrivers.value.splice(idx, 1)
    }
  }

  function setHoveredLap(lap) {
    hoveredLap.value = lap
  }

  function setBrushedRange(range) {
    brushedLapRange.value = range
  }

  function setHighlightedDriver(code) {
    highlightedDriver.value = code
  }

  function resetStrategy() {
    simulatedData.value = null
    modifiedStrategy.value = null
    showSimulated.value = false
  }

  return {
    availableRaces,
    selectedRace,
    raceData,
    simulatedData,
    selectedDrivers,
    hoveredLap,
    brushedLapRange,
    highlightedDriver,
    showSimulated,
    loading,
    error,
    modifiedStrategy,
    drivers,
    activeDrivers,
    totalLaps,
    loadAvailableRaces,
    loadRace,
    simulate,
    toggleDriver,
    setHoveredLap,
    setBrushedRange,
    setHighlightedDriver,
    resetStrategy,
  }
})
