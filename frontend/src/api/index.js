/**
 * Backend: FastAPI on port 8000 (see vite proxy /api -> 8000).
 */

const BASE = '/api'

async function request(path, options = {}) {
  const { parseJson = true, ...init } = options
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init.headers },
    ...init,
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const err = await res.json()
      msg = err.detail != null ? (typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)) : msg
    } catch {
      const text = await res.text().catch(() => '')
      if (text) msg = text.slice(0, 500)
    }
    throw new Error(msg || `HTTP ${res.status}`)
  }
  if (!parseJson) return res
  return res.json()
}

/** @returns {Promise<number[]>} */
export function fetchYears() {
  return request('/options/years')
}

/**
 * @param {number} year
 * @returns {Promise<{ year: number, grand_prix: string, country: string, label: string, cache_tag: string }[]>}
 * Use `year`, `grand_prix`, `country` for load — **never** send `label` as grand_prix.
 */
export function fetchRacesForYear(year) {
  return request(`/races?year=${encodeURIComponent(year)}`)
}

/**
 * POST /api/race body must be exactly this shape (numbers/strings from the race list row):
 *
 * ```json
 * { "year": 2023, "grand_prix": "Las Vegas Grand Prix", "country": "United States" }
 * ```
 *
 * Do not use `label` or any combined "2023 - …" string as `grand_prix`.
 *
 * @param {{ year: number, grand_prix: string, country: string }} raceRow — fields from `fetchRacesForYear`, not display text
 */
export function fetchRaceData(raceRow) {
  const year = Number(raceRow.year)
  const grand_prix = String(raceRow.grand_prix ?? '').trim()
  const country = String(raceRow.country ?? '').trim()
  if (!year || !grand_prix || !country) {
    return Promise.reject(
      new Error(
        'POST /api/race needs { year, grand_prix, country } from the API race list — not the label string.'
      )
    )
  }
  const body = { year, grand_prix, country }
  return request('/race', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * @param {object} body
 * @param {string} [body.cache_tag]
 * @param {number} [body.year]
 * @param {string} [body.grand_prix]
 * @param {string} [body.country]
 * @param {string} body.driver
 * @param {number} body.new_pit_lap
 * @param {string} [body.new_compound]
 * @param {number} [body.pit_loss_sec]
 */
export function fetchSimulation(body) {
  return request('/simulate', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
