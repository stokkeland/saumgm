import createClient, { type Middleware } from 'openapi-fetch'

import type { components, paths } from './schema'

export type Schemas = components['schemas']

/** An error from the API, with the server's message ready to show to the user. */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const CSRF_COOKIE = 'saumgm_csrf'
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
    ?.slice(name.length + 1)
}

/** Listeners told when the session has ended (401), so the app can show the login page. */
const sessionListeners = new Set<() => void>()
export function onSessionExpired(listener: () => void): () => void {
  sessionListeners.add(listener)
  return () => sessionListeners.delete(listener)
}

const middleware: Middleware = {
  onRequest({ request }) {
    // Cookie-authenticated changes must echo the CSRF token (double-submit).
    if (!SAFE_METHODS.has(request.method)) {
      const token = cookie(CSRF_COOKIE)
      if (token) request.headers.set('X-CSRF-Token', decodeURIComponent(token))
    }
    return request
  },
  onResponse({ response, request }) {
    if (response.status === 401 && !request.url.endsWith('/api/auth/login')) {
      sessionListeners.forEach((listener) => listener())
    }
    return response
  },
}

// Typed API client: paths, parameters and responses come from the backend's OpenAPI schema
// (regenerate with `npm run gen:api` after changing the API).
export const api = createClient<paths>({ baseUrl: '/' })
api.use(middleware)

type Detail = string | { msg: string; loc?: (string | number)[] }[] | undefined

function message(status: number, body: unknown): string {
  const detail = (body as { detail?: Detail } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const field = d.loc?.filter((part) => part !== 'body').join('.')
        return field ? `${field}: ${d.msg}` : d.msg
      })
      .join('\n')
  }
  return status >= 500 ? 'The server had a problem; please try again.' : `Request failed (${status})`
}

/** Return the data of an openapi-fetch result, or throw an ApiError with a readable message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(result.response.status, message(result.response.status, result.error))
  }
  return result.data as T
}

/**
 * A request by URL, for the few places that build paths dynamically (e.g. generic deletes).
 * Same CSRF and error handling as the typed client.
 */
export async function send(method: string, url: string, body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = cookie(CSRF_COOKIE)
  if (!SAFE_METHODS.has(method) && token) headers['X-CSRF-Token'] = decodeURIComponent(token)
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 401) sessionListeners.forEach((listener) => listener())
  const data = response.status === 204 ? undefined : await response.json().catch(() => undefined)
  if (!response.ok) throw new ApiError(response.status, message(response.status, data))
  return data
}

export type Health = Schemas['Health']
