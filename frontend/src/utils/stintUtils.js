export const COMPOUND_COLORS = {
  SOFT: '#ff3333',
  MEDIUM: '#ffd700',
  HARD: '#e8e8e8',
  INTERMEDIATE: '#3cc54e',
  WET: '#3388ee',
}

/**
 * @param {{ laps: { lap: number, compound?: string }[] }} driver
 * @param {Array<{ lap: number, fromCompound?: string, toCompound?: string, duration_s?: number }>} pitStops
 * @param {number} totalLaps
 */
export function buildStints(driver, pitStops, totalLaps) {
  const stints = []
  let stintStart = 1

  for (const pit of pitStops) {
    const startLapData = driver.laps.find((l) => l.lap === stintStart)
    stints.push({
      startLap: stintStart,
      endLap: pit.lap - 1,
      compound: pit.fromCompound || startLapData?.compound || 'MEDIUM',
    })
    stintStart = pit.lap
  }

  const lastPit = pitStops[pitStops.length - 1]
  stints.push({
    startLap: stintStart,
    endLap: totalLaps,
    compound:
      lastPit?.toCompound
      || driver.laps.find((l) => l.lap === stintStart)?.compound
      || 'HARD',
  })

  return stints
}

/** Lap 1..N → 0–100% along track (same as previous D3 linear domain). */
export function lapToPct(lap, totalLaps) {
  const span = Math.max(1, totalLaps - 1)
  return ((Number(lap) - 1) / span) * 100
}

export function stintLayout(stints, totalLaps) {
  const span = Math.max(1, totalLaps - 1)
  return stints.map((s) => {
    const leftPct = lapToPct(s.startLap, totalLaps)
    /** Match prior D3 scale: bar width x(end)−x(start) on domain [1, totalLaps]. */
    const widthPct = Math.max(0.35, ((s.endLap - s.startLap) / span) * 100)
    return {
      ...s,
      leftPct,
      widthPct,
      span,
    }
  })
}

export function pitLayoutPct(pitLap, totalLaps) {
  return lapToPct(pitLap, totalLaps)
}
