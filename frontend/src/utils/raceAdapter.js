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

/** Raw gap for trace / sim / ranking (may be negative); null if missing. */
function rawGap(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

/** For sorting: smaller gap = closer to leader = better rank. */
function gapForRank(g) {
  if (g == null || g === '') return Infinity
  const n = Number(g)
  return Number.isFinite(n) ? n : Infinity
}

/**
 * Each lap, rank everyone with a lap row by gap (actual gaps; simulated gap for one driver).
 * @returns {Map<number, Map<string, number>>} lap → driver code → P1..Pn
 */
function buildSimulatedFieldPositions(allDrivers, simCode, simGapsByLap) {
  const simU = String(simCode || '').toUpperCase()
  const maxLap = Math.max(
    0,
    ...allDrivers.flatMap((d) => d.laps.map((l) => l.lap)),
  )
  /** @type {Map<number, Map<string, number>>} */
  const out = new Map()
  for (let lap = 1; lap <= maxLap; lap++) {
    const row = []
    for (const d of allDrivers) {
      const lp = d.laps.find((l) => l.lap === lap)
      if (!lp) continue
      let g
      if (String(d.code).toUpperCase() === simU) {
        g = simGapsByLap.has(lap) ? simGapsByLap.get(lap) : gapForRank(lp.gapToLeader)
      } else {
        g = gapForRank(lp.gapToLeader)
      }
      row.push({ code: d.code, g })
    }
    if (!row.length) continue
    row.sort((a, b) => a.g - b.g || String(a.code).localeCompare(String(b.code)))
    const m = new Map()
    row.forEach((e, i) => m.set(e.code, i + 1))
    out.set(lap, m)
  }
  return out
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
    traceMap.set(`${d}-${lap}`, rawGap(row.gap_to_leader))
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
      gapToLeader: gap != null && Number.isFinite(gap) ? gap : null, // raw gap (may be negative)
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
 * @param {object[]|null} allDrivers - full race field for simulated position ranks; omit to keep actual positions
 */
/**
 * Gap percentiles for simulated_gap_to_leader (seconds). Sources: simulated_trace (canonical)
 * or per-lap fields on simulated_laps (simulated_gap_p05…p95 from POST /api/simulate).
 */
function gapPercentilesFromTraceRow(row) {
  return {
    gap: rawGap(row.simulated_gap_to_leader),
    p5: rawGap(row.p5 ?? row.simulated_gap_p05),
    p25: rawGap(row.p25 ?? row.simulated_gap_p25),
    p75: rawGap(row.p75 ?? row.simulated_gap_p75),
    p95: rawGap(row.p95 ?? row.simulated_gap_p95),
  }
}

function gapPercentilesFromLapRow(row) {
  return {
    gap: null,
    p5: rawGap(row.p5 ?? row.simulated_gap_p05),
    p25: rawGap(row.p25 ?? row.simulated_gap_p25),
    p75: rawGap(row.p75 ?? row.simulated_gap_p75),
    p95: rawGap(row.p95 ?? row.simulated_gap_p95),
  }
}

export function simulateToViewModel(sim, originalDriver, modifiedStrategy, allDrivers = null) {
  /** @type {Map<number, { gap: number | null, p5?: null, p25?: null, p75?: null, p95?: null }>} */
  const traceMeta = new Map()
  for (const row of sim.simulated_trace || []) {
    const lap = Math.round(Number(row.lap))
    traceMeta.set(lap, gapPercentilesFromTraceRow(row))
  }
  for (const row of sim.simulated_laps || []) {
    const lap = Math.round(Number(row.lap))
    const fromLap = gapPercentilesFromLapRow(row)
    const prev = traceMeta.get(lap)
    if (!prev) {
      traceMeta.set(lap, {
        gap: fromLap.gap,
        p5: fromLap.p5,
        p25: fromLap.p25,
        p75: fromLap.p75,
        p95: fromLap.p95,
      })
      continue
    }
    const merged = { ...prev }
    for (const k of ['p5', 'p25', 'p75', 'p95']) {
      if (merged[k] == null && fromLap[k] != null) merged[k] = fromLap[k]
    }
    traceMeta.set(lap, merged)
  }

  /** @type {Map<number, number>} */
  const simGapsByLap = new Map()
  for (const [lap, meta] of traceMeta) {
    if (meta.gap != null) simGapsByLap.set(lap, meta.gap)
  }

  const posRankByLap =
    allDrivers?.length > 0
      ? buildSimulatedFieldPositions(allDrivers, originalDriver.code, simGapsByLap)
      : null

  const laps = (sim.simulated_laps || []).map((row) => {
    const lap = Math.round(Number(row.lap))
    const origLap = originalDriver.laps.find((l) => l.lap === lap)
    const meta = traceMeta.get(lap)
    let gapToLeader = null
    if (meta?.gap != null) {
      gapToLeader = meta.gap
    } else {
      gapToLeader =
        origLap?.gapToLeader != null && Number.isFinite(origLap.gapToLeader)
          ? origLap.gapToLeader
          : null
    }

    let position = parsePosition(origLap?.position)
    if (posRankByLap) {
      const rankMap = posRankByLap.get(lap)
      const ranked = rankMap?.get(originalDriver.code)
      if (ranked != null && Number.isFinite(ranked)) position = ranked
    }

    return {
      lap,
      time_s: row.simulated_lap_time_sec != null ? Number(row.simulated_lap_time_sec) : null,
      gapToLeader,
      p5: meta?.p5 ?? null,
      p25: meta?.p25 ?? null,
      p75: meta?.p75 ?? null,
      p95: meta?.p95 ?? null,
      position,
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
    monteCarloSamples: Number(sim.monte_carlo_samples) || 1,
    hasSimulatedGapUncertainty: Boolean(sim.has_simulated_gap_uncertainty),
  }
}

/**
 * Find first pit stop whose lap differs from original (after user drags).
 */
/**
 * Replace one driver's race_trace gaps with simulated gaps (for strategy-viz / sim delta).
 * @param {object} rawRace - envelope.race shape
 * @param {string} driverCode
 * @param {Array<{ lap: number, simulated_gap_to_leader: number }>} simulatedTrace
 */
export function mergeSimulatedRaceTrace(rawRace, driverCode, simulatedTrace) {
  const code = String(driverCode || '')
    .trim()
    .toUpperCase()
  const prev = rawRace.race_trace || []
  const filtered = prev.filter((r) => String(r.driver || '').toUpperCase() !== code)
  const added = (simulatedTrace || []).map((row) => ({
    driver: code,
    lap: row.lap,
    gap_to_leader: row.simulated_gap_to_leader,
  }))
  return { ...rawRace, race_trace: [...filtered, ...added] }
}

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
