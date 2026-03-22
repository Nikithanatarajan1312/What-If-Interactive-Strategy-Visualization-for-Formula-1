import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '../api/index.js'
import {
  racePayloadToViewModel,
  simulateToViewModel,
  diffPitChange,
} from '../utils/raceAdapter.js'

export const useRaceStore = defineStore('race', () => {
  const availableYears = ref([])
  const selectedYear = ref(new Date().getFullYear())
  const availableRaces = ref([])
  const selectedRace = ref(null)
  /** @type {import('vue').Ref<null | object>} */
  const raceData = ref(null)
  const cacheTag = ref(null)
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
    return drivers.value.filter((d) => selectedDrivers.value.includes(d.code))
  })

  const totalLaps = computed(() => raceData.value?.race?.totalLaps ?? 0)

  async function loadYears() {
    try {
      const years = await api.fetchYears()
      availableYears.value = years
      if (!years.includes(selectedYear.value)) {
        selectedYear.value = years.includes(2024) ? 2024 : years[years.length - 1]
      }
    } catch (e) {
      error.value = `Failed to load years: ${e.message}`
    }
  }

  async function loadRacesForYear(year) {
    try {
      selectedYear.value = year
      selectedRace.value = null
      raceData.value = null
      cacheTag.value = null
      simulatedData.value = null
      modifiedStrategy.value = null
      availableRaces.value = await api.fetchRacesForYear(year)
    } catch (e) {
      error.value = `Failed to load races: ${e.message}`
    }
  }

  async function bootstrap() {
    error.value = null
    await loadYears()
    await loadRacesForYear(selectedYear.value)
  }

  async function loadRace(race) {
    if (!race) return
    loading.value = true
    error.value = null
    simulatedData.value = null
    modifiedStrategy.value = null
    showSimulated.value = false
    brushedLapRange.value = null
    highlightedDriver.value = null
    try {
      const year = Number(race.year)
      const grand_prix = String(race.grand_prix ?? '').trim()
      const country = String(race.country ?? '').trim()
      if (!year || !grand_prix || !country) {
        throw new Error('Pick a race from the list (needs year, grand_prix, country — not a label-only string).')
      }
      // Keep the list row so dropdown matching (year / grand_prix / country) stays in sync.
      selectedRace.value = race
      // Exact POST body: { year, grand_prix, country } e.g. Las Vegas + United States
      const envelope = await api.fetchRaceData({ year, grand_prix, country })
      cacheTag.value = envelope.cache_tag
      raceData.value = racePayloadToViewModel(envelope)
      selectedDrivers.value = []
    } catch (e) {
      error.value = `Failed to load race: ${e.message}`
      raceData.value = null
      cacheTag.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * Call after user edits pit stops (drag). Clears previous sim so charts can refresh.
   */
  function setModifiedStrategy(strategy) {
    modifiedStrategy.value = strategy
    simulatedData.value = null
    showSimulated.value = false
    error.value = null
  }

  /**
   * After moving a pit marker: save strategy + re-run backend sim so traces update.
   * (Avoids the bug where Run Simulation stayed hidden once simulatedData was set.)
   */
  async function applyPitStrategyChange(strategy) {
    if (!selectedRace.value || !cacheTag.value || !raceData.value) return
    setModifiedStrategy(strategy)
    await simulate(strategy, { silentNoDiff: true })
  }

  /**
   * @param {{ silentNoDiff?: boolean }} opts - if true, no error when pit laps match original (e.g. tiny drag)
   */
  async function simulate(strategy, opts = {}) {
    if (!selectedRace.value || !cacheTag.value || !raceData.value) return
    const driverCode = strategy.driverCode
    const originalDriver = raceData.value.drivers.find((d) => d.code === driverCode)
    if (!originalDriver) {
      error.value = 'Driver not found'
      return
    }

    const change = diffPitChange(originalDriver.pitStops, strategy.pitStops)
    if (!change) {
      if (!opts.silentNoDiff) {
        error.value = 'Move a pit stop lap first, then run simulation.'
      }
      return
    }

    loading.value = true
    error.value = null
    try {
      modifiedStrategy.value = strategy
      const raw = await api.fetchSimulation({
        cache_tag: cacheTag.value,
        driver: driverCode,
        new_pit_lap: change.new_pit_lap,
        new_compound: change.new_compound,
        pit_loss_sec: change.pit_loss_sec,
      })
      const simDriver = simulateToViewModel(raw, originalDriver, strategy)
      simulatedData.value = { drivers: [simDriver] }
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
    availableYears,
    selectedYear,
    availableRaces,
    selectedRace,
    cacheTag,
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
    loadYears,
    loadRacesForYear,
    bootstrap,
    loadRace,
    simulate,
    setModifiedStrategy,
    applyPitStrategyChange,
    toggleDriver,
    setHoveredLap,
    setBrushedRange,
    setHighlightedDriver,
    resetStrategy,
  }
})
