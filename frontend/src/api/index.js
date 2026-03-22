const BASE = '/api'

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export function fetchRaces() {
  return request('/races')
}

export function fetchRaceData(year, round) {
  return request(`/race/${year}/${round}`)
}

export function fetchDrivers(year, round) {
  return request(`/drivers/${year}/${round}`)
}

export function fetchSimulation(year, round, strategy) {
  return request(`/simulate`, {
    method: 'POST',
    body: JSON.stringify({ year, round, strategy }),
  })
}
