import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/**
 * List filters kept in the URL query string, so Back returns to the same view and links can be
 * shared. Changing any filter except the offset resets paging.
 */
export function useUrlState<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams()

  const values = Object.fromEntries(
    Object.entries(defaults).map(([key, fallback]) => [key, params.get(key) ?? fallback]),
  ) as T

  const set = useCallback(
    (changes: Partial<T>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          for (const [key, value] of Object.entries(changes)) {
            if (value === undefined || value === '' || value === defaults[key]) next.delete(key)
            else next.set(key, String(value))
          }
          if (!('offset' in changes)) next.delete('offset')
          return next
        },
        { replace: true },
      )
    },
    [setParams, defaults],
  )

  return [values, set] as const
}
