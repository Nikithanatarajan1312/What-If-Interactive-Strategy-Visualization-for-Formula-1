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

  /**
   * Per-driver saved what-if runs: driver code -> { strategy, simDriver, simDelta }.
   * Lets multiple drivers keep simulated overlays in one session.
   */
  const savedSimulations = ref({})

  const selectedDrivers = ref([])
  const hoveredLap = ref(null)
  const brushedLapRange = ref(null)
  const highlightedDriver = ref(null)
  const showSimulated = ref(false)
  const loading = ref(false)
  const error = ref(null)

  const modifiedStrategy = ref(null)
  /** @type {import('vue').Ref<null | { pit_window: Record<string, object[]>, delta_breakdown: Record<string, object> }>} */
  const strategyViz = ref(null)

  const drivers = computed(() => raceData.value?.drivers ?? [])

  const activeDrivers = computed(() => {
    if (selectedDrivers.value.length === 0) return drivers.value
    return drivers.value.filter((d) => selectedDrivers.value.includes(d.code))
  })

  const totalLaps = computed(() => raceData.value?.race?.totalLaps ?? 0)

  /** Merged `{ drivers: [...] }` for charts — one simDriver per saved driver. */
  const simulatedData = computed(() => {
    const entries = Object.values(savedSimulations.value)
    if (!entries.length) return null
    return { drivers: entries.map((e) => e.simDriver) }
  })

  const savedSimulationCodes = computed(() => Object.keys(savedSimulations.value))

  /** True when current modified pits differ from race actual and from saved snapshot for this driver (needs Run). */
  const canRunSimulation = computed(() => {
    if (!modifiedStrategy.value || !raceData.value) return false
    const code = modifiedStrategy.value.driverCode
    const orig = raceData.value.drivers.find((d) => d.code === code)
    if (!orig) return false
    const ch = diffPitChange(orig.pitStops, modifiedStrategy.value.pitStops)
    if (!ch) return false
    const sav = savedSimulations.value[code]
    if (!sav) return true
    return (
      JSON.stringify(sav.strategy.pitStops) !== JSON.stringify(modifiedStrategy.value.pitStops)
    )
  })

  function pitsEqual(a, b) {
    return JSON.stringify(a ?? []) === JSON.stringify(b ?? [])
  }

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
      savedSimulations.value = {}
      modifiedStrategy.value = null
      showSimulated.value = false
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
    savedSimulations.value = {}
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
      selectedRace.value = race
      strategyViz.value = null
      const envelope = await api.fetchRaceData({ year, grand_prix, country })
      cacheTag.value = envelope.cache_tag
      raceData.value = racePayloadToViewModel(envelope)
      selectedDrivers.value = []
      try {
        const codes = raceData.value.drivers.map((d) => d.code)
        strategyViz.value = await api.fetchStrategyViz({
          raw_race: raceData.value._raw,
          drivers: codes,
        })
      } catch (e) {
        console.warn('strategy-viz failed', e.message)
      }
    } catch (e) {
      error.value = `Failed to load race: ${e.message}`
      raceData.value = null
      cacheTag.value = null
    } finally {
      loading.value = false
    }
  }

  /**
   * When user edits pits for a driver, drop that driver's saved sim if pits no longer match.
   * Other drivers' saved simulations are kept.
   */
  function setModifiedStrategy(strategy) {
    modifiedStrategy.value = strategy
    const code = strategy.driverCode
    const prev = savedSimulations.value[code]
    if (prev && !pitsEqual(prev.strategy.pitStops, strategy.pitStops)) {
      const next = { ...savedSimulations.value }
      delete next[code]
      savedSimulations.value = next
    }
    error.value = null
  }

  async function applyPitStrategyChange(strategy) {
    if (!selectedRace.value || !cacheTag.value || !raceData.value) return
    setModifiedStrategy(strategy)
    await simulate(strategy, { silentNoDiff: true })
  }

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
      const simDriver = simulateToViewModel(
        raw,
        originalDriver,
        strategy,
        raceData.value.drivers,
      )
      const bd = raw?.delta_breakdown
      let simDelta = bd?.components ? { code: driverCode, ...bd } : null
      try {
        const selectedLap = Number(change.new_pit_lap)
        if (Number.isFinite(selectedLap)) {
          const viz = await api.fetchStrategyViz({
            raw_race: raceData.value._raw,
            drivers: [driverCode],
            selected_pit_laps: { [String(driverCode).toUpperCase()]: selectedLap },
          })
          const u = String(driverCode).toUpperCase()
          const simBd = viz?.delta_breakdown?.[u]
          if (simBd?.components) simDelta = { code: driverCode, ...simBd }
        }
      } catch (e) {
        console.warn('strategy-viz selected-lap breakdown failed', e.message)
      }

      const strategySnap = JSON.parse(JSON.stringify(strategy))
      savedSimulations.value = {
        ...savedSimulations.value,
        [driverCode]: {
          strategy: strategySnap,
          simDriver,
          simDelta,
        },
      }
      showSimulated.value = true
    } catch (e) {
      error.value = `Simulation failed: ${e.message}`
    } finally {
      loading.value = false
    }
  }

  function removeSavedSimulation(code) {
    if (!code || !savedSimulations.value[code]) return
    const next = { ...savedSimulations.value }
    delete next[code]
    savedSimulations.value = next
    if (!Object.keys(next).length) showSimulated.value = false
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
    savedSimulations.value = {}
    modifiedStrategy.value = null
    showSimulated.value = false
    error.value = null
  }

  return {
    availableYears,
    selectedYear,
    availableRaces,
    selectedRace,
    cacheTag,
    raceData,
    savedSimulations,
    simulatedData,
    savedSimulationCodes,
    canRunSimulation,
    selectedDrivers,
    hoveredLap,
    brushedLapRange,
    highlightedDriver,
    showSimulated,
    loading,
    error,
    modifiedStrategy,
    strategyViz,
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
    removeSavedSimulation,
    toggleDriver,
    setHoveredLap,
    setBrushedRange,
    setHighlightedDriver,
    resetStrategy,
  }
})
