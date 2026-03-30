const AUTH_TOKEN_KEY = 'auth_token'

function _getAuthHeaders() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY)
  if (token) {
    return { Authorization: `Bearer ${token}` }
  }
  return {}
}

function _handle401(response) {
  if (response.status === 401) {
    const wasLoggedIn = !!localStorage.getItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem('auth_user')
    if (wasLoggedIn) {
      window.dispatchEvent(new CustomEvent('auth_expired', { detail: 'Session expired. Please login again.' }))
    } else {
      window.dispatchEvent(new Event('auth_expired'))
    }
  }
}

function _formatErrorMessage(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(err => {
      const field = err.loc ? err.loc[err.loc.length - 1] : ''
      return field ? `${field}: ${err.msg}` : err.msg
    }).join(', ')
  }
  if (detail && typeof detail === 'object') {
    return JSON.stringify(detail)
  }
  return 'Unknown error'
}

export async function fetchWithAuth(url, options = {}) {
  const headers = { ..._getAuthHeaders(), ...(options.headers || {}) }
  const response = await fetch(url, { ...options, headers })
  _handle401(response)
  return response
}

export async function fetchJson(url, options = {}) {
  const response = await fetchWithAuth(url, options)
  let payload = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }

  if (!response.ok) {
    const message = _formatErrorMessage(payload?.detail) || `Request failed (${response.status})`
    throw new Error(message)
  }

  return payload
}

export async function fetchJsonWithMeta(url, options = {}) {
  const start = performance.now()
  const response = await fetchWithAuth(url, options)
  let payload = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }

  const durationMs = Math.round(performance.now() - start)

  if (!response.ok) {
    const message = _formatErrorMessage(payload?.detail) || `Request failed (${response.status})`
    throw new Error(message)
  }

  return { payload, response, durationMs }
}

export async function fetchJsonRaw(url, options = {}) {
  const response = await fetchWithAuth(url, options)
  let payload = {}

  if (response.status !== 304) {
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
  }

  if (!response.ok && response.status !== 304) {
    const message = _formatErrorMessage(payload?.detail) || `Request failed (${response.status})`
    throw new Error(message)
  }

  return { response, payload }
}
