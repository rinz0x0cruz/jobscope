import { useMemo } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { searchSchema, type SearchState } from '@/lib/urlState'

/** Ergonomic typed read/update of the URL search state. `set` merges a patch;
 *  pass `{ replace: true }` for high-frequency updates (e.g. search typing) so we
 *  don't flood the history stack. */
export function useSearchState() {
  const raw = useSearch({ strict: false }) as Record<string, unknown>
  // Stabilise across renders (keyed on the serialised search) so downstream
  // useMemo selectors don't recompute every render.
  const key = JSON.stringify(raw)
  const state = useMemo(() => searchSchema.parse(raw), [key])
  const navigate = useNavigate()

  const set = (patch: Partial<SearchState>, opts?: { replace?: boolean }) => {
    void navigate({
      to: '/',
      search: (prev: Record<string, unknown>) => ({ ...searchSchema.parse(prev), ...patch }),
      replace: opts?.replace ?? false,
    })
  }

  return { state, set }
}
