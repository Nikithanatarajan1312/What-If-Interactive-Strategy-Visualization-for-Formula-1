/**
 * Maps FastAPI backend payloads to the shape expected by Vue/D3 components.
 */

const DRIVER_COLORS = [
  '#e10600', '#3671c6', '#6cd3bf', '#ffd700', '#ff8700',
  '#27ae60', '#9b59b6', '#1abc9c', '#e74c3c', '#3498db',
  '#95a5a6', '#34495e', '#f39c12', '#d35400', '#16a085',
  '#8e44ad', '#2ecc71', '#c0392b',
]

function colorForCode(code) {
  let h = 0
  for (let i = 0; i < code.length; i++) h = (h * 31 + code.charCodeAt(i)) >>> 0
  return DRIVER_COLORS[h % DRIVER_COLORS.length]
}

/** Seconds behind leader; null / NaN / missing → no plot (do not use 0). */
function parseGapValue(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  if (!Number.isFinite(n)) return null
  return Math.max(0, n)
}

/** Race position for charts; null if unknown / invalid (BumpChart will skip). */
function parsePosition(v) {
  if (v == null || v === '') return null
  const n = Math.round(Number(v))
  return Number.isFinite(n) && n >= 1 ? n : null
}

/**
 * Pit stops between consecutive stints (pit lap = first lap of new stint).
 */
function pitStopsFromStints(stintsForDriver) {
  const s = [...stintsForDriver].sort((a, b) => a.start_lap - b.start_lap)
  const pits = []
  for (let i = 0; i < s.length - 1; i++) {
    pits.push({
      lap: Math.round(s[i + 1].start_lap),
      fromCompound: String(s[i].compound || 'MEDIUM').toUpperCase(),
      toCompound: String(s[i + 1].compound || 'HARD').toUpperCase(),
      duration_s: 22,
    })
  }
  return pits
}

/**
 * @param {object} envelope - GET /api/race response: { cache_tag, year, grand_prix, country, race }
 */
export function racePayloadToViewModel(envelope) {
  const raw = envelope.race
  const lapsClean = raw.laps_clean || []
  const stintsClean = raw.stints_clean || []
  const raceTrace = raw.race_trace || []
  const events = raw.events || []
  const meta = raw.meta || {}

  const traceMap = new Map()
  for (const row of raceTrace) {
    const d = String(row.driver || '').toUpperCase()
    const lap = Math.round(Number(row.lap))
    traceMap.set(`${d}-${lap}`, parseGapValue(row.gap_to_leader))
  }

  const pitEventSet = new Set()
  for (const e of events) {
    if (e.type === 'pit_stop' && e.driver) {
      pitEventSet.add(`${String(e.driver).toUpperCase()}-${Math.round(Number(e.lap))}`)
    }
  }

  const stintsByDriver = new Map()
  for (const row of stintsClean) {
    const code = String(row.driver || '').toUpperCase()
    if (!stintsByDriver.has(code)) stintsByDriver.set(code, [])
    stintsByDriver.get(code).push({
      stint: row.stint,
      start_lap: row.start_lap,
      end_lap: row.end_lap,
      compound: String(row.compound || 'MEDIUM').toUpperCase(),
    })
  }

  const driversMap = new Map()
  for (const row of lapsClean) {
    const code = String(row.driver || '').toUpperCase()
    if (!driversMap.has(code)) {
      driversMap.set(code, {
        code,
        color: colorForCode(code),
        laps: [],
        pitStops: [],
      })
    }
    const lap = Math.round(Number(row.lap))
    const key = `${code}-${lap}`
    const gap = traceMap.get(key)
    const isPitLap = pitEventSet.has(key)

    driversMap.get(code).laps.push({
      lap,
      time_s: row.lap_time_sec != null ? Number(row.lap_time_sec) : null,
      gapToLeader: gap != null && Number.isFinite(gap) ? gap : null,
      position: parsePosition(row.position),
      compound: String(row.compound || 'MEDIUM').toUpperCase(),
      tyreAge: Math.round(Number(row.tyre_age)) || 1,
      isPitLap,
    })
  }

  for (const [, d] of driversMap) {
    d.laps.sort((a, b) => a.lap - b.lap)
    const st = stintsByDriver.get(d.code) || []
    d.pitStops = pitStopsFromStints(st)
  }

  const drivers = [...driversMap.values()].sort((a, b) => a.code.localeCompare(b.code))

  let totalLaps = 0
  for (const d of drivers) {
    for (const l of d.laps) totalLaps = Math.max(totalLaps, l.lap)
  }

  return {
    cacheTag: envelope.cache_tag,
    year: envelope.year,
    grand_prix: envelope.grand_prix,
    country: envelope.country,
    race: {
      name: meta.resolved_event_name || envelope.grand_prix || 'Race',
      totalLaps,
    },
    drivers,
    _raw: raw,
  }
}

/**
 * @param {object} sim - POST /api/simulate JSON
 * @param {object} originalDriver - view-model driver
 * @param {object} modifiedStrategy - { driverCode, pitStops }
 */
export function simulateToViewModel(sim, originalDriver, modifiedStrategy) {
  const traceMap = new Map()
  for (const row of sim.simulated_trace || []) {
    const lap = Math.round(Number(row.lap))
    traceMap.set(lap, parseGapValue(row.simulated_gap_to_leader))
  }

  const laps = (sim.simulated_laps || []).map((row) => {
    const lap = Math.round(Number(row.lap))
    const origLap = originalDriver.laps.find((l) => l.lap === lap)
    let gapToLeader = null
    if (traceMap.has(lap)) {
      gapToLeader = traceMap.get(lap)
    } else {
      gapToLeader =
        origLap?.gapToLeader != null && Number.isFinite(origLap.gapToLeader)
          ? origLap.gapToLeader
          : null
    }
    return {
      lap,
      time_s: row.simulated_lap_time_sec != null ? Number(row.simulated_lap_time_sec) : null,
      gapToLeader,
      position:
        origLap?.position != null && Number.isFinite(origLap.position) ? origLap.position : null,
      compound: String(row.compound || 'MEDIUM').toUpperCase(),
      tyreAge: Math.round(Number(row.simulated_tyre_age)) || 1,
      isPitLap: lap === sim.new_pit_lap,
    }
  })

  const pitStops = (modifiedStrategy?.pitStops || originalDriver.pitStops).map((p) => ({
    lap: Math.round(Number(p.lap)),
    fromCompound: String(p.fromCompound || 'MEDIUM').toUpperCase(),
    toCompound: String(p.toCompound || 'HARD').toUpperCase(),
    duration_s: Number(p.duration_s) || 22,
  }))

  return {
    code: originalDriver.code,
    color: originalDriver.color,
    laps,
    pitStops,
  }
}

/**
 * Find first pit stop whose lap differs from original (after user drags).
 */
export function diffPitChange(originalPits, modifiedPits) {
  if (!modifiedPits?.length) return null
  const orig = originalPits || []
  for (let i = 0; i < modifiedPits.length; i++) {
    const m = modifiedPits[i]
    const o = orig[i]
    const ml = Math.round(Number(m.lap))
    const ol = o != null ? Math.round(Number(o.lap)) : null
    if (o == null || ml !== ol) {
      return {
        index: i,
        new_pit_lap: ml,
        new_compound: m.toCompound != null ? String(m.toCompound) : undefined,
        pit_loss_sec: Number(m.duration_s) || 22,
      }
    }
  }
  return null
}
