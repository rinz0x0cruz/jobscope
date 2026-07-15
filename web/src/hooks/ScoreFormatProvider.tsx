import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ScoreFormatContext, type ScoreFormat } from './scoreFormatContext'

const KEY = 'jobscope-score-format'

function readInitial(): ScoreFormat {
  try {
    return localStorage.getItem(KEY) === 'grade' ? 'grade' : 'number'
  } catch {
    return 'number'
  }
}

export function ScoreFormatProvider({ children }: { children: ReactNode }) {
  const [format, setFormat] = useState<ScoreFormat>(readInitial)
  useEffect(() => {
    try {
      localStorage.setItem(KEY, format)
    } catch {
      // Private mode keeps the choice in memory only.
    }
  }, [format])
  const toggle = useCallback(
    () => setFormat((current) => (current === 'number' ? 'grade' : 'number')),
    [],
  )
  return (
    <ScoreFormatContext.Provider value={{ format, setFormat, toggle }}>
      {children}
    </ScoreFormatContext.Provider>
  )
}