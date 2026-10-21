import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

// Typed API client: paths, parameters and responses come from the backend's OpenAPI schema
// (regenerate with `npm run gen:api` after changing the API).
export const api = createClient<paths>({ baseUrl: '/' })

export type Health = components['schemas']['Health']
