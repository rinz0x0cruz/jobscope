import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

// How a job's fit is shown on cards and in the drawer: the raw 0–100 number or an
// A–F letter grade. Persisted per-browser in localStorage, mirroring useTheme and
// the Applications view switcher.
export type ScoreFormat = 'number' | 'grade'

const KEY = 'jobscope-score-format'

function readInitial(): ScoreFormat {
  try {
    return localStorage.getItem(KEY) === 'grade' ? 'grade' : 'number'
  } catch {
    return 'number'
  }
}

interface ScoreFormatCtx {
  format: ScoreFormat
  setFormat: (f: ScoreFormat) => void
  toggle: () => void
}

const Ctx = createContext<ScoreFormatCtx>({
  format: 'number',
  setFormat: () => {},
  toggle: () => {},
})

export function ScoreFormatProvider({ children }: { children: ReactNode }) {
  const [format, setFormat] = useState<ScoreFormat>(readInitial)
  useEffect(() => {
    try {
      localStorage.setItem(KEY, format)
    } catch {
      /* private mode: keep the choice in memory only */
    }
  }, [format])
  const toggle = useCallback(() => setFormat((f) => (f === 'number' ? 'grade' : 'number')), [])
  return <Ctx.Provider value={{ format, setFormat, toggle }}>{children}</Ctx.Provider>
}

export function useScoreFormat(): ScoreFormatCtx {
  return useContext(Ctx)
}
